"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ForecastItem(BaseModel):
    sku: str
    product_title: str = ""
    forecast_days: int = 30
    days_until_stockout: Optional[float] = None
    predicted_units_sold: float = 0
    predicted_stock_remaining: float = 0
    confidence: float = Field(ge=0, le=1, default=0.5)


class RecommendationItem(BaseModel):
    sku: str
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    quantity: int
    urgency: Literal["critical", "high", "normal"]
    reason: str
    supplier_message: str = ""
    # "ordered" — create_purchase_order actually ran during the ReAct loop.
    # "pending_approval" — the agent flagged this but didn't have enough
    # confidence/info to order it. "failed" — it tried and the tool errored.
    status: Literal["ordered", "pending_approval", "failed"] = "ordered"
    purchase_order_id: Optional[str] = None


class AlertItem(BaseModel):
    type: str
    severity: Literal["low", "medium", "high", "critical"]
    sku: Optional[str] = None
    message: str


class AgentDecision(BaseModel):
    """The final structured output — mirrors the design doc's
    'What gets returned to the Supervisor' shape, plus actions_executed
    now that this agent can act, not just recommend."""
    summary: str
    forecasts: List[ForecastItem] = []
    recommendations: List[RecommendationItem] = []
    alerts: List[AlertItem] = []
    actions_executed: List[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []
