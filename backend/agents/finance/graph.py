"""
Finance Agent — LangGraph pipeline.

Same shape as agents/inventory/graph.py, agents/sales/graph.py, and
agents/marketing/graph.py:
    build_context   (Step 1 — read Postgres: profit/expense summary,
                      inventory valuation, open PO costs, + Sales/
                      Inventory/Marketing agents' outputs)
        -> reason           (Steps 2-4 — ReAct loop; tools = live Shopify/
                              Meta read-only data via shopify-mcp + meta-mcp,
                              plus internal profit/cashflow/margin/ROI/
                              purchase-order-affordability tools, all
                              called on demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured FinancialDecision)
        -> persist          (Step 7 — write the financial report/cashflow
                              forecast/insights + execution log + memory)

RAG note: same as the other three agents — retrieval is NOT a forced
pre-fetch node. It's the retrieve_policy / search_agent_memory tools in
agents/finance/tools.py, backed by agents/finance/memory.py's Chroma
collections, called only when the ReAct loop decides it needs policy or
past-run context.

Operational note: record_expense, create_budget_recommendation, and
assess_financial_risk write real rows mid-loop (same pattern as
Inventory's create_purchase_order / Marketing's schedule_content) rather
than waiting for persist_node. evaluate_purchase_order is deliberately
read-only/advisory — Finance doesn't own purchase_orders and won't flip
its status; see agents/finance/prompt.py.
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
from langchain.agents import create_agent
from langchain_mistralai import ChatMistralAI
from langchain.chat_models import init_chat_model

from agents.common.tool_scoping import scope_tools_to_brand
from db import crud_finance as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_finance_tools
from .output_schema import FinancialDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .state import FinancePipelineState
from .tools import build_internal_tools


# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

def _time_range_from_task(task_obj: Any) -> str:
    if isinstance(task_obj, dict):
        return task_obj.get("time_range") or task_obj.get("period") or "last_30_days"
    return "last_30_days"


async def build_context_node(state: FinancePipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[FinanceAgent] Building business context for brand_id=%s", brand_id)
    time_range = _time_range_from_task(state.get("task", {}))
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, brand_id, time_range=time_range)
    return {"context": context}


async def reasoning_node(state: FinancePipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[FinanceAgent] Running reasoning node for brand_id=%s", brand_id)

    live_tools = scope_tools_to_brand(await get_finance_tools(), brand_id)
    internal_tools = build_internal_tools(brand_id)
    tools = [*live_tools, *internal_tools]

    model = ChatMistralAI(
        model="mistral-medium-3-5",
        temperature=0,
        model_kwargs={"reasoning_effort": "high"},
    )

    agent = create_agent(model, tools)

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

    logger.info("[FinanceAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: FinancePipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[FinanceAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(FinancialDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: FinancialDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "financial decision. In actions_executed, list only things that actually happened "
        "(a tool call succeeded) — not things merely proposed:\n\n" + transcript
    )

    logger.info("[FinanceAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    return {
        "profit_report": decision.profit_report.model_dump(),
        "cashflow_forecast": decision.cashflow_forecast.model_dump() if decision.cashflow_forecast else None,
        "insights": [i.model_dump() for i in decision.insights],
        "purchase_order_evaluation": decision.purchase_order_evaluation.model_dump() if decision.purchase_order_evaluation else None,
        "actions_executed": decision.actions_executed,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: FinancePipelineState) -> dict:
    brand_id = state["brand_id"]
    period = _time_range_from_task(state.get("task", {}))

    profit_report = state.get("profit_report", {})
    cashflow_forecast = state.get("cashflow_forecast")
    insights = state.get("insights", [])
    summary = state.get("summary", "")

    logger.info("[FinanceAgent] Persisting outputs for brand_id=%s (insights=%d, has_forecast=%s)", brand_id, len(insights), bool(cashflow_forecast))
    async with AsyncSessionLocal() as session:
        await crud.save_financial_report(
            session, brand_id, period, summary,
            revenue=profit_report.get("revenue", 0.0), expenses=profit_report.get("expenses", 0.0),
            profit=profit_report.get("profit", 0.0), margin=profit_report.get("margin_pct", 0.0),
            kpis=profit_report,
        )
        if cashflow_forecast:
            await crud.save_cashflow_forecast(session, brand_id, cashflow_forecast, cashflow_forecast.get("forecast_days", 30))
        if insights:
            await crud.save_financial_insights(session, brand_id, insights)
        if summary:
            await crud.save_agent_memory(session, brand_id, "finance_agent", summary, kind="run_summary")
        await session.commit()

    db_updates = ["financial_reports: +1"]
    if cashflow_forecast:
        db_updates.append("financial_forecasts: +1")
    if insights:
        db_updates.append(f"financial_insights: +{len(insights)}")

    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_finance_graph():
    graph = StateGraph(FinancePipelineState)
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


_finance_graph = None


def get_finance_graph():
    global _finance_graph
    if _finance_graph is None:
        _finance_graph = build_finance_graph()
    return _finance_graph


async def run_finance_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor input, e.g.:
        {"task_type": "financial_analysis", "time_range": "last_30_days"}
    or:
        {"task_type": "evaluate_purchase_order", "purchase_order_id": "..."}
    or:
        {"task_type": "cashflow_forecast", "forecast_days": 90}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    logger.info("[FinanceAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
    graph = get_finance_graph()
    initial_state: FinancePipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("[FinanceAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "finance_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[FinanceAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "finance_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "profit_report": final_state.get("profit_report", {}),
        "cashflow_forecast": final_state.get("cashflow_forecast"),
        "insights": final_state.get("insights", []),
        "purchase_order_evaluation": final_state.get("purchase_order_evaluation"),
        "actions_executed": final_state.get("actions_executed", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



finance_agent = CompiledSubAgent(
    name="finance_agent",
    description=(
        "Finance agent — the brand's Chief Financial Officer. Computes profit/margin from real revenue, "
        "expenses, and refunds, forecasts cash position, ranks products by actual margin (price vs cost), "
        "computes ROI on ad spend, and checks whether a specific Inventory purchase order is affordable "
        "right now. Reads the Sales, Inventory, and Marketing agents' outputs instead of recomputing them. "
        "OPERATIONAL: it can log real expenses to the books, issue budget recommendations, and flag "
        "financial risks — visible immediately on the dashboard — and can alert the brand owner. It does "
        "NOT place purchase orders, launch campaigns, or change another agent's data itself; its "
        "purchase-order evaluation is advisory. "
        "Delegate for anything about profit, margin, cash position, budget, expenses, ROI, or whether the "
        "brand can afford a specific spend (financial_analysis, evaluate_purchase_order, cashflow_forecast, "
        "budget_review, expense_analysis). Include the relevant time range, purchase_order_id, or "
        "forecast_days in the task description when relevant."
    ),
    runnable=get_finance_graph()
)