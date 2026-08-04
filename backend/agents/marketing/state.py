"""
FashionOS Marketing Agent — Pipeline State
=============================================
Same shape/spirit as agents/inventory/state.py and agents/sales/state.py —
"one architecture, different domain tools" — with Marketing Agent-specific
task and output fields.
"""
from typing import Any, Dict, List, Optional, Annotated, Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class MarketingTask(TypedDict, total=False):
    """What the supervisor (or a scheduler/webhook) hands the agent."""
    task_type: Literal[
        "plan_marketing",
        "daily_content",
        "campaign_analysis",
        "launch_campaign",
        "audience_analysis",
    ]
    objective: str                # e.g. "Increase hoodie sales"
    budget: Literal["low", "medium", "high"]
    timeline: str                 # e.g. "7_days"
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str                  # "daily_scheduler" | "manual" | "webhook:..." | ...


class MarketingBusinessContext(TypedDict, total=False):
    """Step 1 (+3) output — the snapshot handed to the reasoning loop."""
    products: List[Dict[str, Any]]
    sales_insights: List[Dict[str, Any]]
    latest_sales_report: Optional[Dict[str, Any]]
    inventory_alerts: List[Dict[str, Any]]
    customer_segments: List[Dict[str, Any]]
    previous_campaigns: List[Dict[str, Any]]
    marketing_calendar: List[Dict[str, Any]]


class CampaignOut(TypedDict, total=False):
    campaign_name: str
    goal: str
    platform: str
    target_audience: str
    budget: Optional[str]
    duration_days: int
    status: Literal["launched", "scheduled", "draft"]


class ContentAssetOut(TypedDict, total=False):
    platform: str
    content_type: str
    caption: str
    hashtags: List[str]
    subject: str
    body: str
    cta: str
    scheduled_for: Optional[str]
    status: Literal["published", "scheduled", "draft"]
    published_ref_id: Optional[str]


class AudienceRecommendationOut(TypedDict, total=False):
    segment: str
    rationale: str
    estimated_size: Optional[int]


class MarketingInsightOut(TypedDict, total=False):
    insight: str
    confidence: float
    priority: Literal["low", "medium", "high"]


class MarketingPipelineState(MessagesState, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: MarketingTask

    # ── step 1 + 3: context builder + RAG snapshot ───────────────────────
    context: MarketingBusinessContext



    tools_used: List[str]

    # ── step 5/6: decision generator output ───────────────────────────────
    campaigns: List[CampaignOut]
    content: List[ContentAssetOut]
    audience_recommendations: List[AudienceRecommendationOut]
    insights: List[MarketingInsightOut]
    actions_executed: List[str]
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ──────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ────────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]