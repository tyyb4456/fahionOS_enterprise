"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via ChatAnthropic.with_structured_output().
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


class AlertItem(BaseModel):
    type: str
    severity: Literal["low", "medium", "high", "critical"]
    sku: Optional[str] = None
    message: str


class AgentDecision(BaseModel):
    """The final structured output — mirrors the design doc's
    'What gets returned to the Supervisor' shape."""
    summary: str
    forecasts: List[ForecastItem] = []
    recommendations: List[RecommendationItem] = []
    alerts: List[AlertItem] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []
