"""
Supplier Agent — LangGraph pipeline.

Same shape as agents/inventory/graph.py, agents/sales/graph.py,
agents/marketing/graph.py, and agents/finance/graph.py:
    build_context   (Step 1 — read Postgres: Inventory's unresolved sourcing
                      needs/alerts, suppliers, open POs + shipment status,
                      recent quotes/negotiations)
        -> reason           (Steps 2-4 — ReAct loop; tools = live Shopify
                              product context + supplier-mcp's simulated
                              marketplace search / shipment tracking, plus
                              internal supplier/quote/PO/negotiation/scoring
                              tools, all called on demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured SupplierDecision)
        -> persist          (Step 7 — write supplier insights + execution
                              log + memory)

RAG note: same as the other four agents — retrieval is NOT a forced
pre-fetch node. It's the retrieve_policy / search_agent_memory tools in
agents/supplier/tools.py, backed by agents/supplier/memory.py's Chroma
collections, called only when the ReAct loop decides it needs a contract
term, a negotiation precedent, or past-run context.

Operational note: request_quotes, create_purchase_order, send_supplier_message,
update_shipment_status, record_negotiation, and update_supplier_score all
write real rows / send real messages mid-loop — same pattern as Inventory's
create_purchase_order / notify_supplier. create_purchase_order writes into
the SAME purchase_orders table Inventory can also write to (a shared-table
cross-agent write, the same pattern Sales' flag_inventory_issue already
uses against Inventory's own alert table).
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
from agents.common.tool_scoping import scope_tools_to_brand
from db import crud_supplier as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_supplier_mcp_tools
from .output_schema import SupplierDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .state import SupplierPipelineState
from .tools import build_internal_tools


# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

async def build_context_node(state: SupplierPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[SupplierAgent] Building business context for brand_id=%s", brand_id)
    emit_progress("build_context", "started", "Building business context")
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, brand_id)
    emit_progress("build_context", "done", "Business context ready")
    return {"context": context}


async def reasoning_node(state: SupplierPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[SupplierAgent] Running reasoning node for brand_id=%s", brand_id)
    emit_progress("reason", "started", "Running analysis — calling tools as needed")

    live_tools = scope_tools_to_brand(await get_supplier_mcp_tools(), brand_id)
    internal_tools = build_internal_tools(brand_id)
    tools = [*live_tools, *internal_tools]

    model = ChatMistralAI(
        model="mistral-medium-3-5",
        temperature=0,
        model_kwargs={"reasoning_effort": "high"},
    )

    agent = create_deep_agent(model, tools, middleware=[AnnounceToolCalls()])

    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        task_input = getattr(last_msg, "content", str(last_msg))
    else:
        task_input = state.get("task", {})

    task_prompt = build_task_prompt(task_input, state.get("context", {}))
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
    logger.info("[SupplierAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: SupplierPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[SupplierAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    emit_progress("extract_decision", "started", "Extracting structured decision")
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(SupplierDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: SupplierDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "procurement decision. In actions_executed, list only things that actually happened "
        "(a tool call succeeded) — not things merely proposed:\n\n" + transcript
    )

    logger.info("[SupplierAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    emit_progress("extract_decision", "done", "Decision extracted")
    return {
        "supplier_recommendations": [r.model_dump() for r in decision.supplier_recommendations],
        "quote_comparisons": [q.model_dump() for q in decision.quote_comparisons],
        "purchase_orders": [p.model_dump() for p in decision.purchase_orders],
        "negotiation_plans": [n.model_dump() for n in decision.negotiation_plans],
        "shipment_updates": [s.model_dump() for s in decision.shipment_updates],
        "insights": [i.model_dump() for i in decision.insights],
        "actions_executed": decision.actions_executed,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: SupplierPipelineState) -> dict:
    brand_id = state["brand_id"]
    insights = state.get("insights", [])
    summary = state.get("summary", "")

    logger.info("[SupplierAgent] Persisting outputs for brand_id=%s (insights=%d)", brand_id, len(insights))
    emit_progress("persist", "started", "Persisting results")
    async with AsyncSessionLocal() as session:
        if insights:
            await crud.save_supplier_insights(session, brand_id, insights)
        if summary:
            await crud.save_agent_memory(session, brand_id, "supplier_agent", summary, kind="run_summary")
        await session.commit()

    db_updates = []
    if insights:
        db_updates.append(f"supplier_insights: +{len(insights)}")

    emit_progress("persist", "done", "Results saved")
    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_supplier_graph():
    graph = StateGraph(SupplierPipelineState)
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


_supplier_graph = None


def get_supplier_graph():
    global _supplier_graph
    if _supplier_graph is None:
        _supplier_graph = build_supplier_graph()
    return _supplier_graph


async def run_supplier_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor input, e.g.:
        {"task_type": "procure_inventory", "sku": "HD001", "quantity": 500,
         "deadline": "2026-08-15"}
    or:
        {"task_type": "find_supplier", "product": "Oversized Hoodie"}
    or:
        {"task_type": "track_purchase_order", "purchase_order_id": "..."}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    logger.info("[SupplierAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
    graph = get_supplier_graph()
    initial_state: SupplierPipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("[SupplierAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "supplier_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[SupplierAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "supplier_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "supplier_recommendations": final_state.get("supplier_recommendations", []),
        "quote_comparisons": final_state.get("quote_comparisons", []),
        "purchase_orders": final_state.get("purchase_orders", []),
        "negotiation_plans": final_state.get("negotiation_plans", []),
        "shipment_updates": final_state.get("shipment_updates", []),
        "insights": final_state.get("insights", []),
        "actions_executed": final_state.get("actions_executed", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



supplier_agent = CompiledSubAgent(
    name="supplier_agent",
    description=(
        "Supplier & procurement agent — the brand's Procurement / Supply Chain Manager. Finds and scores "
        "suppliers (on-file first, external marketplace search as a fallback), requests and compares quotes "
        "on price/lead-time/reliability/quality together (not just cheapest), negotiates terms, and checks "
        "affordability against Finance's cash math before spending. Reads the Inventory Agent's unresolved "
        "reorder recommendations and alerts as its sourcing triggers instead of re-forecasting demand itself. "
        "OPERATIONAL: it can request quotes, message suppliers (WhatsApp/email), place real purchase orders, "
        "track shipments, log negotiations, update supplier reliability/quality scores, and alert the brand "
        "owner — it runs procurement, it doesn't just suggest it. "
        "Delegate for anything about sourcing, suppliers, quotes, purchase orders, shipment status, or "
        "vendor negotiation (procure_inventory, find_supplier, track_purchase_order, negotiate, "
        "evaluate_suppliers). Include the SKU/quantity/deadline or purchase_order_id in the task description "
        "when relevant."
    ),
    runnable=get_supplier_graph()
)