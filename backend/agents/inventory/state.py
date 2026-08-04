"""
FashionOS Pipeline State
==========================
Shared state schema for LangGraph agent pipelines. The Inventory Agent
(agents/inventory/graph.py) is the current consumer; other agents (Sales,
Marketing, Finance, Customer Support, Supplier...) are meant to reuse this
same shape per the "one architecture, different domain tools" pattern —
only `task`, the tool set, and the output fields change per agent.
"""
from typing import Any, Dict, List, Optional, Annotated, Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class InventoryTask(TypedDict, total=False):
    """What the supervisor (or a scheduler/webhook) hands the agent."""
    task_type: Literal[
        "forecast_inventory",
        "check_stockouts",
        "reorder_analysis",
        "overstock_analysis",
        "full_inventory_review",
    ]
    forecast_days: int
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str            # "daily_scheduler" | "manual" | "webhook:orders/paid" | ...
    sku: Optional[str]      # narrow the task to a single SKU, if set


class BusinessContext(TypedDict, total=False):
    """Step 1 (+3) output — the snapshot handed to the reasoning loop."""
    products: List[Dict[str, Any]]
    sales_summary: List[Dict[str, Any]]
    open_purchase_orders: List[Dict[str, Any]]
    suppliers: List[Dict[str, Any]]
    warehouses: List[Dict[str, Any]]
    upcoming_seasonal_events: List[Dict[str, Any]]


class ForecastOut(TypedDict, total=False):
    sku: str
    product_title: str
    forecast_days: int
    days_until_stockout: Optional[float]
    predicted_units_sold: float
    predicted_stock_remaining: float
    confidence: float


class RecommendationOut(TypedDict, total=False):
    sku: str
    supplier_id: Optional[str]
    supplier_name: Optional[str]
    quantity: int
    urgency: Literal["critical", "high", "normal"]
    reason: str
    supplier_message: str


class AlertOut(TypedDict, total=False):
    type: str
    severity: Literal["low", "medium", "high", "critical"]
    sku: Optional[str]
    message: str


class InventoryPipelineState(MessagesState, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: InventoryTask

    # ── step 1 + 3: context builder + RAG snapshot ───────────────────────
    context: BusinessContext

    # ── step 4: tool used ────────────────────────────────────────────
    tools_used: List[str]

    # ── step 5/6: decision generator output ───────────────────────────────
    forecasts: List[ForecastOut]
    recommendations: List[RecommendationOut]
    alerts: List[AlertOut]
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ──────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ────────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]