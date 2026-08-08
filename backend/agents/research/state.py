"""
FashionOS Research Agent — Pipeline State
============================================
Same shape/spirit as agents/inventory/state.py, agents/sales/state.py,
agents/marketing/state.py, and agents/finance/state.py — "one architecture,
different domain tools" — with Research Agent-specific task and output
fields.
"""
from typing import Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class ResearchTask(TypedDict, total=False):
    """What the supervisor (or a scheduler) hands the agent."""
    task_type: Literal[
        "market_research",
        "competitor_analysis",
        "trend_monitoring",
        "pricing_intelligence",
        "product_opportunity_scan",
    ]
    category: Optional[str]          # e.g. "hoodies"
    region: Optional[str]            # e.g. "Pakistan"
    competitors: Optional[List[str]] # e.g. ["Brand A", "Brand B"]
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str                     # "daily_scheduler" | "manual" | "webhook:..." | ...


class ResearchBusinessContext(TypedDict, total=False):
    """Step 1 output — the snapshot handed to the reasoning loop. Mostly
    internal grounding context; the real substance comes from external
    tools called on demand inside the ReAct loop (Step 2 in the design
    doc), not pre-fetched here."""
    catalog: Dict[str, Any]
    sales_insights: List[Dict[str, Any]]
    inventory_signals: List[Dict[str, Any]]
    active_campaigns: List[Dict[str, Any]]
    previous_trends: List[Dict[str, Any]]
    previous_opportunities: List[Dict[str, Any]]


class TrendOut(TypedDict, total=False):
    trend: str
    category: Optional[str]
    growth_pct: Optional[float]
    confidence: float
    source: Optional[str]
    summary: str


class ResearchInsightOut(TypedDict, total=False):
    category: Literal["trend", "competitor", "pricing", "customer", "keyword", "forecast"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float


class ResearchPipelineState(MessagesState, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: ResearchTask

    # ── step 1: context builder ─────────────────────────────────────────
    context: ResearchBusinessContext

    # ── step 4: tools used ───────────────────────────────────────────────
    tools_used: List[str]

    # ── step 5/6: decision generator output ─────────────────────────────
    trends: List[TrendOut]
    insights: List[ResearchInsightOut]
    actions_executed: List[str]
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ───────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]