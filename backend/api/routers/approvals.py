"""
FashionOS — Approval Center API
================================
One router that turns the platform's scattered "needs a human decision"
states into a single review queue:

  reorder  (ReorderRecommendation)  status = pending_approval
  refund   (RefundRecord)           status = pending_approval
  exchange (ExchangeRecord)         status = pending
  quote    (SupplierQuote)          status = estimated
  po       (PurchaseOrder)          status = pending

The queue is *derived* from these tables' existing status columns (no new
schema), so an item appears as soon as any agent writes the pending state
and disappears once a decision transitions it. Every decision (approve or
reject, with an optional note) is logged to AgentMemory (kind
"approval_decision") so the owner gets an audit trail, and the owner is
prompted by WhatsApp/email when items enter the queue at creation time (see
the notify_approval_required calls in db/crud_*.py).

Endpoints:
  GET  /api/v1/approvals?kind=&status=   list + counts + recent decisions
  POST /api/v1/approvals/{kind}/{id}/approve   {"note": "..."}
  POST /api/v1/approvals/{kind}/{id}/reject    {"note": "..."}
"""
import json
import logging
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_brand
from db.models import (
    AgentMemory, Brand, ExchangeRecord, PurchaseOrder, ReorderRecommendation,
    RefundRecord, Supplier, SupplierQuote,
)
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])

PENDING_STATUSES = {
    "reorder":  ["pending_approval"],
    "refund":   ["pending_approval"],
    "exchange": ["pending"],
    "quote":    ["estimated"],
    "po":       ["pending"],
}

APPROVE_TO = {
    "reorder":  "approved",
    "refund":   "approved",
    "exchange": "completed",
    "quote":    "accepted",
    "po":       "approved",
}

REJECT_TO = {
    "reorder":  "rejected",
    "refund":   "failed",
    "exchange": "failed",
    "quote":    "rejected",
    "po":       "cancelled",
}

KIND_LABELS = {
    "reorder":  ("Reorder",  "inventory"),
    "refund":   ("Refund",   "customer_support"),
    "exchange": ("Exchange", "customer_support"),
    "quote":    ("Quote",    "supplier"),
    "po":       ("PO",       "supplier"),
}


class DecisionBody(BaseModel):
    note: Optional[str] = None


async def _supplier_names(session: AsyncSession, brand_id: str) -> dict:
    rows = (await session.execute(
        select(Supplier.id, Supplier.name).where(Supplier.brand_id == brand_id)
    )).all()
    return {str(i): n for i, n in rows}


# ── per-kind loaders: return normalized dicts with an `_row` ref for decide ──

async def _load_reorder(session, brand_id, statuses):
    rows = (await session.execute(
        select(ReorderRecommendation)
        .where(ReorderRecommendation.brand_id == brand_id,
               ReorderRecommendation.status.in_(statuses))
        .order_by(ReorderRecommendation.created_at.desc())
    )).scalars().all()
    return [{
        "id": str(r.id), "title": f"Reorder {r.sku} × {r.quantity}",
        "summary": r.reason, "urgency": r.urgency, "amount": None,
        "extra": {"supplier_id": str(r.supplier_id) if r.supplier_id else None,
                  "supplier_message": r.supplier_message},
        "created_at": r.created_at.isoformat(), "_row": r,
    } for r in rows]


async def _load_refund(session, brand_id, statuses):
    rows = (await session.execute(
        select(RefundRecord)
        .where(RefundRecord.brand_id == brand_id,
               RefundRecord.status.in_(statuses))
        .order_by(RefundRecord.created_at.desc())
    )).scalars().all()
    return [{
        "id": str(r.id),
        "title": f"Refund order #{r.shopify_order_id}",
        "summary": r.reason, "urgency": None, "amount": r.amount,
        "extra": {"ticket_id": str(r.ticket_id) if r.ticket_id else None},
        "created_at": r.created_at.isoformat(), "_row": r,
    } for r in rows]


async def _load_exchange(session, brand_id, statuses):
    rows = (await session.execute(
        select(ExchangeRecord)
        .where(ExchangeRecord.brand_id == brand_id,
               ExchangeRecord.status.in_(statuses))
        .order_by(ExchangeRecord.created_at.desc())
    )).scalars().all()
    return [{
        "id": str(r.id),
        "title": f"Exchange {r.original_sku} → {r.new_sku}",
        "summary": f"Order #{r.shopify_order_id}", "urgency": None, "amount": None,
        "extra": {"ticket_id": str(r.ticket_id) if r.ticket_id else None},
        "created_at": r.created_at.isoformat(), "_row": r,
    } for r in rows]


async def _load_quote(session, brand_id, statuses):
    rows = (await session.execute(
        select(SupplierQuote)
        .where(SupplierQuote.brand_id == brand_id,
               SupplierQuote.status.in_(statuses))
        .order_by(SupplierQuote.created_at.desc())
    )).scalars().all()
    names = await _supplier_names(session, brand_id)
    return [{
        "id": str(r.id),
        "title": f"Quote {r.sku} × {r.quantity}",
        "summary": names.get(str(r.supplier_id), "supplier"),
        "urgency": None, "amount": r.unit_price * r.quantity if r.unit_price else None,
        "extra": {"supplier_id": str(r.supplier_id), "moq": r.moq,
                  "lead_time_days": r.lead_time_days},
        "created_at": r.created_at.isoformat(), "_row": r,
    } for r in rows]


async def _load_po(session, brand_id, statuses):
    rows = (await session.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.brand_id == brand_id,
               PurchaseOrder.status.in_(statuses))
        .order_by(PurchaseOrder.created_at.desc())
    )).scalars().all()
    names = await _supplier_names(session, brand_id)
    return [{
        "id": str(r.id),
        "title": f"PO {r.sku} × {r.ordered_quantity}",
        "summary": names.get(str(r.supplier_id), "supplier"),
        "urgency": None, "amount": r.total_cost,
        "extra": {"supplier_id": str(r.supplier_id) if r.supplier_id else None,
                  "expected_delivery": r.expected_delivery.isoformat() if r.expected_delivery else None},
        "created_at": r.created_at.isoformat(), "_row": r,
    } for r in rows]


LOADERS = {
    "reorder":  _load_reorder,
    "refund":   _load_refund,
    "exchange": _load_exchange,
    "quote":    _load_quote,
    "po":       _load_po,
}


async def _recent_executions(session: AsyncSession, brand_id: str, limit: int = 100) -> dict:
    """Map (kind, id) -> latest background-execution claim, so the Decisions
    tab can show what actually happened after an approve (see
    tasks/approval_tasks.py)."""
    rows = (await session.execute(
        select(AgentMemory)
        .where(AgentMemory.brand_id == brand_id,
               AgentMemory.agent == "approvals",
               AgentMemory.kind == "approval_execution")
        .order_by(AgentMemory.created_at.desc())
        .limit(limit)
    )).scalars().all()
    out = {}
    for r in rows:
        try:
            data = json.loads(r.content)
        except (TypeError, ValueError):
            continue
        key = (data.get("kind"), str(data.get("id")))
        if key not in out:
            out[key] = {
                "status": data.get("status"),
                "detail": data.get("detail"),
                "updated_at": r.created_at.isoformat(),
            }
    return out


async def _recent_decisions(session: AsyncSession, brand_id: str, limit: int = 15) -> list[dict]:
    rows = (await session.execute(
        select(AgentMemory)
        .where(AgentMemory.brand_id == brand_id,
               AgentMemory.kind == "approval_decision")
        .order_by(AgentMemory.created_at.desc())
        .limit(limit)
    )).scalars().all()
    executions = await _recent_executions(session, brand_id)
    out = []
    for r in rows:
        try:
            data = json.loads(r.content)
        except (TypeError, ValueError):
            continue
        out.append({
            "kind": data.get("kind"), "id": data.get("id"),
            "title": data.get("title"), "decision": data.get("decision"),
            "note": data.get("note"), "decided_at": r.created_at.isoformat(),
            "execution": executions.get((data.get("kind"), str(data.get("id")))),
        })
    return out


@router.get("")
async def list_approvals(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
    kind: Optional[str] = Query(None),
    status: str = Query("pending", pattern="^(pending|decided)$"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    kinds = [kind] if kind else list(LOADERS.keys())
    if any(k not in LOADERS for k in kinds):
        raise HTTPException(status_code=400, detail=f"Unknown kind. Allowed: {', '.join(LOADERS)}")

    pending = []
    counts = {}
    annotated = []
    for k in kinds:
        label, agent = KIND_LABELS[k]
        items = await LOADERS[k](session, brand.brand_id, PENDING_STATUSES[k])
        counts[k] = len(items)
        for it in items:
            it["kind"] = k
            it["kind_label"] = label
            it["agent"] = agent
            it["status"] = it["_row"].status
            it.pop("_row", None)
            annotated.append(it)

    annotated.sort(key=lambda x: x["created_at"], reverse=True)

    decided = []
    if status == "decided":
        decided = await _recent_decisions(session, brand.brand_id, limit=limit)

    return {
        "pending": annotated[:limit],
        "counts": counts,
        "total_pending": sum(counts.values()),
        "decided": decided,
        "kind_labels": {k: KIND_LABELS[k][0] for k in LOADERS},
    }


@router.get("/counts")
async def approval_counts(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
) -> dict:
    counts = {}
    for k in LOADERS:
        loader = LOADERS[k]
        items = await loader(session, brand.brand_id, PENDING_STATUSES[k])
        counts[k] = len(items)
    return {"counts": counts, "total": sum(counts.values())}


async def _decide(
    brand: Brand,
    session: AsyncSession,
    kind: str,
    entity_id: str,
    decision: str,
    body: DecisionBody,
) -> dict:
    if kind not in LOADERS:
        raise HTTPException(status_code=400, detail=f"Unknown kind. Allowed: {', '.join(LOADERS)}")
    try:
        eid = uuid_mod.UUID(entity_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity id.")

    items = await LOADERS[kind](session, brand.brand_id, PENDING_STATUSES[kind])
    row = next((it["_row"] for it in items if str(it["id"]) == entity_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No {kind} awaiting approval with id {entity_id}.")

    target = (APPROVE_TO if decision == "approve" else REJECT_TO)[kind]
    row.status = target

    title = next(it["title"] for it in items if str(it["id"]) == entity_id)
    session.add(AgentMemory(
        brand_id=brand.brand_id, agent="approvals", kind="approval_decision",
        content=json.dumps({
            "kind": kind, "id": str(row.id), "title": title,
            "decision": decision, "note": body.note or "",
        }),
    ))
    await session.flush()

    from notifications.dispatch import notify_brand_owner  # local import, avoids load-time cycles
    try:
        await notify_brand_owner(
            brand.brand_id, "Approvals",
            f"{decision.title()} — {title}",
            f"{KIND_LABELS[kind][0]} '{title}' was {decision}d"
            + (f".\n\nNote: {body.note}" if body.note else "")
            + "\n\nSee the Approval Center in your dashboard.",
        )
    except Exception:
        logger.exception("Approval decision notification failed")

    # Approving hands the item to a background executor (tasks/approval_tasks.py)
    # that does the real-world work: places the PO + notifies the supplier,
    # issues the Shopify refund, or notifies the customer. Rejecting has nothing
    # to execute. Fire-and-forget: if the broker/Celery is down, the periodic
    # sweep re-enqueues the item later, so a dropped enqueue isn't fatal.
    if decision == "approve":
        from tasks.approval_tasks import EXECUTORS  # local import avoids a load-time cycle
        try:
            EXECUTORS[kind].delay(brand.brand_id, entity_id)
        except Exception:
            logger.exception("Failed to enqueue approval execution for kind=%s id=%s", kind, entity_id)

    return {
        "kind": kind, "id": entity_id, "title": title,
        "decision": decision, "status": target, "note": body.note or "",
    }


@router.post("/{kind}/{entity_id}/approve")
async def approve(
    kind: str,
    entity_id: str,
    body: DecisionBody,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await _decide(brand, session, kind, entity_id, "approve", body)


@router.post("/{kind}/{entity_id}/reject")
async def reject(
    kind: str,
    entity_id: str,
    body: DecisionBody,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await _decide(brand, session, kind, entity_id, "reject", body)
