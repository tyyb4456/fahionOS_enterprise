"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProfitReportOut(BaseModel):
    period: str = "last_30_days"
    revenue: float = 0
    expenses: float = 0
    refunds: float = 0
    profit: float = 0
    margin_pct: float = 0


class CashflowForecastOut(BaseModel):
    forecast_days: int = 30
    cash_today: float = 0
    predicted_cash: float = 0
    predicted_revenue: float = 0
    predicted_expenses: float = 0
    risk: Literal["low", "medium", "high", "critical"] = "low"
    confidence: float = Field(ge=0, le=1, default=0.5)


class FinancialInsightItem(BaseModel):
    category: Literal["profitability", "cashflow", "expense", "budget", "risk"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float = Field(ge=0, le=1, default=0.6)


class PurchaseOrderEvaluationOut(BaseModel):
    purchase_order_id: Optional[str] = None
    approved: Optional[bool] = None
    approved_budget: Optional[float] = None
    reason: str = ""
    conditions: List[str] = []


class FinancialDecision(BaseModel):
    """The final structured output — mirrors the design doc's 'What It
    Returns to Supervisor' shape, plus actions_executed for what this
    agent actually did (record_expense, create_budget_recommendation,
    assess_financial_risk), not just recommended."""
    summary: str
    profit_report: ProfitReportOut = ProfitReportOut()
    cashflow_forecast: Optional[CashflowForecastOut] = None
    insights: List[FinancialInsightItem] = []
    purchase_order_evaluation: Optional[PurchaseOrderEvaluationOut] = None
    actions_executed: List[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []