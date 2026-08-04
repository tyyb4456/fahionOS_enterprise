"""
Internal tools for the Sales Agent's ReAct loop — everything that isn't a
live Shopify call (those come from shopify-mcp, see mcp_client.py). Each
factory below binds `brand_id` in a closure so the LLM never has to supply
it — same reasoning as agents/common/tool_scoping.py.
"""
import logging
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from db import crud_sales as crud
from db.session import AsyncSessionLocal

from . import analytics
from . import memory as rag

logger = logging.getLogger(__name__)


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_revenue_kpi_tool(brand_id),
        _make_anomaly_tool(brand_id),
        _make_forecast_tool(brand_id),
        _make_product_performance_tool(brand_id),
        _make_customer_segments_tool(brand_id),
        _make_customer_lookup_tool(brand_id),
        _make_cohort_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
    ]


# ── get_revenue_kpis ──────────────────────────────────────────────────────

class _RevenueKpiArgs(BaseModel):
    time_range: str = Field(
        default="last_7_days",
        description="One of: today, yesterday, last_7_days, last_14_days, last_30_days, last_90_days.",
    )


def _make_revenue_kpi_tool(brand_id: str) -> StructuredTool:
    async def _run(time_range: str = "last_7_days") -> dict:
        async with AsyncSessionLocal() as session:
            return await crud.get_revenue_kpis(session, brand_id, time_range=time_range)

    return StructuredTool.from_function(
        name="get_revenue_kpis",
        description=(
            "Compute revenue, order count, AOV, refund rate, and repeat-customer "
            "rate for a given time range from our database. Use this instead of "
            "eyeballing numbers from the context snapshot."
        ),
        args_schema=_RevenueKpiArgs,
        coroutine=_run,
    )


# ── detect_sales_anomaly ─────────────────────────────────────────────────

class _AnomalyArgs(BaseModel):
    metric: str = Field(default="revenue", description="'revenue' or 'orders'.")
    days: int = Field(default=14, description="Days of history to establish a baseline from.")


def _make_anomaly_tool(brand_id: str) -> StructuredTool:
    async def _run(metric: str = "revenue", days: int = 14) -> dict:
        async with AsyncSessionLocal() as session:
            series = await crud.get_daily_revenue_series(session, brand_id, days=days)
        key = metric if metric in ("revenue", "orders") else "revenue"
        values = [d[key] for d in series]
        result = analytics.detect_anomaly(values, metric=key)
        return result or {"anomaly": False, "metric": key, "message": "No anomaly detected in this window."}

    return StructuredTool.from_function(
        name="detect_sales_anomaly",
        description=(
            "Check whether today's revenue or order count is a statistical outlier "
            "against the recent daily baseline. Use before declaring something "
            "'unusual' — confirm it with numbers first."
        ),
        args_schema=_AnomalyArgs,
        coroutine=_run,
    )


# ── forecast_revenue ──────────────────────────────────────────────────────

class _ForecastArgs(BaseModel):
    history_days: int = Field(default=30, description="Days of daily revenue history to base the forecast on.")
    forecast_days: int = Field(default=7, description="Days to project forward.")


def _make_forecast_tool(brand_id: str) -> StructuredTool:
    async def _run(history_days: int = 30, forecast_days: int = 7) -> dict:
        async with AsyncSessionLocal() as session:
            series = await crud.get_daily_revenue_series(session, brand_id, days=history_days)
        values = [d["revenue"] for d in series]
        return analytics.forecast_revenue(values, forecast_days=forecast_days)

    return StructuredTool.from_function(
        name="forecast_revenue",
        description="Project revenue forward N days from recent daily history. Use this instead of guessing a trend.",
        args_schema=_ForecastArgs,
        coroutine=_run,
    )


# ── get_product_performance (ABC analysis) ───────────────────────────────

class _ProductPerfArgs(BaseModel):
    days: int = Field(default=14, description="Look-back window in days.")
    top_n: int = Field(default=10, description="How many top and worst products to return.")


def _make_product_performance_tool(brand_id: str) -> StructuredTool:
    async def _run(days: int = 14, top_n: int = 10) -> dict:
        async with AsyncSessionLocal() as session:
            return await crud.get_product_performance(session, brand_id, days=days, top_n=top_n)

    return StructuredTool.from_function(
        name="get_product_performance",
        description="Rank products by revenue over a window — best and worst sellers (ABC-style analysis).",
        args_schema=_ProductPerfArgs,
        coroutine=_run,
    )


# ── get_customer_segments ────────────────────────────────────────────────

class _NoArgs(BaseModel):
    pass


def _make_customer_segments_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            customers = await crud.get_customer_segments_data(session, brand_id)
        return analytics.segment_customers(customers)

    return StructuredTool.from_function(
        name="get_customer_segments",
        description=(
            "Segment the brand's customers into VIP / Loyal / New / At Risk / "
            "Inactive buckets based on order recency, frequency, and lifetime spend."
        ),
        args_schema=_NoArgs,
        coroutine=_run,
    )


# ── get_customer_details ─────────────────────────────────────────────────

class _CustomerLookupArgs(BaseModel):
    identifier: str = Field(description="Customer email (fuzzy match) or Shopify customer ID.")


def _make_customer_lookup_tool(brand_id: str) -> StructuredTool:
    async def _run(identifier: str) -> dict:
        async with AsyncSessionLocal() as session:
            customer = await crud.get_customer_by_identifier(session, brand_id, identifier)
        return customer or {"error": f"No customer matching '{identifier}'."}

    return StructuredTool.from_function(
        name="get_customer_details",
        description="Look up a single customer's order history, lifetime value, and location by email or ID.",
        args_schema=_CustomerLookupArgs,
        coroutine=_run,
    )


# ── get_cohort_retention ─────────────────────────────────────────────────

class _CohortArgs(BaseModel):
    months_back: int = Field(default=6, description="How many months of order history to build cohorts from.")


def _make_cohort_tool(brand_id: str) -> StructuredTool:
    async def _run(months_back: int = 6) -> list[dict]:
        async with AsyncSessionLocal() as session:
            orders_by_customer = await crud.get_cohort_orders(session, brand_id, months_back=months_back)
        return analytics.cohort_retention(orders_by_customer)

    return StructuredTool.from_function(
        name="get_cohort_retention",
        description=(
            "Group customers by the month of their first order and report what percent "
            "of each cohort returned to buy again in the following months."
        ),
        args_schema=_CohortArgs,
        coroutine=_run,
    )


# ── retrieve_policy (RAG) ────────────────────────────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'minimum gross margin policy'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description=(
            "Search brand-specific business documents (pricing strategy, sales SOP, "
            "promotion policy, target KPIs) for guidance relevant to your query."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )


# ── search_agent_memory ──────────────────────────────────────────────────

def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description=(
            "Search notes this agent kept from previous runs (e.g. past campaign "
            "results, prior anomalies and their causes) for anything relevant now."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )