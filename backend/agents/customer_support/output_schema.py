"""
Structured shape the agent's free-form reasoning gets condensed into
(Step 5/6 — Decision Generator) via a structured-output model call — see
extract_decision_node in graph.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TicketItem(BaseModel):
    issue_type: Literal[
        "order_status", "delivery_issue", "return", "exchange",
        "refund", "product_question", "complaint", "other",
    ] = "other"
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    status: Literal["open", "in_progress", "resolved", "escalated", "closed"] = "open"
    resolution: str = ""


class SupportInsightItem(BaseModel):
    category: Literal["pattern", "product", "delivery", "policy", "churn_risk"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float = Field(ge=0, le=1, default=0.6)


class SupportDecision(BaseModel):
    """The final structured output — mirrors the design doc's 'What It
    Returns to Supervisor' shape. actions_executed lists only what
    actually happened (create_support_ticket / record_refund /
    create_exchange / send_customer_message tool calls that succeeded),
    not things merely proposed. customer_reply is the exact text that was
    (or should be) sent back to the customer — kept separate from
    `summary`, which is the internal report to the supervisor."""
    summary: str
    ticket: TicketItem = TicketItem()
    customer_reply: str = ""
    customer_sentiment: Literal["positive", "mixed", "negative"] = "mixed"
    insights: List[SupportInsightItem] = []
    actions_executed: List[str] = []
    escalation_required: bool = False
    escalation_reason: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    next_actions: List[str] = []