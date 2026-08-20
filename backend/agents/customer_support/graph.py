"""
Customer Support Agent — LangGraph pipeline.

Same shape as every other agent's graph.py:
    build_context   (Step 1 — read Postgres: customer profile, recent
                      orders, return history, open tickets, conversation
                      thread history, + Inventory's open alerts. Also
                      resolves/creates the conversation thread and logs
                      the inbound message for an event-driven run — see
                      db/crud_customer_support.py::get_business_context.)
        -> reason           (Steps 2-4 — ReAct loop; tools = live Shopify
                              order/refund/cancel + Instagram DM + courier
                              tracking via mcp_client.py, plus internal
                              eligibility/refund-math/escalation/
                              sentiment/ticket/RAG tools, all called on
                              demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured SupportDecision)
        -> persist          (Step 7 — write support insights + close the
                              conversation if resolved + execution log +
                              memory)

RAG note: same as every other agent in this codebase — retrieval is NOT a
forced pre-fetch node. It's the retrieve_policy / search_agent_memory
tools in agents/customer_support/tools.py, backed by
agents/customer_support/memory.py's Chroma collections, called only when
the ReAct loop decides it needs a policy number or past-conversation
context. See that module's docstring for the full reasoning — identical
to every other agent's memory.py.

Operational note: create_support_ticket, update_ticket_status,
record_refund, create_exchange, send_customer_message, and
flag_recurring_issue all write real rows / send real messages mid-loop —
same pattern as every other agent's operational tools. create_refund and
cancel_order are the two real Shopify writes, called via shopify-mcp
(mcp_client.py), same as Sales' create_discount_code or Inventory's
set_inventory_level.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

from langgraph.graph import END, StateGraph
from deepagents import CompiledSubAgent, create_deep_agent
from langchain_mistralai import ChatMistralAI
from langchain.chat_models import init_chat_model

from agents.common.progress import AnnounceToolCalls, progress as emit_progress
from agents.common.task_input import resolve_task_input
from agents.common.tool_scoping import scope_tools_to_brand
from db import crud_customer_support as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_customer_support_tools
from .output_schema import SupportDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .state import SupportPipelineState
from .tools import build_internal_tools


# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

async def build_context_node(state: SupportPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[CustomerSupportAgent] Building business context for brand_id=%s", brand_id)
    emit_progress("build_context", "started", "Building business context")
    task_obj = state.get("task", {})
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, brand_id, task_obj if isinstance(task_obj, dict) else {})
        await session.commit()
    emit_progress("build_context", "done", "Business context ready")
    return {"context": context}


async def reasoning_node(state: SupportPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[CustomerSupportAgent] Running reasoning node for brand_id=%s", brand_id)
    emit_progress("reason", "started", "Running analysis — calling tools as needed")

    live_tools = scope_tools_to_brand(await get_customer_support_tools(), brand_id)
    internal_tools = build_internal_tools(brand_id)
    tools = [*live_tools, *internal_tools]

    model = ChatMistralAI(
        model="mistral-medium-3-5",
        temperature=0,
        model_kwargs={"reasoning_effort": "high"},
    )

    agent = create_deep_agent(model, tools, middleware=[AnnounceToolCalls()])

    task_prompt = build_task_prompt(resolve_task_input(state), state.get("context", {}))
    result = await agent.ainvoke({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ]
    })

    tools_used = sorted({
        call["name"]
        for message in result["messages"]
        for call in (getattr(message, "tool_calls", None) or [])
    })

    emit_progress("reason", "done", "Analysis complete")
    logger.info("[CustomerSupportAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: SupportPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[CustomerSupportAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    emit_progress("extract_decision", "started", "Extracting structured decision")
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(SupportDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: SupportDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "customer support decision. customer_reply must be the exact text that was (or should "
        "be) sent to the customer — not a summary of it. In actions_executed, list only things "
        "that actually happened (a tool call succeeded) — not things merely proposed:\n\n" + transcript
    )

    logger.info("[CustomerSupportAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    emit_progress("extract_decision", "done", "Decision extracted")
    return {
        "ticket": decision.ticket.model_dump(),
        "customer_reply": decision.customer_reply,
        "customer_sentiment": decision.customer_sentiment,
        "insights": [i.model_dump() for i in decision.insights],
        "actions_executed": decision.actions_executed,
        "escalation_required": decision.escalation_required,
        "escalation_reason": decision.escalation_reason,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: SupportPipelineState) -> dict:
    brand_id = state["brand_id"]
    insights = state.get("insights", [])
    summary = state.get("summary", "")
    ticket = state.get("ticket", {})
    conversation_id = state.get("context", {}).get("conversation_id")

    logger.info("[CustomerSupportAgent] Persisting outputs for brand_id=%s (insights=%d)", brand_id, len(insights))
    emit_progress("persist", "started", "Persisting results")
    async with AsyncSessionLocal() as session:
        if insights:
            await crud.save_support_insights(session, brand_id, insights)
        if summary:
            await crud.save_agent_memory(session, brand_id, "customer_support_agent", summary, kind="run_summary")
        # Close the conversation thread once the ticket reached a terminal
        # resolved state — mirrors the ticket status the agent itself set
        # via update_ticket_status mid-loop, so the thread doesn't linger
        # "open" after the issue is actually done.
        await crud.close_conversation_if_resolved(session, conversation_id, ticket.get("status") == "resolved")
        await session.commit()

    db_updates = []
    if insights:
        db_updates.append(f"support_insights: +{len(insights)}")

    emit_progress("persist", "done", "Results saved")
    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_customer_support_graph():
    graph = StateGraph(SupportPipelineState)
    graph.add_node("build_context", build_context_node)
    graph.add_node("reason", reasoning_node)
    graph.add_node("extract_decision", extract_decision_node)
    graph.add_node("persist", persist_node)

    graph.set_entry_point("build_context")
    graph.add_edge("build_context", "reason")
    graph.add_edge("reason", "extract_decision")
    graph.add_edge("extract_decision", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_customer_support_graph = None


def get_customer_support_graph():
    global _customer_support_graph
    if _customer_support_graph is None:
        _customer_support_graph = build_customer_support_graph()
    return _customer_support_graph


async def run_customer_support_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor/webhook input, e.g.:
        {"task_type": "handle_customer_message", "channel": "whatsapp",
         "external_thread_id": "+923001234567", "message": "Where is my order?"}
    or:
        {"task_type": "handle_customer_issue", "customer_id": "CUS-1024",
         "channel": "whatsapp", "issue": "Customer wants to exchange a shirt"}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    logger.info("[CustomerSupportAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
    graph = get_customer_support_graph()
    initial_state: SupportPipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("[CustomerSupportAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "customer_support_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[CustomerSupportAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "customer_support_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "ticket": final_state.get("ticket", {}),
        "customer_reply": final_state.get("customer_reply", ""),
        "customer_sentiment": final_state.get("customer_sentiment", "mixed"),
        "insights": final_state.get("insights", []),
        "actions_executed": final_state.get("actions_executed", []),
        "escalation_required": final_state.get("escalation_required", False),
        "escalation_reason": final_state.get("escalation_reason", ""),
        "conversation_id": final_state.get("context", {}).get("conversation_id"),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



customer_support_agent = CompiledSubAgent(
    name="customer_support_agent",
    description=(
        "Customer Support agent — the brand's AI Customer Success Manager. Handles the full "
        "support lifecycle across WhatsApp, Instagram DM, email, and website chat: answers order "
        "status and product questions, investigates delivery delays via courier tracking, and "
        "resolves returns/exchanges/refunds/cancellations/complaints under this brand's actual "
        "policy — it doesn't just reply, it resolves. Reads the customer's real order/return "
        "history and any of Inventory's/Sales' relevant signals instead of guessing. "
        "OPERATIONAL: it can create real Shopify refunds, cancel unfulfilled orders, create "
        "exchanges, open/update support tickets, message the customer back on their own channel, "
        "flag recurring product/delivery/policy patterns (including straight into Inventory's own "
        "alert feed when a SKU is the root cause), and alert the brand owner. Escalates rather "
        "than auto-resolving anything over the refund approval limit or a churn-risk case. "
        "Delegate for anything about a customer conversation, order status question, delivery "
        "issue, return, exchange, refund, cancellation, or complaint (handle_customer_message, "
        "handle_customer_issue, process_return, check_order_status, escalation_review). Include "
        "the channel + external_thread_id (or customer_id/order_id) and the customer's message/"
        "issue in the task description."
    ),
    runnable=get_customer_support_graph()
)