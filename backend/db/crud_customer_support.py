"""
Customer Support Agent — read/write layer.

Table ownership:
  - reads but doesn't own: Customer/SalesOrder/OrderLineItem/Return
    (Shopify mirror), Product/ProductVariant (catalog), CustomerSegment
    (Sales Agent's own output — used for "customer_segment" in the
    profile), InventoryAlert (Inventory Agent's own output, read for
    cross-checking + written to for cross-agent flags, same "shared
    Postgres, no duplicate tables" pattern Sales' create_inventory_flag
    already uses).
  - owns outright: SupportConversation, SupportMessage, SupportTicket,
    SupportAction, RefundRecord, ExchangeRecord, CustomerFeedback,
    SupportInsight, + the shared AgentExecutionLog/AgentMemory via
    db/crud_common.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Brand, Customer, CustomerFeedback, CustomerSegment, ExchangeRecord,
    InventoryAlert, OrderLineItem, Product, ProductVariant, RefundRecord,
    Return, SalesOrder, SupportAction, SupportConversation, SupportInsight,
    SupportMessage, SupportTicket,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(session: AsyncSession, brand_id: str, task: dict) -> dict[str, Any]:
    """
    Assemble the snapshot handed to the reasoning loop. For an inbound
    channel message this also resolves (or creates) the conversation
    thread and logs the customer's inbound text as a SupportMessage —
    a "get-or-create" role similar to Marketing's create_scheduled_content
    creating a real row the rest of the run then references.
    """
    channel = task.get("channel")
    external_thread_id = task.get("external_thread_id")
    identifier = task.get("customer_id") or external_thread_id or ""

    conversation = None
    if channel and external_thread_id:
        conversation = await get_or_create_conversation(session, brand_id, channel, external_thread_id)
        if task.get("message"):
            await _log_message(session, brand_id, conversation.id, "customer", task["message"])
        await session.flush()

    customer = await get_customer_profile(session, brand_id, identifier) if identifier else None
    orders = await _recent_orders_for_customer(session, brand_id, customer) if customer else []
    returns = await _return_history_for_customer(session, brand_id, customer) if customer else []
    open_tickets = await _open_tickets_for_customer(session, brand_id, customer) if customer else []
    recent_conversation = (
        await get_conversation_history(session, brand_id, channel, external_thread_id, limit=20)
        if channel and external_thread_id else []
    )
    inventory_alerts = await _open_inventory_alerts(session, brand_id, limit=10)

    return {
        "customer": customer,
        "recent_orders": orders,
        "return_history": returns,
        "open_tickets": open_tickets,
        "recent_conversation": recent_conversation,
        "inventory_alerts": inventory_alerts,
        "conversation_id": str(conversation.id) if conversation else None,
    }


async def _recent_orders_for_customer(session: AsyncSession, brand_id: str, customer: dict, limit: int = 10) -> list[dict]:
    shopify_customer_id = customer.get("shopify_customer_id")
    if not shopify_customer_id:
        return []
    stmt = (
        select(SalesOrder)
        .where(SalesOrder.brand_id == brand_id, SalesOrder.shopify_customer_id == shopify_customer_id)
        .order_by(SalesOrder.created_at.desc())
        .limit(limit)
    )
    orders = (await session.execute(stmt)).scalars().all()
    result = []
    for o in orders:
        items = (await session.execute(select(OrderLineItem).where(OrderLineItem.order_id == o.id))).scalars().all()
        result.append({
            "order_id": str(o.shopify_order_id), "created_at": o.created_at.isoformat(),
            "financial_status": o.financial_status, "fulfillment_status": o.fulfillment_status,
            "total_price": o.total_price,
            "line_items": [{"sku": li.sku, "name": li.name, "quantity": li.quantity, "price": li.price} for li in items],
        })
    return result


async def _return_history_for_customer(session: AsyncSession, brand_id: str, customer: dict, limit: int = 10) -> list[dict]:
    shopify_customer_id = customer.get("shopify_customer_id")
    if not shopify_customer_id:
        return []
    order_ids = list((await session.execute(
        select(SalesOrder.shopify_order_id).where(SalesOrder.brand_id == brand_id, SalesOrder.shopify_customer_id == shopify_customer_id)
    )).scalars().all())
    if not order_ids:
        return []
    stmt = (
        select(Return)
        .where(Return.brand_id == brand_id, Return.shopify_order_id.in_(order_ids))
        .order_by(Return.refunded_at.desc())
        .limit(limit)
    )
    return [
        {"sku": r.sku, "product_name": r.product_name, "quantity": r.quantity,
         "refund_amount": r.refund_amount, "return_reason": r.return_reason or ""}
        for r in (await session.execute(stmt)).scalars().all()
    ]


async def _open_tickets_for_customer(session: AsyncSession, brand_id: str, customer: dict, limit: int = 10) -> list[dict]:
    shopify_customer_id = customer.get("shopify_customer_id")
    if not shopify_customer_id:
        return []
    stmt = (
        select(SupportTicket)
        .where(
            SupportTicket.brand_id == brand_id,
            SupportTicket.shopify_customer_id == shopify_customer_id,
            SupportTicket.status.in_(["open", "in_progress", "escalated"]),
        )
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    return [
        {"id": str(t.id), "issue_type": t.issue_type, "priority": t.priority, "status": t.status, "created_at": t.created_at.isoformat()}
        for t in (await session.execute(stmt)).scalars().all()
    ]


async def _open_inventory_alerts(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    stmt = (
        select(InventoryAlert)
        .where(InventoryAlert.brand_id == brand_id, InventoryAlert.resolved == False)  # noqa: E712
        .order_by(InventoryAlert.created_at.desc())
        .limit(limit)
    )
    return [
        {"type": a.type, "severity": a.severity, "sku": a.sku, "message": a.message}
        for a in (await session.execute(stmt)).scalars().all()
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Conversations / messages
# ══════════════════════════════════════════════════════════════════════════════

async def get_or_create_conversation(session: AsyncSession, brand_id: str, channel: str, external_thread_id: str) -> SupportConversation:
    stmt = select(SupportConversation).where(
        SupportConversation.brand_id == brand_id, SupportConversation.channel == channel,
        SupportConversation.external_thread_id == external_thread_id, SupportConversation.status == "open",
    )
    convo = (await session.execute(stmt)).scalar_one_or_none()
    if convo:
        return convo

    convo = SupportConversation(brand_id=brand_id, channel=channel, external_thread_id=external_thread_id, status="open")
    session.add(convo)
    await session.flush()
    return convo


async def _log_message(session: AsyncSession, brand_id: str, conversation_id, sender: str, content: str) -> None:
    session.add(SupportMessage(brand_id=brand_id, conversation_id=conversation_id, sender=sender, content=content))
    await session.flush()


async def log_agent_message(session: AsyncSession, brand_id: str, channel: str, external_thread_id: str, content: str) -> dict:
    """Used by agents/customer_support/tools.py::send_customer_message
    after a real send — logs the outbound reply against the same thread."""
    convo = await get_or_create_conversation(session, brand_id, channel, external_thread_id)
    await _log_message(session, brand_id, convo.id, "agent", content)
    convo.last_message_at = datetime.now(timezone.utc)
    await session.flush()
    return {"conversation_id": str(convo.id), "logged": True}


async def get_conversation_history(session: AsyncSession, brand_id: str, channel: Optional[str], external_thread_id: Optional[str], limit: int = 20) -> list[dict]:
    if not channel or not external_thread_id:
        return []
    convo = (await session.execute(
        select(SupportConversation)
        .where(SupportConversation.brand_id == brand_id, SupportConversation.channel == channel, SupportConversation.external_thread_id == external_thread_id)
        .order_by(SupportConversation.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not convo:
        return []
    rows = list(reversed((await session.execute(
        select(SupportMessage).where(SupportMessage.conversation_id == convo.id).order_by(SupportMessage.created_at.desc()).limit(limit)
    )).scalars().all()))
    return [{"sender": m.sender, "content": m.content, "created_at": m.created_at.isoformat()} for m in rows]


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/customer_support/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def get_customer_profile(session: AsyncSession, brand_id: str, identifier: str) -> Optional[dict]:
    if not identifier:
        return None
    as_int = int(identifier) if identifier.isdigit() else None
    stmt = select(Customer).where(
        Customer.brand_id == brand_id,
        (Customer.email.ilike(f"%{identifier}%"))
        | (Customer.phone.ilike(f"%{identifier}%"))
        | (Customer.shopify_customer_id == (as_int if as_int is not None else -1)),
    )
    c = (await session.execute(stmt)).scalars().first()
    if not c:
        return None

    segment = await _customer_segment_label(session, brand_id, str(c.shopify_customer_id))

    open_count = (await session.execute(select(func.count(SupportTicket.id)).where(
        SupportTicket.brand_id == brand_id, SupportTicket.shopify_customer_id == c.shopify_customer_id,
        SupportTicket.status.in_(["open", "in_progress", "escalated"]),
    ))).scalar_one() or 0

    return {
        "customer_id": str(c.shopify_customer_id),
        "shopify_customer_id": c.shopify_customer_id,
        "email": c.email, "phone": c.phone,
        "name": f"{c.first_name or ''} {c.last_name or ''}".strip(),
        "country": c.country, "city": c.city,
        "orders_count": c.orders_count, "total_spent": c.total_spent,
        "first_order_at": c.first_order_at.isoformat() if c.first_order_at else None,
        "last_order_at": c.last_order_at.isoformat() if c.last_order_at else None,
        "customer_segment": segment,
        "open_ticket_count": open_count,
    }


async def _customer_segment_label(session: AsyncSession, brand_id: str, shopify_customer_id: str) -> Optional[str]:
    """CustomerSegment.customer_ids is a JSON list of string ids (see
    agents/sales/analytics.py::segment_customers) — no FK to join on, so
    this is a light Python-side scan over this brand's (small) segment set."""
    for seg in (await session.execute(select(CustomerSegment).where(CustomerSegment.brand_id == brand_id))).scalars().all():
        if shopify_customer_id in (seg.customer_ids or []):
            return seg.segment
    return None


async def check_product_stock(session: AsyncSession, brand_id: str, sku: str) -> Optional[dict]:
    row = (await session.execute(
        select(ProductVariant, Product).join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.brand_id == brand_id, ProductVariant.sku == sku)
    )).first()
    if not row:
        return None
    variant, product = row
    return {
        "sku": sku, "title": product.title, "variant_title": variant.title,
        "price": variant.price, "inventory_quantity": variant.inventory_quantity,
    }

async def get_brand_reply_to_email(session: AsyncSession, brand_id: str) -> Optional[str]:
    """Used by agents/customer_support/tools.py when sending an email
    reply, so the customer's "Reply" routes back into our inbound
    pipeline instead of the unmonitored outbound sending address."""
    stmt = select(Brand.support_inbound_email).where(Brand.brand_id == brand_id)
    return (await session.execute(stmt)).scalar_one_or_none()

# ══════════════════════════════════════════════════════════════════════════════
# Operational writes — real, immediate DB changes made mid-ReAct-loop by
# agents/customer_support/tools.py. Callers commit; these only add+flush,
# same convention as the rest of this codebase's Step 7 helpers. ──────────

async def create_ticket(
    session: AsyncSession, brand_id: str, issue_type: str, priority: str = "normal",
    customer_id: Optional[str] = None, order_id: Optional[str] = None, conversation_id: Optional[str] = None,
) -> dict:
    logger.info("Creating support ticket for brand=%s issue_type=%s priority=%s", brand_id, issue_type, priority)
    ticket = SupportTicket(
        brand_id=brand_id, issue_type=issue_type, priority=priority, status="open",
        shopify_customer_id=int(customer_id) if customer_id and str(customer_id).isdigit() else None,
        shopify_order_id=int(order_id) if order_id and str(order_id).isdigit() else None,
        conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
    )
    session.add(ticket)
    await session.flush()
    return {"ticket_id": str(ticket.id), "issue_type": issue_type, "priority": priority, "status": "open"}


async def update_ticket(session: AsyncSession, brand_id: str, ticket_id: str, status: str, resolution: str = "") -> dict:
    try:
        tid = uuid.UUID(ticket_id)
    except ValueError:
        return {"error": f"Invalid ticket_id '{ticket_id}'."}
    ticket = (await session.execute(select(SupportTicket).where(SupportTicket.brand_id == brand_id, SupportTicket.id == tid))).scalar_one_or_none()
    if not ticket:
        return {"error": f"No ticket '{ticket_id}' found for this brand."}

    ticket.status = status
    if resolution:
        ticket.resolution = resolution
    ticket.updated_at = datetime.now(timezone.utc)
    await session.flush()

    session.add(SupportAction(brand_id=brand_id, ticket_id=tid, action_type=f"STATUS_{status.upper()}", result={"resolution": resolution}))
    await session.flush()
    return {"ticket_id": ticket_id, "status": status}


async def record_refund(
    session: AsyncSession, brand_id: str, order_id: str, amount: float, reason: str,
    shopify_refund_id: Optional[str] = None, ticket_id: Optional[str] = None, status: str = "issued",
) -> dict:
    logger.info("Recording refund for brand=%s order=%s amount=%.2f status=%s", brand_id, order_id, amount, status)
    tid = None
    if ticket_id:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError:
            tid = None

    record = RefundRecord(
        brand_id=brand_id, shopify_order_id=int(order_id) if str(order_id).isdigit() else 0,
        amount=amount, reason=reason,
        shopify_refund_id=int(shopify_refund_id) if shopify_refund_id and str(shopify_refund_id).isdigit() else None,
        ticket_id=tid, status=status,
    )
    session.add(record)
    await session.flush()

    if status == "pending_approval":
        from notifications.dispatch import notify_approval_required  # local import, avoids load-time cycles
        try:
            await notify_approval_required(
                brand_id, "Refund",
                f"Refund order #{order_id} — {amount:.2f}",
                f"Reason: {reason}",
            )
        except Exception:
            logger.exception("Refund approval notification failed for brand=%s", brand_id)

    if tid:
        session.add(SupportAction(brand_id=brand_id, ticket_id=tid, action_type="REFUND_" + status.upper(), result={"amount": amount, "reason": reason}))
        await session.flush()

    return {"refund_record_id": str(record.id), "order_id": order_id, "amount": amount, "status": status}


async def create_exchange(session: AsyncSession, brand_id: str, order_id: str, original_sku: str, new_sku: str, ticket_id: Optional[str] = None) -> dict:
    logger.info("Creating exchange for brand=%s order=%s %s -> %s", brand_id, order_id, original_sku, new_sku)
    tid = None
    if ticket_id:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError:
            tid = None

    record = ExchangeRecord(
        brand_id=brand_id, shopify_order_id=int(order_id) if str(order_id).isdigit() else 0,
        original_sku=original_sku, new_sku=new_sku, status="pending", ticket_id=tid,
    )
    session.add(record)
    await session.flush()

    from notifications.dispatch import notify_approval_required  # local import, avoids load-time cycles
    try:
        await notify_approval_required(
            brand_id, "Exchange",
            f"Exchange {original_sku} → {new_sku} (order #{order_id})",
            "Customer exchange awaiting approval.",
        )
    except Exception:
        logger.exception("Exchange approval notification failed for brand=%s", brand_id)

    if tid:
        session.add(SupportAction(brand_id=brand_id, ticket_id=tid, action_type="EXCHANGE_CREATED", result={"original_sku": original_sku, "new_sku": new_sku}))
        await session.flush()

    return {"exchange_record_id": str(record.id), "original_sku": original_sku, "new_sku": new_sku, "status": "pending"}


async def create_support_insight(session: AsyncSession, brand_id: str, category: str, severity: str, message: str) -> dict:
    logger.info("Creating support insight for brand=%s category=%s severity=%s", brand_id, category, severity)
    row = SupportInsight(brand_id=brand_id, category=category, severity=severity, message=message, confidence=0.7)
    session.add(row)
    await session.flush()
    return {"insight_id": str(row.id), "category": category, "severity": severity}


async def create_inventory_flag(session: AsyncSession, brand_id: str, sku: str, message: str, severity: str = "medium") -> dict:
    """Same cross-agent-write pattern as Sales' create_inventory_flag —
    writes straight into Inventory's own InventoryAlert table (type=
    'support_flag') so a recurring product complaint shows up alongside
    Inventory's own alerts."""
    alert = InventoryAlert(brand_id=brand_id, type="support_flag", severity=severity, sku=sku, message=message, resolved=False)
    session.add(alert)
    await session.flush()
    return {"alert_id": str(alert.id), "sku": sku, "severity": severity}


async def record_customer_feedback(session: AsyncSession, brand_id: str, customer_id: Optional[str], sentiment: str, feedback: str, category: str = "general") -> None:
    session.add(CustomerFeedback(
        brand_id=brand_id,
        shopify_customer_id=int(customer_id) if customer_id and str(customer_id).isdigit() else None,
        sentiment=sentiment, feedback=feedback, category=category,
    ))
    await session.flush()


async def close_conversation_if_resolved(session: AsyncSession, conversation_id: Optional[str], resolved: bool) -> None:
    if not conversation_id or not resolved:
        return
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        return
    convo = (await session.execute(select(SupportConversation).where(SupportConversation.id == cid))).scalar_one_or_none()
    if convo and convo.status != "closed":
        convo.status = "closed"
        convo.closed_at = datetime.now(timezone.utc)
        await session.flush()


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (routine AI-generated output — every run)
# ══════════════════════════════════════════════════════════════════════════════

async def save_support_insights(session: AsyncSession, brand_id: str, insights: list[dict]) -> None:
    logger.info("Saving %d support insights for brand=%s", len(insights), brand_id)
    for i in insights:
        session.add(SupportInsight(
            brand_id=brand_id, category=i.get("category", "pattern"),
            severity=i.get("severity", "low"), message=i.get("message", ""),
            confidence=i.get("confidence", 0.5),
        ))
    await session.flush()


async def log_execution(session: AsyncSession, brand_id: str, agent: str, task_type: str, status: str,
                         duration_ms: float, tools_used: list[str], token_usage: dict, summary: str) -> None:
    from db import crud_common
    await crud_common.log_execution(session, brand_id, agent, task_type, status, duration_ms, tools_used, token_usage, summary)


async def save_agent_memory(session: AsyncSession, brand_id: str, agent: str, content: str, kind: str = "run_summary") -> None:
    """Structured copy in Postgres (audit trail) + semantic copy in Chroma
    (so future runs can retrieve it by meaning, see
    agents/customer_support/memory.py)."""
    from db import crud_common
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.customer_support import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_tickets(session: AsyncSession, brand_id: str, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    stmt = select(SupportTicket).where(SupportTicket.brand_id == brand_id)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    stmt = stmt.order_by(SupportTicket.created_at.desc()).limit(limit)
    return [
        {
            "id": str(t.id), "issue_type": t.issue_type, "priority": t.priority, "status": t.status,
            "shopify_customer_id": t.shopify_customer_id, "shopify_order_id": t.shopify_order_id,
            "resolution": t.resolution, "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat(),
        }
        for t in (await session.execute(stmt)).scalars().all()
    ]


async def list_conversations(session: AsyncSession, brand_id: str, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    stmt = select(SupportConversation).where(SupportConversation.brand_id == brand_id)
    if status:
        stmt = stmt.where(SupportConversation.status == status)
    stmt = stmt.order_by(SupportConversation.last_message_at.desc()).limit(limit)
    return [
        {"id": str(c.id), "channel": c.channel, "external_thread_id": c.external_thread_id,
         "status": c.status, "started_at": c.started_at.isoformat(), "last_message_at": c.last_message_at.isoformat()}
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def list_conversation_messages(session: AsyncSession, brand_id: str, conversation_id: str) -> list[dict]:
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        return []
    stmt = select(SupportMessage).where(SupportMessage.brand_id == brand_id, SupportMessage.conversation_id == cid).order_by(SupportMessage.created_at.asc())
    return [{"sender": m.sender, "content": m.content, "created_at": m.created_at.isoformat()} for m in (await session.execute(stmt)).scalars().all()]


async def list_refunds(session: AsyncSession, brand_id: str, limit: int = 50) -> list[dict]:
    stmt = select(RefundRecord).where(RefundRecord.brand_id == brand_id).order_by(RefundRecord.created_at.desc()).limit(limit)
    return [
        {"id": str(r.id), "shopify_order_id": r.shopify_order_id, "amount": r.amount, "reason": r.reason,
         "status": r.status, "created_at": r.created_at.isoformat()}
        for r in (await session.execute(stmt)).scalars().all()
    ]


async def list_exchanges(session: AsyncSession, brand_id: str, limit: int = 50) -> list[dict]:
    stmt = select(ExchangeRecord).where(ExchangeRecord.brand_id == brand_id).order_by(ExchangeRecord.created_at.desc()).limit(limit)
    return [
        {"id": str(e.id), "shopify_order_id": e.shopify_order_id, "original_sku": e.original_sku,
         "new_sku": e.new_sku, "status": e.status, "created_at": e.created_at.isoformat()}
        for e in (await session.execute(stmt)).scalars().all()
    ]


async def list_support_insights(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(SupportInsight).where(SupportInsight.brand_id == brand_id).order_by(SupportInsight.created_at.desc()).limit(limit)
    return [
        {"id": str(i.id), "category": i.category, "severity": i.severity, "message": i.message,
         "confidence": i.confidence, "created_at": i.created_at.isoformat()}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def list_customer_feedback(session: AsyncSession, brand_id: str, limit: int = 50) -> list[dict]:
    stmt = select(CustomerFeedback).where(CustomerFeedback.brand_id == brand_id).order_by(CustomerFeedback.created_at.desc()).limit(limit)
    return [
        {"id": str(f.id), "shopify_customer_id": f.shopify_customer_id, "sentiment": f.sentiment,
         "feedback": f.feedback, "category": f.category, "created_at": f.created_at.isoformat()}
        for f in (await session.execute(stmt)).scalars().all()
    ]

# ══════════════════════════════════════════════════════════════════════════════
# Webhook routing — WhatsApp phone_number_id / Instagram page id -> brand_id.
# Used by api/routers/customer_support_webhook.py to route an inbound Meta
# webhook to the right brand. Both keys are unique-indexed columns on
# Brand (see db/models.py) rather than a separate junction table —
# Instagram already stored instagram_page_id on Brand from the OAuth
# callback (api/routers/oauth.py::meta_oauth_callback), so reusing that
# column as the lookup key (now with a real uniqueness guarantee) avoids
# a redundant join for what's fundamentally 1:1 data. whatsapp_phone_number_id
# is the WhatsApp analogue — set via PUT /api/v1/brands/me once a brand
# connects their own WhatsApp Business phone number (no OAuth flow exists
# for that yet — see api/routers/brands.py).
# ══════════════════════════════════════════════════════════════════════════════

async def get_brand_id_by_whatsapp_phone_number_id(session: AsyncSession, phone_number_id: str) -> Optional[str]:
    stmt = select(Brand.brand_id).where(Brand.whatsapp_phone_number_id == phone_number_id, Brand.is_active == True)  # noqa: E712
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_brand_id_by_instagram_page_id(session: AsyncSession, ig_page_id: str) -> Optional[str]:
    stmt = select(Brand.brand_id).where(Brand.instagram_page_id == ig_page_id, Brand.is_active == True)  # noqa: E712
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_brand_whatsapp_phone_number_id(session: AsyncSession, brand_id: str) -> Optional[str]:
    """Used by agents/customer_support/tools.py when sending a WhatsApp
    reply, so it sends FROM the same number the customer messaged rather
    than defaulting to FashionOS's own platform-level number."""
    stmt = select(Brand.whatsapp_phone_number_id).where(Brand.brand_id == brand_id)
    return (await session.execute(stmt)).scalar_one_or_none()