"""
Sales Agent — LangGraph pipeline.

Same shape as agents/inventory/graph.py:
    build_context   (Step 1 — read Postgres: revenue, products, returns,
                      customers, discounts, daily revenue series)
        -> reason           (Steps 2-4 — ReAct loop; tools = live Shopify
                              read data via shopify-mcp + revenue/KPI/
                              anomaly/forecast math + customer segmentation/
                              cohort + RAG, all called on demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured SalesDecision)
        -> persist          (Step 7 — write reports/insights/forecasts/
                              anomalies/customer segments + execution log +
                              memory)

RAG note: retrieval is NOT a forced pre-step/node here, same as Inventory.
It's the retrieve_policy / search_agent_memory tools in agents/sales/
tools.py, backed by agents/sales/memory.py's Chroma collections — the
ReAct loop calls them only when it decides it needs brand policy or
past-run context.
"""
from __future__ import annotations

import os
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from deepagents import CompiledSubAgent, create_deep_agent
from langchain_mistralai import ChatMistralAI
from langchain.chat_models import init_chat_model

from agents.common.tool_scoping import scope_tools_to_brand
from db import crud_sales as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_shopify_read_tools
from .output_schema import SalesDecision
from .prompts import SYSTEM_PROMPT, build_task_prompt
from .state import SalesPipelineState
from .tools import build_internal_tools



# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

async def build_context_node(state: SalesPipelineState) -> dict:
    brand_id = state["brand_id"]
    task_obj = state["task", {}]
    time_range = task_obj.get("time_range", "last_7_days") if isinstance(task_obj, dict) else "last_7_days"
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, brand_id, time_range=time_range)
    return {"context": context}


async def reasoning_node(state: SalesPipelineState) -> dict:
    brand_id = state["brand_id"]

    shopify_tools = scope_tools_to_brand(await get_shopify_read_tools(), brand_id)
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

    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: SalesPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    model = init_chat_model("google_genai:gemini-3.6-flash")

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: SalesDecision = await model.ainvoke(
        "Based on this analysis, produce the final structured sales decision:\n\n" + transcript
    )

    return {
        "kpis": decision.kpis.model_dump(),
        "insights": [i.model_dump() for i in decision.insights],
        "forecasts": [f.model_dump() for f in decision.forecasts],
        "anomalies": [a.model_dump() for a in decision.anomalies],
        "customer_segments": [c.model_dump() for c in decision.customer_segments],
        "recommendations": decision.recommendations,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: SalesPipelineState) -> dict:
    brand_id = state["brand_id"]
    task_obj = state["task", {}]
    period = task_obj.get("time_range", "last_7_days") if isinstance(task_obj, dict) else "last_7_days"

    kpis = state.get("kpis", {})
    insights = state.get("insights", [])
    forecasts = state.get("forecasts", [])
    anomalies = state.get("anomalies", [])
    customer_segments = state.get("customer_segments", [])
    summary = state.get("summary", "")

    async with AsyncSessionLocal() as session:
        await crud.save_sales_report(session, brand_id, period, summary, kpis)
        if insights:
            await crud.save_sales_insights(session, brand_id, insights)
        if forecasts:
            await crud.save_sales_forecasts(session, brand_id, forecasts)
        if anomalies:
            await crud.save_sales_anomalies(session, brand_id, anomalies)
        if customer_segments:
            await crud.save_customer_segments(session, brand_id, customer_segments)
        if summary:
            await crud.save_agent_memory(session, brand_id, "sales_agent", summary, kind="run_summary")
        await session.commit()

    db_updates = ["sales_reports: +1"]
    if insights:
        db_updates.append(f"sales_insights: +{len(insights)}")
    if forecasts:
        db_updates.append(f"sales_forecasts: +{len(forecasts)}")
    if anomalies:
        db_updates.append(f"sales_anomalies: +{len(anomalies)}")
    if customer_segments:
        db_updates.append(f"customer_segments: upserted {len(customer_segments)}")

    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_sales_graph():
    graph = StateGraph(SalesPipelineState)
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


_sales_graph = None


def get_sales_graph():
    global _sales_graph
    if _sales_graph is None:
        _sales_graph = build_sales_graph()
    return _sales_graph


async def run_sales_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor input, e.g.:
        {"task_type": "analyze_sales", "time_range": "last_7_days",
         "priority": "high", "trigger": "daily_scheduler"}
    or:
        {"task_type": "answer_question", "question": "Why did revenue drop yesterday?",
         "time_range": "yesterday", "trigger": "manual"}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    graph = get_sales_graph()
    initial_state: SalesPipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "sales_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "sales_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "kpis": final_state.get("kpis", {}),
        "insights": final_state.get("insights", []),
        "forecasts": final_state.get("forecasts", []),
        "anomalies": final_state.get("anomalies", []),
        "customer_segments": final_state.get("customer_segments", []),
        "recommendations": final_state.get("recommendations", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }


sales_agent = CompiledSubAgent(
    name="sales_agent",
    description=(
        "Sales & revenue analysis agent. Analyzes daily sales trends, calculates KPIs (AOV, Conversion), "
        "detects revenue anomalies, and segments customer cohorts."
    ),
    runnable=get_sales_graph()
)