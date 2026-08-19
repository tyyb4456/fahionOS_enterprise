"""
Product / Merchandising Agent — LangGraph pipeline.

Same shape as agents/research/graph.py (the closest architectural
precedent — broad cross-agent reads, conditional operational writes):
    build_context   (Step 1 — read Postgres: our own catalog, variant-level
                      sales breakdown, Inventory's alerts, Research's
                      opportunities/trends/competitor analysis, Marketing's
                      insights/campaigns, Finance's margin snapshot,
                      Supplier's on-file suppliers, + this agent's own
                      recent proposals/collections/lifecycle)
        -> reason           (Steps 2-4 — ReAct loop; tools = a read+write
                              shopify-mcp subset (catalog reads +
                              create_product/update_product_details/
                              add_product_variant) plus internal lookup/
                              scoring/creative/operational tools, all
                              called on demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured ProductDecision: proposals,
                              collections, lifecycle_updates, insights —
                              the routine, always-attempted per-run output)
        -> persist          (Step 7 — write proposals/collections/
                              lifecycle_updates/insights + execution log +
                              memory)

RAG note: same as every other agent in this codebase — retrieval is NOT a
forced pre-fetch node. It's the retrieve_policy / search_agent_memory
tools in agents/product/tools.py, backed by agents/product/memory.py's
Chroma collections, called only when the ReAct loop decides it needs brand
strategy/design-guideline or past-run context.

Operational note: create_product_proposal, update_proposal_status,
update_product_lifecycle_stage, create_collection, and
add_product_to_collection write real rows mid-loop (same pattern as every
other agent's operational tools). Actually creating/publishing/archiving a
product on Shopify goes through shopify-mcp's create_product /
update_product_details / add_product_variant (added alongside Inventory's
own Shopify write tools in the same server) — the agent calls those
directly, then records the outcome via update_proposal_status /
update_product_lifecycle_stage.

Customer feedback note: wired against the real, confirmed Customer
Support Agent schema (db/models.py::Return/ExchangeRecord/SupportTicket/
SupportInsight, db/crud_customer_support.py) — return-reason patterns and
exchange-by-SKU patterns are precise (both tables have a real sku column);
Customer Support's own SupportInsight (category="product") rows are read
directly rather than re-derived; ticket volume is surfaced only at the
issue_type level, not per-SKU, since SupportTicket has no sku column and
forcing one via an order-level join would misattribute a ticket to every
line item on that order.

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
from db import crud_product as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_product_tools
from .output_schema import ProductDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .state import ProductPipelineState
from .tools import build_internal_tools


# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

def _category_from_task(task_obj: Any) -> str | None:
    if isinstance(task_obj, dict):
        return task_obj.get("category")
    return None


async def build_context_node(state: ProductPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[ProductAgent] Building business context for brand_id=%s", brand_id)
    emit_progress("build_context", "started", "Building business context")
    category = _category_from_task(state.get("task", {}))
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, brand_id, category=category)
    emit_progress("build_context", "done", "Business context ready")
    return {"context": context}


async def reasoning_node(state: ProductPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[ProductAgent] Running reasoning node for brand_id=%s", brand_id)
    emit_progress("reason", "started", "Running analysis — calling tools as needed")

    shopify_tools = scope_tools_to_brand(await get_product_tools(), brand_id)
    internal_tools = build_internal_tools(brand_id)
    tools = [*shopify_tools, *internal_tools]

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
    logger.info("[ProductAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: ProductPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[ProductAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    emit_progress("extract_decision", "started", "Extracting structured decision")
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(ProductDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: ProductDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "merchandising decision. In actions_executed, list only things that actually "
        "happened (a tool call succeeded — e.g. a proposal was actually recorded or a "
        "Shopify product actually created) — not things merely discussed:\n\n" + transcript
    )

    logger.info("[ProductAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    emit_progress("extract_decision", "done", "Decision extracted")
    return {
        "proposals": [p.model_dump() for p in decision.proposals],
        "collections": [c.model_dump() for c in decision.collections],
        "lifecycle_updates": [l.model_dump() for l in decision.lifecycle_updates],
        "insights": [i.model_dump() for i in decision.insights],
        "actions_executed": decision.actions_executed,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: ProductPipelineState) -> dict:
    brand_id = state["brand_id"]
    proposals = state.get("proposals", [])
    collections = state.get("collections", [])
    lifecycle_updates = state.get("lifecycle_updates", [])
    insights = state.get("insights", [])
    summary = state.get("summary", "")

    logger.info(
        "[ProductAgent] Persisting outputs for brand_id=%s (proposals=%d, collections=%d, lifecycle=%d, insights=%d)",
        brand_id, len(proposals), len(collections), len(lifecycle_updates), len(insights),
    )
    emit_progress("persist", "started", "Persisting results")
    async with AsyncSessionLocal() as session:
        proposal_ids = await crud.save_proposals(session, brand_id, proposals) if proposals else []
        collection_ids = await crud.save_collections(session, brand_id, collections) if collections else []
        if lifecycle_updates:
            await crud.save_lifecycle_updates(session, brand_id, lifecycle_updates)
        if insights:
            await crud.save_merchandising_insights(session, brand_id, insights)
        if summary:
            await crud.save_agent_memory(session, brand_id, "product_agent", summary, kind="run_summary")
        await session.commit()

    db_updates = []
    if proposal_ids:
        db_updates.append(f"product_proposals: +{len(proposal_ids)}")
    if collection_ids:
        db_updates.append(f"collections: +{len(collection_ids)}")
    if lifecycle_updates:
        db_updates.append(f"product_lifecycle: upserted {len(lifecycle_updates)}")
    if insights:
        db_updates.append(f"merchandising_insights: +{len(insights)}")

    emit_progress("persist", "done", "Results saved")
    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_product_graph():
    graph = StateGraph(ProductPipelineState)
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


_product_graph = None


def get_product_graph():
    global _product_graph
    if _product_graph is None:
        _product_graph = build_product_graph()
    return _product_graph


async def run_product_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor input, e.g.:
        {"task_type": "create_product_opportunity", "category": "oversized hoodies", "target": "Gen Z", "region": "Pakistan"}
    or:
        {"task_type": "plan_next_collection", "season": "winter", "budget": 1500000}
    or:
        {"task_type": "evaluate_variant_performance", "product_ref": "Oversized Hoodie"}
    or:
        {"task_type": "product_lifecycle_review"}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    logger.info("[ProductAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
    graph = get_product_graph()
    initial_state: ProductPipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("[ProductAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "product_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[ProductAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "product_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "proposals": final_state.get("proposals", []),
        "collections": final_state.get("collections", []),
        "lifecycle_updates": final_state.get("lifecycle_updates", []),
        "insights": final_state.get("insights", []),
        "actions_executed": final_state.get("actions_executed", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



product_agent = CompiledSubAgent(
    name="product_agent",
    description=(
        "Product & merchandising agent — the brand's Head of Product/Merchandising. Sits between market "
        "intelligence and the catalog: evaluates whether a trend or opportunity (usually from the Research "
        "Agent) is worth launching, checks brand fit, competition, supplier feasibility, and expected margin "
        "before proposing anything, and plans variant mixes (colors/sizes), collections, and initial "
        "production quantities from real sales/margin/supplier data — not guesses. "
        "OPERATIONAL: it can formally record product proposals and collections, track a product's lifecycle "
        "stage (idea through archived), and — once a proposal is approved — actually create, update, "
        "publish, or archive the product on Shopify and add new variants. It can alert the brand owner for "
        "urgent findings (e.g. a declining product, a sizing-driven return pattern). It does NOT place "
        "purchase orders, launch marketing campaigns, or change prices itself — those stay with Supplier/"
        "Inventory, Marketing, and Sales/Pricing; surface next_actions for the Supervisor to route (e.g. "
        "'Supplier: request quotes for the new cargo pants', 'Marketing: prepare a launch campaign'). "
        "Delegate for anything about what to sell, product launches, variant/color/size decisions, "
        "collections, product lifecycle (grow/decline/retire), or turning a Research opportunity into a "
        "real product (create_product_opportunity, plan_next_collection, evaluate_variant_performance, "
        "product_lifecycle_review, launch_product). Include category/season/budget/product reference in "
        "the task description when relevant."
    ),
    runnable=get_product_graph()
)