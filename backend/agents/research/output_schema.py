"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.

Only trends + insights live here — the routine, always-attempted analytical
output every run produces (same role as Inventory's forecasts/alerts or
Sales's insights/anomalies). product_opportunities / competitor_updates /
pricing_insights are NOT part of this schema on purpose: those are written
directly, conditionally, mid-loop via their own dedicated tools
(create_product_opportunity / record_competitor_analysis /
record_pricing_insight in agents/research/tools.py) — the same split
Finance uses for record_expense / create_budget_recommendation /
assess_financial_risk vs. its own always-written profit_report.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TrendItem(BaseModel):
    trend: str
    category: str = ""
    growth_pct: Optional[float] = None
    confidence: float = Field(ge=0, le=1, default=0.5)
    source: str = ""
    summary: str = ""


class ResearchInsightItem(BaseModel):
    category: Literal["trend", "competitor", "pricing", "customer", "keyword", "forecast"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float = Field(ge=0, le=1, default=0.6)


class ResearchDecision(BaseModel):
    """The final structured output — mirrors the design doc's 'What It
    Returns to Supervisor' shape. actions_executed covers what actually
    got written via the mid-loop operational tools (product opportunities,
    competitor analyses, pricing insights, notifications) during this run —
    list only things that actually happened, not things merely proposed."""
    summary: str
    trends: List[TrendItem] = []
    insights: List[ResearchInsightItem] = []
    actions_executed: List[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []