"""
Internal tools for the Customer Support Agent's ReAct loop — everything
that isn't a live Shopify/Meta/courier call (those come from shopify-mcp /
meta-mcp / customer-support-mcp, see mcp_client.py). Each factory below
binds `brand_id` in a closure so the LLM never has to supply it — same
reasoning as agents/common/tool_scoping.py.

Four flavors of tool live here:
  - lookups (customer profile, conversation history, stock check before
    promising an exchange)
  - deterministic helpers (agents/customer_support/analytics.py — return/
    exchange eligibility windows, refund math: things that should be
    computed from the policy numbers already retrieved, not eyeballed)
  - LLM-backed analysis (analyze_customer_sentiment — a dedicated,
    extraction-focused call, same separation-of-concerns reasoning as
    Research's analyze_customer_sentiment / Marketing's caption generator)
  - operational writes (create_support_ticket, record_refund,
    create_exchange, send_customer_message, flag_recurring_issue,
    notify_brand_owner) — these change real state immediately, mid-loop,
    the same way every other agent's operational tools do

create_refund and cancel_order are deliberately NOT here — they're real
Shopify writes and live on shopify-mcp like every other Shopify write in
this codebase (see mcp_client.py). record_refund is the follow-up
internal tool that logs what create_refund just did into our own audit
table — same two-step shape as Inventory's create_purchase_order ->
notify_supplier, or Supplier's track_shipment -> update_shipment_status.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.common.notify_tools import make_notify_brand_owner_tool
from db import crud_customer_support as crud
from db.session import AsyncSessionLocal
from notifications.dispatch import send_email, send_whatsapp

from . import analytics
from . import memory as rag

logger = logging.getLogger(__name__)

CUSTOMER_SUPPORT_ANALYSIS_MODEL = os.getenv("CUSTOMER_SUPPORT_ANALYSIS_MODEL", "claude-sonnet-5")


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_customer_profile_tool(brand_id),
        _make_customer_orders_tool(brand_id),
        _make_conversation_history_tool(brand_id),
        _make_check_stock_tool(brand_id),
        _make_eligibility_tool(),
        _make_refund_calc_tool(),
        _make_escalation_check_tool(),
        _make_sentiment_tool(),
        _make_create_ticket_tool(brand_id),
        _make_update_ticket_tool(brand_id),
        _make_record_refund_tool(brand_id),
        _make_create_exchange_tool(brand_id),
        _make_send_whatsapp_email_tool(brand_id),
        _make_flag_recurring_issue_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
        make_notify_brand_owner_tool(brand_id, agent_name="Customer Support Agent"),
    ]


# ── get_customer_profile ──────────────────────────────────────────────────

class _IdentifierArgs(BaseModel):
    identifier: str = Field(description="Customer email, phone number (fuzzy match), or Shopify customer_id.")


def _make_customer_profile_tool(brand_id: str) -> StructuredTool:
    async def _run(identifier: str) -> dict:
        async with AsyncSessionLocal() as session:
            profile = await crud.get_customer_profile(session, brand_id, identifier)
        return profile or {"error": f"No customer matching '{identifier}'."}

    return StructuredTool.from_function(
        name="get_customer_profile",
        description=(
            "Look up a customer's full profile — name, contact info, order history summary, "
            "lifetime value, customer_segment (VIP/Loyal/New/At Risk/Inactive from the Sales "
            "Agent), and how many other support tickets they have open right now. Always call "
            "this before resolving anything — never guess who you're talking to."
        ),
        args_schema=_IdentifierArgs,
        coroutine=_run,
    )


# ── get_customer_orders ───────────────────────────────────────────────────

class _CustomerOrdersArgs(BaseModel):
    identifier: str = Field(description="Customer email, phone, or Shopify customer_id.")


def _make_customer_orders_tool(brand_id: str) -> StructuredTool:
    async def _run(identifier: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            profile = await crud.get_customer_profile(session, brand_id, identifier)
            if not profile:
                return [{"error": f"No customer matching '{identifier}'."}]
            return await crud._recent_orders_for_customer(session, brand_id, profile, limit=20)

    return StructuredTool.from_function(
        name="get_customer_orders",
        description="Full recent order history for a customer, with line items — use when the context snapshot's order list isn't enough (older order, need more than 10).",
        args_schema=_CustomerOrdersArgs,
        coroutine=_run,
    )


# ── get_conversation_history ──────────────────────────────────────────────

class _ConversationHistoryArgs(BaseModel):
    channel: str = Field(description="'whatsapp' | 'instagram' | 'email' | 'webchat'.")
    external_thread_id: str = Field(description="Phone number / IGSID / email address / webchat session id for this thread.")


def _make_conversation_history_tool(brand_id: str) -> StructuredTool:
    async def _run(channel: str, external_thread_id: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_conversation_history(session, brand_id, channel, external_thread_id, limit=50)

    return StructuredTool.from_function(
        name="get_conversation_history",
        description="Full message history for a conversation thread, beyond what's already in your context — use if you need more than the recent snippet shown.",
        args_schema=_ConversationHistoryArgs,
        coroutine=_run,
    )


# ── check_product_stock ───────────────────────────────────────────────────

class _SkuArgs(BaseModel):
    sku: str = Field(description="SKU to check — e.g. the replacement size/color for an exchange.")


def _make_check_stock_tool(brand_id: str) -> StructuredTool:
    async def _run(sku: str) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.check_product_stock(session, brand_id, sku)
        return result or {"error": f"SKU '{sku}' not found in synced product data."}

    return StructuredTool.from_function(
        name="check_product_stock",
        description="Check current stock for a SKU before promising an exchange or telling a customer something is available.",
        args_schema=_SkuArgs,
        coroutine=_run,
    )


# ── check_return_eligibility (deterministic helper) ───────────────────────

class _EligibilityArgs(BaseModel):
    delivered_at: Optional[str] = Field(default=None, description="ISO8601 delivery date, from the order. Omit if unknown.")
    window_days: int = Field(description="The policy's window in days — get this from retrieve_policy first, don't guess it.")


def _make_eligibility_tool() -> StructuredTool:
    async def _run(delivered_at: Optional[str] = None, window_days: int = 7) -> dict:
        parsed = None
        if delivered_at:
            try:
                parsed = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
            except ValueError:
                return {"error": f"Couldn't parse delivered_at='{delivered_at}' as ISO8601."}
        return analytics.check_window_eligibility(parsed, window_days)

    return StructuredTool.from_function(
        name="check_return_eligibility",
        description=(
            "Check whether an order is still inside a return/exchange/cancellation window — pure "
            "date math against the delivered_at date and the policy's window_days (from "
            "retrieve_policy). Use this instead of eyeballing dates yourself."
        ),
        args_schema=_EligibilityArgs,
        coroutine=_run,
    )


# ── calculate_refund_amount (deterministic helper) ────────────────────────

class _RefundCalcArgs(BaseModel):
    line_item_price: float = Field(description="Unit price of the item being refunded.")
    quantity: int = Field(default=1, description="Quantity being refunded.")
    restocking_fee_pct: float = Field(default=0.0, description="Restocking fee % from policy, if any.")
    deduct_original_shipping: bool = Field(default=False, description="Whether policy says original shipping is non-refundable.")
    original_shipping_cost: float = Field(default=0.0, description="Original shipping cost, if it's being deducted.")


def _make_refund_calc_tool() -> StructuredTool:
    async def _run(
        line_item_price: float, quantity: int = 1, restocking_fee_pct: float = 0.0,
        deduct_original_shipping: bool = False, original_shipping_cost: float = 0.0,
    ) -> dict:
        return analytics.calculate_refund_amount(
            line_item_price, quantity, restocking_fee_pct, deduct_original_shipping, original_shipping_cost,
        )

    return StructuredTool.from_function(
        name="calculate_refund_amount",
        description="Compute the exact refund amount from policy numbers (restocking fee %, shipping deduction) — never do this arithmetic yourself.",
        args_schema=_RefundCalcArgs,
        coroutine=_run,
    )


# ── check_escalation_guardrail (deterministic helper) ─────────────────────

class _EscalationArgs(BaseModel):
    priority: str = Field(description="'low' | 'normal' | 'high' | 'critical'.")
    sentiment: str = Field(description="'positive' | 'mixed' | 'negative'.")
    previous_open_issues: int = Field(default=0, description="This customer's other currently-open ticket count, from get_customer_profile.")
    refund_amount: Optional[float] = Field(default=None, description="The refund amount under consideration, if any.")
    refund_auto_approval_limit: float = Field(default=20000.0, description="This brand's auto-approval ceiling — check retrieve_policy for the real number if one is on file.")


def _make_escalation_check_tool() -> StructuredTool:
    async def _run(
        priority: str, sentiment: str, previous_open_issues: int = 0,
        refund_amount: Optional[float] = None, refund_auto_approval_limit: float = 20000.0,
    ) -> dict:
        return analytics.should_auto_escalate(priority, sentiment, previous_open_issues, refund_amount, refund_auto_approval_limit)

    return StructuredTool.from_function(
        name="check_escalation_guardrail",
        description=(
            "Deterministic check for whether this case must be escalated rather than "
            "auto-resolved (critical priority, refund over the approval limit, or a churn-risk "
            "pattern of repeat unresolved issues + negative sentiment). Call before deciding to "
            "resolve a refund/complaint yourself."
        ),
        args_schema=_EscalationArgs,
        coroutine=_run,
    )


# ── analyze_customer_sentiment (LLM-backed analysis) ───────────────────────

def _analysis_model(temperature: float = 0.1) -> ChatAnthropic:
    return ChatAnthropic(model=CUSTOMER_SUPPORT_ANALYSIS_MODEL, temperature=temperature)


class _SentimentOutput(BaseModel):
    sentiment: str = Field(description="'positive' | 'mixed' | 'negative'.")
    is_churn_risk: bool = Field(description="True if the customer sounds ready to stop buying from this brand.")
    key_concerns: List[str] = Field(default_factory=list)


class _SentimentArgs(BaseModel):
    message: str = Field(description="The customer's message text to analyze.")
    context_note: str = Field(default="", description="Optional — anything relevant, e.g. 'this is their 3rd complaint in 30 days'.")


def _make_sentiment_tool() -> StructuredTool:
    async def _run(message: str, context_note: str = "") -> dict:
        model = _analysis_model().with_structured_output(_SentimentOutput)
        result: _SentimentOutput = await model.ainvoke(
            f"Analyze this customer message for sentiment and churn risk.\n"
            f"Context: {context_note or '(none)'}\n\nMessage:\n{message}"
        )
        return result.model_dump()

    return StructuredTool.from_function(
        name="analyze_customer_sentiment",
        description="Read a customer message's real sentiment and churn risk instead of guessing from tone yourself — especially useful when a message reads ambiguous or is a repeat complaint.",
        args_schema=_SentimentArgs,
        coroutine=_run,
    )


# ── create_support_ticket (operational write) ──────────────────────────────

class _CreateTicketArgs(BaseModel):
    issue_type: str = Field(description="'order_status' | 'delivery_issue' | 'return' | 'exchange' | 'refund' | 'product_question' | 'complaint' | 'other'.")
    priority: str = Field(default="normal", description="'low' | 'normal' | 'high' | 'critical'.")
    customer_id: Optional[str] = Field(default=None, description="Shopify customer_id.")
    order_id: Optional[str] = Field(default=None, description="Shopify order_id, if relevant.")
    conversation_id: Optional[str] = Field(default=None, description="From your context — links the ticket to this thread.")


def _make_create_ticket_tool(brand_id: str) -> StructuredTool:
    async def _run(issue_type: str, priority: str = "normal", customer_id: Optional[str] = None, order_id: Optional[str] = None, conversation_id: Optional[str] = None) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.create_ticket(session, brand_id, issue_type, priority, customer_id, order_id, conversation_id)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="create_support_ticket",
        description="Open a real support ticket for this issue — call this near the start of any non-trivial issue so it's tracked, even before you know the resolution yet.",
        args_schema=_CreateTicketArgs,
        coroutine=_run,
    )


# ── update_ticket_status (operational write) ────────────────────────────────

class _UpdateTicketArgs(BaseModel):
    ticket_id: str = Field(description="ticket_id from create_support_ticket.")
    status: str = Field(description="'open' | 'in_progress' | 'resolved' | 'escalated' | 'closed'.")
    resolution: str = Field(default="", description="What was decided/done — required when status is 'resolved' or 'escalated'.")


def _make_update_ticket_tool(brand_id: str) -> StructuredTool:
    async def _run(ticket_id: str, status: str, resolution: str = "") -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.update_ticket(session, brand_id, ticket_id, status, resolution)
            if "error" not in result:
                await session.commit()
        return result

    return StructuredTool.from_function(
        name="update_ticket_status",
        description="Update a ticket's status once you've made progress or reached a resolution. Always resolve or escalate the ticket you opened before finishing — never leave it silently open.",
        args_schema=_UpdateTicketArgs,
        coroutine=_run,
    )


# ── record_refund (operational write — audit log for a completed Shopify refund) ─

class _RecordRefundArgs(BaseModel):
    order_id: str = Field(description="Shopify order_id.")
    amount: float = Field(description="The exact amount refunded — from calculate_refund_amount / create_refund's response.")
    reason: str = Field(description="Why — what you found and decided.")
    shopify_refund_id: Optional[str] = Field(default=None, description="The refund id create_refund returned, if the Shopify write succeeded.")
    ticket_id: Optional[str] = Field(default=None, description="Ticket this refund resolves.")
    status: str = Field(default="issued", description="'issued' if create_refund succeeded, 'pending_approval' if you're escalating instead, 'failed' if the Shopify write errored.")


def _make_record_refund_tool(brand_id: str) -> StructuredTool:
    async def _run(order_id: str, amount: float, reason: str, shopify_refund_id: Optional[str] = None, ticket_id: Optional[str] = None, status: str = "issued") -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.record_refund(session, brand_id, order_id, amount, reason, shopify_refund_id, ticket_id, status)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="record_refund",
        description=(
            "Log a refund to our own audit trail — call this right after a successful "
            "shopify-mcp create_refund (with the real shopify_refund_id and status='issued'), or "
            "on its own with status='pending_approval' when you're escalating a refund instead of "
            "issuing it yourself. Never claim a refund happened without this record."
        ),
        args_schema=_RecordRefundArgs,
        coroutine=_run,
    )


# ── create_exchange (operational write) ─────────────────────────────────────

class _CreateExchangeArgs(BaseModel):
    order_id: str = Field(description="Shopify order_id being exchanged.")
    original_sku: str = Field(description="SKU the customer received.")
    new_sku: str = Field(description="SKU they're exchanging for — confirm stock with check_product_stock first.")
    ticket_id: Optional[str] = Field(default=None, description="Ticket this exchange resolves.")


def _make_create_exchange_tool(brand_id: str) -> StructuredTool:
    async def _run(order_id: str, original_sku: str, new_sku: str, ticket_id: Optional[str] = None) -> dict:
        async with AsyncSessionLocal() as session:
            stock = await crud.check_product_stock(session, brand_id, new_sku)
            if not stock:
                return {"error": f"SKU '{new_sku}' not found — can't create an exchange for something we don't have on file."}
            if stock.get("inventory_quantity", 0) <= 0:
                return {"error": f"SKU '{new_sku}' is out of stock — offer a refund or backorder instead."}
            result = await crud.create_exchange(session, brand_id, order_id, original_sku, new_sku, ticket_id)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="create_exchange",
        description=(
            "Record a real exchange — refuses automatically if the replacement SKU is out of "
            "stock, so you don't have to check separately first (though checking with "
            "check_product_stock before offering it to the customer is still good practice)."
        ),
        args_schema=_CreateExchangeArgs,
        coroutine=_run,
    )


# ── send_customer_message (operational write — real outbound message) ──────

class _SendMessageArgs(BaseModel):
    channel: str = Field(description="'whatsapp' | 'email'. For 'instagram', use send_instagram_dm (meta-mcp) instead. For 'webchat', just put the reply in your final customer_reply — there is no send tool.")
    to: str = Field(description="Phone number (whatsapp) or email address.")
    message: str = Field(description="The reply to send — match the channel's tone (short for WhatsApp, can be longer for email).")
    subject: str = Field(default="", description="Email subject line, required if channel='email'.")


def _make_send_whatsapp_email_tool(brand_id: str) -> StructuredTool:
    async def _run(channel: str, to: str, message: str, subject: str = "") -> dict:
        if channel == "whatsapp":
            async with AsyncSessionLocal() as session:
                from_phone_number_id = await crud.get_brand_whatsapp_phone_number_id(session, brand_id)
            result = await send_whatsapp(to, message, from_phone_number_id=from_phone_number_id)
        elif channel == "email":
            async with AsyncSessionLocal() as session:
                reply_to = await crud.get_brand_reply_to_email(session, brand_id)
            result = await send_email(to, subject or "Re: your recent order", message, reply_to=reply_to)
        else:
            return {"error": f"Unsupported channel '{channel}' for this tool — use send_instagram_dm for Instagram, or just answer directly for webchat."}

        async with AsyncSessionLocal() as session:
            await crud.log_agent_message(session, brand_id, channel, to, message)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="send_customer_message",
        description="Actually send your reply to the customer via WhatsApp or email, and log it to the conversation thread. Always send one, even for a 'we're looking into it' holding reply.",
        args_schema=_SendMessageArgs,
        coroutine=_run,
    )


# ── flag_recurring_issue (operational write) ────────────────────────────────

class _FlagRecurringArgs(BaseModel):
    category: str = Field(description="'pattern' | 'product' | 'delivery' | 'policy' | 'churn_risk'.")
    severity: str = Field(default="medium", description="'low' | 'medium' | 'high' | 'critical'.")
    message: str = Field(description="What you noticed and why it's a real pattern, not a one-off — cite the count/share if you have it (e.g. from detect_recurring_issue math you did in reasoning).")
    sku: Optional[str] = Field(default=None, description="If this traces to a specific SKU, also flag it into Inventory's own alert feed.")


def _make_flag_recurring_issue_tool(brand_id: str) -> StructuredTool:
    async def _run(category: str, message: str, severity: str = "medium", sku: Optional[str] = None) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.create_support_insight(session, brand_id, category, severity, message)
            if sku:
                await crud.create_inventory_flag(session, brand_id, sku, message, severity)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="flag_recurring_issue",
        description=(
            "Formally record a recurring support pattern worth the rest of the business seeing "
            "(e.g. sizing confusion driving returns on a SKU, a courier consistently late) — "
            "visible immediately on the dashboard. If it traces to a specific SKU, also writes "
            "directly into the Inventory Agent's alert feed. Only for real patterns across "
            "multiple tickets, not a single complaint."
        ),
        args_schema=_FlagRecurringArgs,
        coroutine=_run,
    )


# ── retrieve_policy / search_agent_memory (RAG) ────────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'exchange policy for unused items' or 'refund auto-approval limit'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description=(
            "Search brand-specific support policy documents (return/refund/exchange/shipping/"
            "cancellation/warranty policy, size guide, customer service SOP, escalation rules, "
            "brand voice) for guidance relevant to your query. Call before deciding eligibility, "
            "a refund amount, or how to word a reply."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )


def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description="Search notes this agent kept from previous runs (e.g. recurring sizing complaints, what tone worked for a churn-risk customer) for anything relevant now.",
        args_schema=_QueryArgs,
        coroutine=_run,
    )