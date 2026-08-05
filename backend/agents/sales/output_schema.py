"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class KpiReport(BaseModel):
    revenue: float = 0
    orders: int = 0
    average_order_value: float = 0
    refund_rate: float = 0
    repeat_customer_rate: float = 0


class SalesInsightItem(BaseModel):
    category: Literal["revenue", "product", "customer", "channel", "opportunity", "risk"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float = Field(ge=0, le=1, default=0.6)


class SalesForecastItem(BaseModel):
    forecast_date: str = Field(description="ISO date (YYYY-MM-DD) this forecast is for.")
    predicted_revenue: float
    predicted_orders: int = 0
    confidence: float = Field(ge=0, le=1, default=0.5)


class SalesAnomalyItem(BaseModel):
    metric: str
    expected: float
    actual: float
    severity: Literal["low", "medium", "high", "critical"]
    message: str = ""


class CustomerSegmentItem(BaseModel):
    segment: Literal["VIP", "New", "Loyal", "At Risk", "Inactive"]
    customer_count: int = 0
    definition: str = ""
    customer_ids: List[str] = []


class SalesDecision(BaseModel):
    """The final structured output — mirrors the design doc's
    'What gets returned to the Supervisor' shape, plus actions_executed
    now that this agent can act (create_discount_code, flag_inventory_issue),
    not just recommend."""
    summary: str
    kpis: KpiReport = KpiReport()
    insights: List[SalesInsightItem] = []
    forecasts: List[SalesForecastItem] = []
    anomalies: List[SalesAnomalyItem] = []
    customer_segments: List[CustomerSegmentItem] = []
    recommendations: List[str] = []
    actions_executed: List[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []