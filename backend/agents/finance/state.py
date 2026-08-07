"""
FashionOS Finance Agent — Pipeline State
===========================================
Same shape/spirit as agents/inventory/state.py, agents/sales/state.py, and
agents/marketing/state.py — "one architecture, different domain tools" —
with Finance Agent-specific task and output fields.
"""
from typing import Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class FinanceTask(TypedDict, total=False):
    """What the supervisor (or a scheduler/webhook) hands the agent."""
    task_type: Literal[
        "financial_analysis",
        "evaluate_purchase_order",
        "cashflow_forecast",
        "budget_review",
        "expense_analysis",
    ]
    time_range: Literal["today", "yesterday", "last_7_days", "last_14_days", "last_30_days", "last_90_days"]
    period: str                          # some callers may send "period" instead of "time_range" — both accepted
    forecast_days: int                   # for cashflow_forecast
    purchase_order_id: Optional[str]     # for evaluate_purchase_order
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str                         # "daily_scheduler" | "manual" | "webhook:..." | ...


class FinanceBusinessContext(TypedDict, total=False):
    """Step 1 output — the snapshot handed to the reasoning loop."""
    profit_summary: Dict[str, Any]
    inventory_valuation: Dict[str, Any]
    recent_expenses: List[Dict[str, Any]]
    open_purchase_order_costs: List[Dict[str, Any]]
    sales_insights: List[Dict[str, Any]]
    latest_sales_report: Optional[Dict[str, Any]]
    open_inventory_alerts: List[Dict[str, Any]]
    marketing_insights: List[Dict[str, Any]]
    recent_campaigns: List[Dict[str, Any]]
    previous_financial_reports: List[Dict[str, Any]]
    open_risk_assessments: List[Dict[str, Any]]


class ProfitReportOut(TypedDict, total=False):
    period: str
    revenue: float
    expenses: float
    refunds: float
    profit: float
    margin_pct: float


class CashflowForecastOut(TypedDict, total=False):
    forecast_days: int
    cash_today: float
    predicted_cash: float
    predicted_revenue: float
    predicted_expenses: float
    risk: Literal["low", "medium", "high", "critical"]
    confidence: float


class FinancialInsightOut(TypedDict, total=False):
    category: str          # "profitability" | "cashflow" | "expense" | "budget" | "risk"
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float


class PurchaseOrderEvaluationOut(TypedDict, total=False):
    purchase_order_id: Optional[str]
    approved: Optional[bool]
    approved_budget: Optional[float]
    reason: str
    conditions: List[str]


class FinancePipelineState(MessagesState, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: FinanceTask

    # ── step 1: context builder ─────────────────────────────────────────
    context: FinanceBusinessContext

    # ── step 4: tools used ───────────────────────────────────────────────
    tools_used: List[str]

    # ── step 5/6: decision generator output ─────────────────────────────
    profit_report: ProfitReportOut
    cashflow_forecast: Optional[CashflowForecastOut]
    insights: List[FinancialInsightOut]
    purchase_order_evaluation: Optional[PurchaseOrderEvaluationOut]
    actions_executed: List[str]
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ───────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]