"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SupplierRecommendationItem(BaseModel):
    supplier_id: Optional[str] = None
    supplier_name: str
    score: float = Field(ge=0, le=100, default=50)
    reason: str = ""


class QuoteComparisonItem(BaseModel):
    sku: str
    supplier_id: Optional[str] = None
    supplier_name: str = ""
    unit_price: float = 0
    lead_time_days: int = 0
    moq: int = 0


class PurchaseOrderItem(BaseModel):
    purchase_order_id: Optional[str] = None
    sku: str
    supplier_id: Optional[str] = None
    supplier_name: str = ""
    quantity: int = 0
    unit_cost: Optional[float] = None
    total_cost: Optional[float] = None
    expected_delivery: Optional[str] = None
    status: Literal["created", "pending_approval", "failed"] = "pending_approval"


class NegotiationPlanItem(BaseModel):
    supplier_id: Optional[str] = None
    supplier_name: str = ""
    target_price: Optional[float] = None
    max_budget: Optional[float] = None
    strategy: str = ""


class ShipmentUpdateItem(BaseModel):
    purchase_order_id: str
    status: str
    estimated_arrival: Optional[str] = None
    note: str = ""


class SupplierInsightItem(BaseModel):
    supplier_id: Optional[str] = None
    category: Literal["pricing", "quality", "reliability", "risk", "opportunity", "performance"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float = Field(ge=0, le=1, default=0.6)


class SupplierDecision(BaseModel):
    """The final structured output — mirrors the design doc's 'What It
    Returns to Supervisor' shape."""
    summary: str
    supplier_recommendations: List[SupplierRecommendationItem] = []
    quote_comparisons: List[QuoteComparisonItem] = []
    purchase_orders: List[PurchaseOrderItem] = []
    negotiation_plans: List[NegotiationPlanItem] = []
    shipment_updates: List[ShipmentUpdateItem] = []
    insights: List[SupplierInsightItem] = []
    actions_executed: List[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []