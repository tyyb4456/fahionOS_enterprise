"""
Inventory Agent — LangGraph pipeline.

Flow (see design doc):
    build_context   (Step 1 — read Postgres: products, sales, POs, suppliers,
                      warehouses, seasonal calendar)
        -> reason           (Steps 2-4 — ReAct loop; tools = live Shopify
                              data via shopify-mcp + forecasting + supplier/
                              warehouse lookups + RAG (policies + past run
                              notes) + real actions (create_purchase_order,
                              notify_supplier), all called on demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured AgentDecision)
        -> persist          (Step 7 — write forecasts/recommendations/alerts
                              + execution log + memory)

Steps 2 ("Fetch Live Data"), 3 ("Retrieve Memory / RAG"), and the forecast
model are all on-demand tools inside the ReAct loop rather than forced
pre-steps. A blind pre-fetch runs one fixed, generic query regardless of
what the agent ends up needing; a targeted retrieve_policy("ABC Textile
reorder terms") call once the agent has seen a real low-stock SKU and
supplier beats a canned query every time, and skips the round-trip
entirely on runs where policy context doesn't end up mattering.

Operational note: create_purchase_order and notify_supplier make real,
immediate changes mid-loop (a purchase_orders row, an outbound message) —
same pattern as shopify-mcp's set_inventory_level. This agent is no longer
"recommend, don't act"; see agents/inventory/prompts.py.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from deepagents import create_deep_agent
from langchain_mistralai import ChatMistralAI
from langchain.chat_models import init_chat_model
from deepagents import CompiledSubAgent

from db import crud_inventory as crud
from db.session import AsyncSessionLocal
from .state import InventoryPipelineState

from .mcp_client import get_shopify_tools
from .output_schema import AgentDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .tool_scoping import scope_tools_to_brand
from .tools import build_internal_tools

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

async def build_context_node(state: InventoryPipelineState) -> dict:
    logger.info("[InventoryAgent] Building business context for brand_id=%s", state["brand_id"])
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, state["brand_id"])
    return {"context": context}


async def reasoning_node(state: InventoryPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[InventoryAgent] Running reasoning node for brand_id=%s", brand_id)

    shopify_tools = scope_tools_to_brand(await get_shopify_tools(), brand_id)
    internal_tools = build_internal_tools(brand_id)
    tools = [*shopify_tools, *internal_tools]

    model = ChatMistralAI(
        model="mistral-medium-3-5",
        temperature=0,
        model_kwargs={"reasoning_effort": "high"},
    )

    agent = create_deep_agent(model, tools)

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

    logger.info("[InventoryAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: InventoryPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[InventoryAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(AgentDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: AgentDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "inventory decision. In actions_executed, list only things that actually happened "
        "(a tool call succeeded) — not things merely proposed:\n\n" + transcript
    )

    logger.info("[InventoryAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    return {
        "forecasts": [f.model_dump() for f in decision.forecasts],
        "recommendations": [r.model_dump() for r in decision.recommendations],
        "alerts": [a.model_dump() for a in decision.alerts],
        "actions_executed": decision.actions_executed,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: InventoryPipelineState) -> dict:
    brand_id = state["brand_id"]
    forecasts = state.get("forecasts", [])
    recommendations = state.get("recommendations", [])
    alerts = state.get("alerts", [])

    logger.info("[InventoryAgent] Persisting outputs for brand_id=%s (forecasts=%d, recs=%d, alerts=%d)", brand_id, len(forecasts), len(recommendations), len(alerts))
    async with AsyncSessionLocal() as session:
        await crud.save_forecasts(session, brand_id, forecasts)
        await crud.save_recommendations(session, brand_id, recommendations)
        await crud.save_alerts(session, brand_id, alerts)
        if state.get("summary"):
            await crud.save_agent_memory(session, brand_id, "inventory_agent", state["summary"], kind="run_summary")
        await session.commit()

    db_updates = []
    if forecasts:
        db_updates.append(f"inventory_forecasts: +{len(forecasts)}")
    if recommendations:
        db_updates.append(f"reorder_recommendations: +{len(recommendations)}")
    if alerts:
        db_updates.append(f"inventory_alerts: +{len(alerts)}")

    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_inventory_graph():
    graph = StateGraph(InventoryPipelineState)
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


_inventory_graph = None


def get_inventory_graph():
    global _inventory_graph
    if _inventory_graph is None:
        _inventory_graph = build_inventory_graph()
    return _inventory_graph


async def run_inventory_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor input, e.g.:
        {"task_type": "forecast_inventory", "forecast_days": 30,
         "priority": "high", "trigger": "daily_scheduler"}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    logger.info("[InventoryAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
    graph = get_inventory_graph()
    initial_state: InventoryPipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("[InventoryAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "inventory_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[InventoryAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "inventory_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    alerts = final_state.get("alerts", [])
    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "critical_alerts": [a for a in alerts if a.get("severity") in ("high", "critical")],
        "alerts": alerts,
        "recommendations": final_state.get("recommendations", []),
        "forecasts": final_state.get("forecasts", []),
        "actions_executed": final_state.get("actions_executed", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



inventory_agent = CompiledSubAgent(
    name="inventory_agent",
    description=(
        "Inventory & supply chain operations agent. Forecasts SKU demand and days-until-stockout, detects "
        "stockout/overstock risk, computes safety stock and reorder quantities, checks supplier terms (lead time, "
        "minimum order qty, pricing, reliability) and warehouse capacity, and accounts for upcoming seasonal "
        "demand. Reads live Shopify product/order/inventory data plus notes from its past runs. "
        "OPERATIONAL: it can actually place purchase orders (real DB rows), notify suppliers via WhatsApp/email, "
        "correct Shopify inventory levels, create restock recommendations, and alert the brand owner — it acts, "
        "it doesn't just recommend. "
        "Delegate whenever the founder asks about stock levels, restocking, supply chain, suppliers, or a specific "
        "forecast task (forecast_inventory, check_stockouts, reorder_analysis, overstock_analysis, "
        "full_inventory_review). In the task description, state the goal clearly and include any specifics (SKU(s), "
        "forecast window, priority); the agent pulls the rest of the context it needs."
    ),
    runnable=get_inventory_graph()
)