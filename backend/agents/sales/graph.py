"""
Sales Agent — LangGraph pipeline.

Same shape as agents/inventory/graph.py:
    build_context   (Step 1 — read Postgres: revenue, products, returns,
                      customers, discounts, daily revenue series)
        -> reason           (Steps 2-4 — ReAct loop; tools = live Shopify
                              data via shopify-mcp + revenue/KPI/anomaly/
                              forecast math + customer segmentation/cohort +
                              RAG + real actions (create_discount_code,
                              flag_inventory_issue), all called on demand)
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

Operational note: create_discount_code (a real Shopify write, via
shopify-mcp) and flag_inventory_issue (a real cross-agent DB write) make
this agent operational rather than purely advisory — see
agents/sales/prompts.py.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from deepagents import CompiledSubAgent, create_deep_agent
from langchain.agents import create_agent
from langchain_mistralai import ChatMistralAI
from langchain.chat_models import init_chat_model

from agents.common.progress import AnnounceToolCalls, progress as emit_progress
from agents.common.task_input import resolve_task_input
from agents.common.tool_scoping import scope_tools_to_brand
from db import crud_sales as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_shopify_tools
from .output_schema import SalesDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .state import SalesPipelineState
from .tools import build_internal_tools

from dotenv import load_dotenv
load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

async def build_context_node(state: SalesPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[SalesAgent] Building business context for brand_id=%s", brand_id)
    emit_progress("build_context", "started", "Building business context")
    task_obj = state.get("task", {})
    time_range = task_obj.get("time_range", "last_7_days") if isinstance(task_obj, dict) else "last_7_days"
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, brand_id, time_range=time_range)
    emit_progress("build_context", "done", "Business context ready")
    return {"context": context}


async def reasoning_node(state: SalesPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[SalesAgent] Running reasoning node for brand_id=%s", brand_id)
    emit_progress("reason", "started", "Running analysis — calling tools as needed")

    shopify_tools = scope_tools_to_brand(await get_shopify_tools(), brand_id)
    internal_tools = build_internal_tools(brand_id)
    tools = [*shopify_tools, *internal_tools]

    model = ChatMistralAI(
        model="mistral-medium-3-5",
        temperature=0,
        model_kwargs={"reasoning_effort": "high"},
    )

    agent = create_agent(model, tools, middleware=[AnnounceToolCalls()])

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
    logger.info("[SalesAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: SalesPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[SalesAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    emit_progress("extract_decision", "started", "Extracting structured decision")
    
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(SalesDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: SalesDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "sales decision. In actions_executed, list only things that actually happened "
        "(a tool call succeeded) — not things merely proposed:\n\n" + transcript
    )

    logger.info("[SalesAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    emit_progress("extract_decision", "done", "Decision extracted")
    return {
        "kpis": decision.kpis.model_dump(),
        "insights": [i.model_dump() for i in decision.insights],
        "forecasts": [f.model_dump() for f in decision.forecasts],
        "anomalies": [a.model_dump() for a in decision.anomalies],
        "customer_segments": [c.model_dump() for c in decision.customer_segments],
        "recommendations": decision.recommendations,
        "actions_executed": decision.actions_executed,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: SalesPipelineState) -> dict:
    brand_id = state["brand_id"]
    task_obj = state.get("task", {})
    period = task_obj.get("time_range", "last_7_days") if isinstance(task_obj, dict) else "last_7_days"

    kpis = state.get("kpis", {})
    insights = state.get("insights", [])
    forecasts = state.get("forecasts", [])
    anomalies = state.get("anomalies", [])
    customer_segments = state.get("customer_segments", [])
    summary = state.get("summary", "")

    logger.info("[SalesAgent] Persisting outputs for brand_id=%s (insights=%d, forecasts=%d, anomalies=%d, segments=%d)", brand_id, len(insights), len(forecasts), len(anomalies), len(customer_segments))
    emit_progress("persist", "started", "Persisting results")
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

    emit_progress("persist", "done", "Results saved")
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
    logger.info("[SalesAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
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
        logger.exception("[SalesAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "sales_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[SalesAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
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
        "actions_executed": final_state.get("actions_executed", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



sales_agent = CompiledSubAgent(
    name="sales_agent",
    description=(
        "Sales & revenue intelligence agent — the brand's Chief Revenue Officer. Analyzes daily sales trends and "
        "KPIs (revenue, orders, AOV, refund rate, repeat-customer rate), detects statistically-confirmed revenue/order "
        "anomalies, forecasts revenue, ranks products (best/worst sellers, ABC analysis), segments customers "
        "(VIP/Loyal/New/At Risk/Inactive), computes cohort retention, and looks up individual customer history. "
        "Root-causes revenue changes (stockouts, refund spikes, discount overreach, ended campaigns) and answers "
        "ad-hoc revenue questions. "
        "OPERATIONAL: it can create real Shopify discount codes, flag inventory issues straight into the Inventory "
        "agent's alert feed, and alert the brand owner — it acts, it doesn't just report. "
        "Delegate for anything about sales performance, revenue, KPIs, anomalies, forecasts, customer segments, or a "
        "revenue drop/question (analyze_sales, answer_question, revenue_report, customer_segmentation, "
        "forecast_revenue). Include the question or objective in the task description, plus a time range when relevant."
    ),
    runnable=get_sales_graph()
)