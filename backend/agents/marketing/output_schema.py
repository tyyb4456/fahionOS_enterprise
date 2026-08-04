"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CampaignItem(BaseModel):
    campaign_name: str
    goal: str = ""
    platform: str = "multi-channel"
    target_audience: str = ""
    budget: Optional[str] = None
    duration_days: int = 7
    status: Literal["launched", "scheduled", "draft"] = "draft"


class ContentAssetItem(BaseModel):
    platform: Literal["instagram", "facebook", "tiktok", "email", "sms", "blog", "threads"]
    content_type: Literal["post", "story", "reel", "email", "sms", "blog"]
    caption: str = ""
    hashtags: List[str] = []
    subject: str = ""
    body: str = ""
    cta: str = ""
    scheduled_for: Optional[str] = None
    status: Literal["published", "scheduled", "draft"] = "draft"
    published_ref_id: Optional[str] = None


class AudienceRecommendationItem(BaseModel):
    segment: str
    rationale: str = ""
    estimated_size: Optional[int] = None


class MarketingInsightItem(BaseModel):
    insight: str
    confidence: float = Field(ge=0, le=1, default=0.6)
    priority: Literal["low", "medium", "high"] = "low"


class MarketingDecision(BaseModel):
    """The final structured output — mirrors the design doc's
    'What gets returned to the Supervisor' shape, plus actions_executed
    now that this agent can act, not just recommend."""
    summary: str
    campaigns: List[CampaignItem] = []
    content: List[ContentAssetItem] = []
    audience_recommendations: List[AudienceRecommendationItem] = []
    insights: List[MarketingInsightItem] = []
    actions_executed: List[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []
    