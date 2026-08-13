"""
FashionOS Customer Support Agent — Pipeline State
====================================================
Same shape/spirit as every other agent's state.py — "one architecture,
different domain tools" — with Customer Support Agent-specific task and
output fields.

Unlike the other six agents, this one is primarily event-driven (an
inbound WhatsApp/Instagram/email/webchat message, see
api/routers/customer_support_webhook.py) rather than scheduler-driven, so
`task` usually carries the inbound message + channel identifiers rather
than just a time range/objective.
"""
from typing import Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class SupportTask(TypedDict, total=False):
    """What the supervisor, a channel webhook, or a scheduler hands the agent."""
    task_type: Literal[
        "handle_customer_message",  # inbound message from a channel — the main event-driven task
        "handle_customer_issue",    # explicit issue handed by the supervisor/a human
        "process_return",
        "check_order_status",
        "escalation_review",        # periodic sweep of stale open tickets
    ]
    channel: Literal["whatsapp", "instagram", "email", "webchat"]
    external_thread_id: Optional[str]   # phone number | IGSID | email address | webchat session id
    customer_id: Optional[str]          # Shopify customer_id, if already known
    order_id: Optional[str]             # Shopify order_id, if already known
    message: Optional[str]              # the customer's raw inbound text
    issue: Optional[str]                # supervisor-provided issue description
    priority: Literal["low", "normal", "high", "critical"]
    trigger: str                        # "webhook:whatsapp" | "webhook:instagram" | "webhook:email" | "webchat" | "manual" | "escalation_sweep"


class SupportBusinessContext(TypedDict, total=False):
    """Step 1 (+3) output — the snapshot handed to the reasoning loop."""
    customer: Optional[Dict[str, Any]]
    recent_orders: List[Dict[str, Any]]
    return_history: List[Dict[str, Any]]
    open_tickets: List[Dict[str, Any]]
    recent_conversation: List[Dict[str, Any]]
    inventory_alerts: List[Dict[str, Any]]
    conversation_id: Optional[str]


class TicketOut(TypedDict, total=False):
    issue_type: str
    priority: Literal["low", "normal", "high", "critical"]
    status: Literal["open", "in_progress", "resolved", "escalated", "closed"]
    resolution: str


class SupportInsightOut(TypedDict, total=False):
    category: Literal["pattern", "product", "delivery", "policy", "churn_risk"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    confidence: float


class SupportPipelineState(MessagesState, total=False):
    # ── identity ──────────────────────────────────────────────────────────
    brand_id: str

    # ── input ─────────────────────────────────────────────────────────────
    task: SupportTask

    # ── step 1 + 3: context builder + RAG snapshot ───────────────────────
    context: SupportBusinessContext

    # ── step 4: tools used ────────────────────────────────────────────────
    tools_used: List[str]

    # ── step 5/6: decision generator output ───────────────────────────────
    ticket: TicketOut
    customer_reply: str
    customer_sentiment: Literal["positive", "mixed", "negative"]
    insights: List[SupportInsightOut]
    actions_executed: List[str]
    escalation_required: bool
    escalation_reason: str
    summary: str
    confidence: float
    next_actions: List[str]

    # ── step 7: persistence layer result ────────────────────────────────
    db_updates: List[str]

    # ── execution metadata ────────────────────────────────────────────────
    status: Literal["running", "completed", "failed"]
    error: Optional[str]