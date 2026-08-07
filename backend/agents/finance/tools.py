"""
Internal tools for the Finance Agent's ReAct loop — everything that isn't
a live Shopify/Meta read (those come from shopify-mcp / meta-mcp, see
mcp_client.py). Each factory below binds `brand_id` in a closure so the
LLM never has to supply it — same reasoning as agents/common/tool_scoping.py.

Three flavors of tool live here:
  - lookups (read our own tables + other agents' outputs — profit,
    expenses, inventory valuation, PO costs, margin data, Sales/Inventory/
    Marketing signals)
  - deterministic helpers (agents/finance/analytics.py — profit math,
    cashflow projection, margin ranking, ROI, purchase-order affordability:
    things that should be computed, not guessed by the LLM)
  - operational writes (record_expense, create_budget_recommendation,
    assess_financial_risk, notify_brand_owner) — these change real state
    immediately, mid-loop, the same way Inventory's create_purchase_order
    does, rather than waiting for persist_node.

evaluate_purchase_order is deliberately NOT a write — Finance doesn't own
purchase_orders (Inventory does) and never flips its status; it only
returns an affordability recommendation. See agents/finance/prompt.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.common.notify_tools import make_notify_brand_owner_tool
from db import crud_finance as crud
from db.session import AsyncSessionLocal

from . import analytics
from . import memory as rag

logger = logging.getLogger(__name__)


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_profit_report_tool(brand_id),
        _make_expense_breakdown_tool(brand_id),
        _make_inventory_valuation_tool(brand_id),
        _make_cashflow_forecast_tool(brand_id),
        _make_margin_tool(brand_id),
        _make_roi_tool(brand_id),
        _make_evaluate_po_tool(brand_id),
        _make_sales_insights_tool(brand_id),
        _make_inventory_alerts_tool(brand_id),
        _make_marketing_insights_tool(brand_id),
        _make_record_expense_tool(brand_id),
        _make_budget_recommendation_tool(brand_id),
        _make_risk_assessment_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
        make_notify_brand_owner_tool(brand_id, agent_name="Finance Agent"),
    ]


# ── get_profit_report ─────────────────────────────────────────────────────

class _TimeRangeArgs(BaseModel):
    time_range: str = Field(
        default="last_30_days",
        description="One of: today, yesterday, last_7_days, last_14_days, last_30_days, last_90_days.",
    )


def _make_profit_report_tool(brand_id: str) -> StructuredTool:
    async def _run(time_range: str = "last_30_days") -> dict:
        async with AsyncSessionLocal() as session:
            return await crud.get_profit_report(session, brand_id, time_range=time_range)

    return StructuredTool.from_function(
        name="get_profit_report",
        description=(
            "Compute revenue, expenses, refunds, profit, and margin % for a time range "
            "from our database. Use this instead of eyeballing numbers from the context snapshot."
        ),
        args_schema=_TimeRangeArgs,
        coroutine=_run,
    )


# ── get_expense_breakdown ─────────────────────────────────────────────────

class _DaysArgs(BaseModel):
    days: int = Field(default=30, description="Look-back window in days.")


def _make_expense_breakdown_tool(brand_id: str) -> StructuredTool:
    async def _run(days: int = 30) -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_expense_breakdown(session, brand_id, days=days)

    return StructuredTool.from_function(
        name="get_expense_breakdown",
        description="This brand's own recorded expenses over a window, grouped and totaled by category.",
        args_schema=_DaysArgs,
        coroutine=_run,
    )


# ── get_inventory_valuation ───────────────────────────────────────────────

class _NoArgs(BaseModel):
    pass


def _make_inventory_valuation_tool(brand_id: str) -> StructuredTool:
    async def _run() -> dict:
        async with AsyncSessionLocal() as session:
            return await crud.get_inventory_valuation(session, brand_id)

    return StructuredTool.from_function(
        name="get_inventory_valuation",
        description=(
            "Current inventory value (units on hand x cost_price) across active products, plus "
            "a count of variants missing cost_price data (their value can't be counted)."
        ),
        args_schema=_NoArgs,
        coroutine=_run,
    )


# ── forecast_cashflow ─────────────────────────────────────────────────────

class _CashflowArgs(BaseModel):
    history_days: int = Field(default=30, description="Days of daily net-cash-flow history to base the forecast on.")
    forecast_days: int = Field(default=30, description="Days to project forward.")


def _make_cashflow_forecast_tool(brand_id: str) -> StructuredTool:
    async def _run(history_days: int = 30, forecast_days: int = 30) -> dict:
        async with AsyncSessionLocal() as session:
            current_cash, series = await crud.get_cash_position_and_series(session, brand_id, days=history_days)
        result = analytics.forecast_cashflow(current_cash, series, forecast_days=forecast_days)
        result["forecast_days"] = forecast_days
        return result

    return StructuredTool.from_function(
        name="forecast_cashflow",
        description=(
            "Project cash position forward N days from recent daily net cash flow (revenue minus "
            "expenses minus refunds). Note: 'cash' here is a proxy from order/expense history, not a "
            "real bank balance — this environment has no bank/Stripe integration. Use this instead of "
            "guessing a trend yourself."
        ),
        args_schema=_CashflowArgs,
        coroutine=_run,
    )


# ── calculate_product_margins ─────────────────────────────────────────────

class _MarginArgs(BaseModel):
    top_n: int = Field(default=10, description="How many best/worst-margin products to return.")


def _make_margin_tool(brand_id: str) -> StructuredTool:
    async def _run(top_n: int = 10) -> dict:
        async with AsyncSessionLocal() as session:
            variants = await crud.get_variant_costs_and_prices(session, brand_id)
        return analytics.rank_products_by_margin(variants, top_n=top_n)

    return StructuredTool.from_function(
        name="calculate_product_margins",
        description=(
            "Rank active products by real gross margin (selling price vs cost_price) — best and worst. "
            "Also flags variants with no cost_price on file, whose margin can't be computed. Use this "
            "instead of assuming a bestseller is profitable."
        ),
        args_schema=_MarginArgs,
        coroutine=_run,
    )


# ── calculate_roi ─────────────────────────────────────────────────────────

class _RoiArgs(BaseModel):
    spend: float = Field(description="Amount spent, e.g. ad spend from get_ad_account_summary.")
    revenue: float = Field(description="Revenue attributed to that spend.")


def _make_roi_tool(brand_id: str) -> StructuredTool:
    async def _run(spend: float, revenue: float) -> dict:
        return analytics.calculate_roi(spend, revenue)

    return StructuredTool.from_function(
        name="calculate_roi",
        description="Compute ROI % given a spend amount and the revenue attributed to it — e.g. from get_ad_account_summary and get_profit_report.",
        args_schema=_RoiArgs,
        coroutine=_run,
    )


# ── evaluate_purchase_order (advisory — never writes) ────────────────────

class _EvaluatePOArgs(BaseModel):
    purchase_order_id: str = Field(description="The purchase_order_id to evaluate (from the task, or from open_purchase_order_costs in context).")


def _make_evaluate_po_tool(brand_id: str) -> StructuredTool:
    async def _run(purchase_order_id: str) -> dict:
        async with AsyncSessionLocal() as session:
            po = await crud.get_purchase_order_cost(session, brand_id, purchase_order_id)
            if not po:
                return {"error": f"No purchase order '{purchase_order_id}' found for this brand."}
            current_cash, _series = await crud.get_cash_position_and_series(session, brand_id, days=30)
        return analytics.evaluate_purchase_order(po, current_cash)

    return StructuredTool.from_function(
        name="evaluate_purchase_order",
        description=(
            "Check whether the brand can safely afford a specific Inventory purchase order right now — "
            "compares its total cost against current cash position and a safety buffer. Returns an "
            "approved/denied recommendation with reasoning and conditions. Advisory only: this never "
            "changes the purchase order's status — Finance doesn't own that table."
        ),
        args_schema=_EvaluatePOArgs,
        coroutine=_run,
    )


# ── cross-agent lookups (deeper reads than the context snapshot) ─────────

def _make_sales_insights_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_sales_insights(session, brand_id, limit=20)

    return StructuredTool.from_function(
        name="get_sales_insights",
        description="Read the Sales Agent's recent insights (best/worst sellers, anomalies, opportunities) — don't recompute this yourself.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_inventory_alerts_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_inventory_alerts(session, brand_id, limit=20)

    return StructuredTool.from_function(
        name="get_inventory_alerts",
        description="Read the Inventory Agent's open alerts (stockout risk, overstock, etc.) — relevant to purchase-order affordability and dead-stock risk.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_marketing_insights_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_marketing_insights(session, brand_id, limit=20)

    return StructuredTool.from_function(
        name="get_marketing_insights",
        description="Read the Marketing Agent's recent insights — useful context before recommending a marketing budget change.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


# ── record_expense (operational write) ────────────────────────────────────

class _RecordExpenseArgs(BaseModel):
    category: str = Field(description="'marketing' | 'shipping' | 'software' | 'salaries' | 'warehouse' | 'utilities' | 'packaging' | 'other'.")
    amount: float = Field(description="Amount in the store's currency.")
    description: str = Field(default="", description="What this expense is for.")
    incurred_at: Optional[str] = Field(default=None, description="ISO8601 date this was incurred. Defaults to now.")
    recurring: bool = Field(default=False, description="Whether this is a recurring cost (e.g. monthly software subscription).")


def _make_record_expense_tool(brand_id: str) -> StructuredTool:
    async def _run(category: str, amount: float, description: str = "", incurred_at: Optional[str] = None, recurring: bool = False) -> dict:
        if incurred_at:
            try:
                when = datetime.fromisoformat(incurred_at.replace("Z", "+00:00"))
            except ValueError:
                return {"error": f"Couldn't parse incurred_at='{incurred_at}' as ISO8601."}
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        else:
            when = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            result = await crud.record_expense(session, brand_id, category, description, amount, when, recurring)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="record_expense",
        description=(
            "Log a real, confirmed expense to the books (e.g. an ad spend you just read from "
            "get_ad_account_summary, a supplier invoice) so future profit/cashflow numbers account for "
            "it. Not for projections or estimates — only confirmed costs."
        ),
        args_schema=_RecordExpenseArgs,
        coroutine=_run,
    )


# ── create_budget_recommendation (operational write) ──────────────────────

class _BudgetRecArgs(BaseModel):
    department: str = Field(description="'marketing' | 'inventory' | 'operations' | or another department name.")
    recommended_budget: float = Field(description="The budget you're recommending.")
    reason: str = Field(description="Why — tie this to a specific KPI, policy, or forecast.")
    current_budget: Optional[float] = Field(default=None, description="The department's current budget, if known.")


def _make_budget_recommendation_tool(brand_id: str) -> StructuredTool:
    async def _run(department: str, recommended_budget: float, reason: str, current_budget: Optional[float] = None) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.create_budget_recommendation(session, brand_id, department, current_budget, recommended_budget, reason)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="create_budget_recommendation",
        description=(
            "Issue a real budget recommendation for a department — visible immediately on the dashboard. "
            "Only call this once you can name a specific reason (a KPI, a policy, a forecast) behind the number."
        ),
        args_schema=_BudgetRecArgs,
        coroutine=_run,
    )


# ── assess_financial_risk (operational write) ──────────────────────────────

class _RiskArgs(BaseModel):
    risk: str = Field(description="What the risk is, plainly stated.")
    severity: str = Field(default="medium", description="'low' | 'medium' | 'high' | 'critical'.")
    recommendation: str = Field(default="", description="What should be done about it.")
    related_amount: Optional[float] = Field(default=None, description="A dollar amount tied to this risk, if relevant (e.g. the shortfall).")


def _make_risk_assessment_tool(brand_id: str) -> StructuredTool:
    async def _run(risk: str, severity: str = "medium", recommendation: str = "", related_amount: Optional[float] = None) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.create_risk_assessment(session, brand_id, risk, severity, recommendation, related_amount)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="assess_financial_risk",
        description=(
            "Flag a real financial risk (e.g. a looming cash shortfall, an unsustainable expense trend) "
            "so it's visible on the dashboard. Pair critical/high severity risks with notify_brand_owner "
            "so they don't sit unseen."
        ),
        args_schema=_RiskArgs,
        coroutine=_run,
    )


# ── retrieve_policy / search_agent_memory (RAG) ────────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'advertising spend cap policy'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description=(
            "Search brand-specific financial documents (accounting policy, budget policy, tax rules, "
            "financial SOP, investment rules) for guidance relevant to your query."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )


def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description="Search notes this agent kept from previous runs (e.g. past cash-flow patterns, prior risk calls) for anything relevant now.",
        args_schema=_QueryArgs,
        coroutine=_run,
    )