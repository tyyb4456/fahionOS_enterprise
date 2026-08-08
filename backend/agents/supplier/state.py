"""
FashionOS Supplier Agent — Pipeline State
============================================
Same shape/spirit as agents/inventory/state.py, agents/sales/state.py,
agents/marketing/state.py, and agents/finance/state.py — "one architecture,
different domain tools" — with Supplier Agent-specific task and output
fields. This agent is the brand's Procurement / Supply Chain Manager: given
a sourcing need (usually from Inventory's reorder recommendations), it
finds and evaluates suppliers, requests/compares quotes, negotiates,
creates purchase orders, tracks shipments, and scores supplier performance.
"""
from typing import Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class SupplierTask(TypedDict, total=False):
    """What the supervisor (or Inventory Agent's reorder recommendations,
    via a scheduler) hands the agent."""
    task_type: Literal[
        "procure_inventory",       # sourcing need for a known SKU/quantity
        "find_supplier",           # discover/rank suppliers for a product
        "track_purchase_order",    # shipment status check on an open PO
        "negotiate",                # renegotiate terms with a supplier
        "evaluate_suppliers",      # periodic scoring/review sweep
    ]
    sku: Optional[str]
    quantity: Optional[int]
    product: Optional[str]         # free-text product description, for find_supplier
    purchase_order_id: Optional[str]
    deadline: Optional[str]        # ISO date — when stock is needed by
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str                   # "daily_scheduler" | "manual" | "inventory_flag" | ...


class SupplierBusinessContext(TypedDict, total=False):
    """Step 1 (+3) output — the snapshot handed to the reasoning loop."""
    sourcing_needs: List[Dict[str, Any]]       # Inventory's pending_approval reorder recs
    open_inventory_alerts: List[Dict[str, Any]]
    suppliers: List[Dict[str, Any]]
    open_purchase_orders: List[Dict[str, Any]]
    recent_quotes: List[Dict[str, Any]]
    recent_negotiations: List[Dict[str, Any]]


class SupplierRecommendationOut(TypedDict, total=False):
    supplier_id: Optional[str]
    supplier_name: str
    score: float
    reason: str


class QuoteComparisonOut(TypedDict, total=False):
    sku: str
    supplier_id: Optional[str]
    supplier_name: str
    unit_price: float
    lead_time_days: int
    moq: int


class PurchaseOrderOut(TypedDict, total=False):
    purchase_order_id: Optional[str]
    sku: str
    supplier_id: Optional[str]
    quantity: int
    unit_cost: Optional[float]
    total_cost: Optional[float]
    expected_delivery: Optional[str]
    status: Literal["created", "pending_approval", "failed"]


class NegotiationPlanOut(TypedDict, total=False):
    supplier_id: Optional[str]
    target_price: Optional[float]
    max_budget: Optional[float]
    strategy: str


class ShipmentUpdateOut(TypedDict, total=False):
    purchase_order_id: str
    status: str
    estimated_arrival: Optional[str]


class SupplierInsightOut(TypedDict, total=False):
    supplier_id: Optional[str]
    category: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float


class SupplierPipelineState(MessagesState, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: SupplierTask

    # ── step 1 + 3: context builder + RAG snapshot ───────────────────────
    context: SupplierBusinessContext

    # ── step 4: tools used ────────────────────────────────────────────────
    tools_used: List[str]

    # ── step 5/6: decision generator output ───────────────────────────────
    supplier_recommendations: List[SupplierRecommendationOut]
    quote_comparisons: List[QuoteComparisonOut]
    purchase_orders: List[PurchaseOrderOut]
    negotiation_plans: List[NegotiationPlanOut]
    shipment_updates: List[ShipmentUpdateOut]
    insights: List[SupplierInsightOut]
    actions_executed: List[str]
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ────────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]