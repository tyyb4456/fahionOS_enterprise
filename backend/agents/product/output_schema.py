"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProductProposalItem(BaseModel):
    product_name: str
    category: str = ""
    description: str = ""
    variants: List[str] = []
    sizes: List[str] = []
    target_price: Optional[float] = None
    market_demand: float = Field(ge=0, le=1, default=0.5)
    brand_fit: float = Field(ge=0, le=1, default=0.5)
    competition: float = Field(ge=0, le=1, default=0.5)
    supplier_feasibility: float = Field(ge=0, le=1, default=0.5)
    expected_margin: Optional[float] = None
    expected_demand_score: float = Field(ge=0, le=1, default=0.5)  # composite_score from score_product_opportunity
    recommended_initial_quantity: Optional[int] = None
    status: Literal["proposed", "approved", "rejected", "in_development", "launched"] = "proposed"
    reason: str = ""


class CollectionItem(BaseModel):
    name: str
    season: str = ""
    theme: str = ""
    product_names: List[str] = []
    launch_date: Optional[str] = None
    status: Literal["planning", "active", "archived"] = "planning"


class LifecycleUpdateItem(BaseModel):
    product_ref: str
    stage: Literal[
        "idea", "proposal", "approved", "development", "sampling", "production",
        "ready", "launch", "growth", "mature", "declining", "clearance", "archived",
    ]
    performance_score: Optional[float] = None
    notes: str = ""


class MerchandisingInsightItem(BaseModel):
    category: Literal["variant_performance", "pricing", "lifecycle", "collection", "customer_feedback", "opportunity"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float = Field(ge=0, le=1, default=0.6)


class ProductDecision(BaseModel):
    """The final structured output — mirrors the design doc's 'What It
    Returns to Supervisor' shape."""
    summary: str
    proposals: List[ProductProposalItem] = []
    collections: List[CollectionItem] = []
    lifecycle_updates: List[LifecycleUpdateItem] = []
    insights: List[MerchandisingInsightItem] = []
    actions_executed: List[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []