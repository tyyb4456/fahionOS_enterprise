"""
FashionOS Sales Agent — Pipeline State
=========================================
Same shape/spirit as state.py (PipelineState) — "one architecture, different
domain tools" — but with Sales Agent-specific task and output fields instead
of Inventory's.
"""
from typing import Any, Dict, List, Optional, Annotated, Literal
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


class SalesTask(TypedDict, total=False):
    """What the supervisor (or a scheduler/webhook) hands the agent."""
    task_type: Literal[
        "analyze_sales",
        "answer_question",
        "revenue_report",
        "customer_segmentation",
        "forecast_revenue",
    ]
    time_range: Literal["today", "yesterday", "last_7_days", "last_14_days", "last_30_days", "last_90_days"]
    question: Optional[str]     # for task_type == "answer_question"
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str                 # "daily_scheduler" | "manual" | "webhook:orders/paid" | ...


class SalesBusinessContext(TypedDict, total=False):
    """Step 1 (+3) output — the snapshot handed to the reasoning loop."""
    revenue_summary: Dict[str, Any]
    top_products: List[Dict[str, Any]]
    worst_products: List[Dict[str, Any]]
    returns_summary: Dict[str, Any]
    customer_summary: Dict[str, Any]
    discount_summary: List[Dict[str, Any]]
    daily_revenue_series: List[Dict[str, Any]]


class KpiReportOut(TypedDict, total=False):
    revenue: float
    orders: int
    average_order_value: float
    refund_rate: float
    repeat_customer_rate: float


class InsightOut(TypedDict, total=False):
    category: str            # "revenue" | "product" | "customer" | "channel" | "opportunity" | "risk"
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float


class ForecastOut(TypedDict, total=False):
    forecast_date: str
    predicted_revenue: float
    predicted_orders: int
    confidence: float


class AnomalyOut(TypedDict, total=False):
    metric: str
    expected: float
    actual: float
    severity: Literal["low", "medium", "high", "critical"]
    message: str


class CustomerSegmentOut(TypedDict, total=False):
    segment: str              # "VIP" | "New" | "At Risk" | "Loyal" | "Inactive"
    customer_count: int
    definition: str
    customer_ids: List[str]


class SalesPipelineState(TypedDict, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: SalesTask

    # ── step 1 + 3: context builder + RAG snapshot ───────────────────────
    context: SalesBusinessContext

    # ── step 4: ReAct loop transcript (LangGraph message state) ──────────
    messages: Annotated[List[Any], add_messages]
    tools_used: List[str]

    # ── step 5/6: decision generator output ───────────────────────────────
    kpis: KpiReportOut
    insights: List[InsightOut]
    forecasts: List[ForecastOut]
    anomalies: List[AnomalyOut]
    customer_segments: List[CustomerSegmentOut]
    recommendations: List[str]
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ──────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ────────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]