"""
FashionOS Product / Merchandising Agent — Pipeline State
============================================================
Same shape/spirit as agents/inventory/state.py, agents/sales/state.py,
agents/marketing/state.py, agents/finance/state.py, agents/research/state.py,
and agents/supplier/state.py — "one architecture, different domain tools" —
with Product Agent-specific task and output fields.
"""
from typing import Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class ProductTask(TypedDict, total=False):
    """What the supervisor (or a scheduler, or another agent's next_actions
    routed through the supervisor — e.g. Research flagging a trend) hands
    the agent."""
    task_type: Literal[
        "create_product_opportunity",
        "plan_next_collection",
        "evaluate_variant_performance",
        "product_lifecycle_review",
        "launch_product",
    ]
    category: Optional[str]        # e.g. "oversized hoodies"
    target: Optional[str]          # e.g. "Gen Z"
    region: Optional[str]          # e.g. "Pakistan"
    season: Optional[str]          # e.g. "winter"
    budget: Optional[float]
    product_ref: Optional[str]     # narrow to one product (title or SKU), for lifecycle/variant tasks
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str                   # "daily_scheduler" | "manual" | "webhook:..." | ...


class ProductBusinessContext(TypedDict, total=False):
    """Step 1 output — the snapshot handed to the reasoning loop."""
    catalog: List[Dict[str, Any]]
    variant_sales_breakdown: List[Dict[str, Any]]
    inventory_signals: List[Dict[str, Any]]
    research_opportunities: List[Dict[str, Any]]
    market_trends: List[Dict[str, Any]]
    competitor_analysis: List[Dict[str, Any]]
    marketing_insights: List[Dict[str, Any]]
    active_campaigns: List[Dict[str, Any]]
    margin_snapshot: Dict[str, Any]
    supplier_snapshot: List[Dict[str, Any]]
    previous_proposals: List[Dict[str, Any]]
    previous_collections: List[Dict[str, Any]]
    product_lifecycle_snapshot: List[Dict[str, Any]]


class ProductProposalOut(TypedDict, total=False):
    product_name: str
    category: str
    description: str
    variants: List[str]
    sizes: List[str]
    target_price: Optional[float]
    market_demand: float
    brand_fit: float
    competition: float
    supplier_feasibility: float
    expected_margin: Optional[float]
    recommended_initial_quantity: Optional[int]
    status: Literal["proposed", "approved", "rejected", "in_development", "launched"]
    reason: str


class CollectionOut(TypedDict, total=False):
    name: str
    season: str
    theme: str
    product_names: List[str]
    launch_date: Optional[str]
    status: Literal["planning", "active", "archived"]


class LifecycleUpdateOut(TypedDict, total=False):
    product_ref: str
    stage: str
    performance_score: Optional[float]
    notes: str


class MerchandisingInsightOut(TypedDict, total=False):
    category: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float


class ProductPipelineState(MessagesState, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: ProductTask

    # ── step 1: context builder ─────────────────────────────────────────
    context: ProductBusinessContext

    # ── step 4: tools used ───────────────────────────────────────────────
    tools_used: List[str]

    # ── step 5/6: decision generator output ─────────────────────────────
    proposals: List[ProductProposalOut]
    collections: List[CollectionOut]
    lifecycle_updates: List[LifecycleUpdateOut]
    insights: List[MerchandisingInsightOut]
    actions_executed: List[str]
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ───────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]