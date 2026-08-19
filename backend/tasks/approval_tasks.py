"""
Approval Center — background execution.

When the brand owner approves an item in the Approval Center
(api/routers/approvals.py), the status flip alone used to be the end of it:
nothing actually placed the PO, issued the refund, or told the customer
anything. This module closes that gap.

Design — deterministic executors + one agent-backed executor + a sweep:

  reorder approved  -> create_purchase_order (deterministic, reuses
                       db/crud_supplier.create_purchase_order), link the
                       reorder recommendation to the new PO, mark it
                       "ordered", and notify the supplier with the drafted
                       supplier_message.
  quote accepted    -> create_purchase_order from the quote's unit_price,
                       then notify the supplier.
  po approved       -> notify the supplier that the order was confirmed.
  refund approved   -> run the Customer Support Agent
                       (run_customer_support_agent_sync) so it issues the
                       real Shopify refund via create_refund and logs it
                       with record_refund — the refund record only stores
                       order_id + amount, and the correct line_item needs
                       order lookup only that agent's loop does.
  exchange approved -> run the Customer Support Agent to notify the
                       customer their exchange is approved and resolve the
                       related ticket.

Idempotency + safety net: each executor claims the item by writing an
AgentMemory row (kind="approval_execution") before doing work, so a
decision can't be executed twice even if Celery or the request path double-
fires. On failure the claim is marked "failed" (backoff) and a periodic
sweep (celery_app.py beat) re-enqueues any post-decision item without a
fresh claim — so an approve that never executed because the broker was
down still gets picked up. This mirrors the repo's "optional infra,
degrade gracefully" philosophy: if notifications/Shopify/MCP aren't
configured, the executor logs and marks the claim failed instead of
corrupting state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select

from db import crud_supplier as supplier_crud
from db.models import (
    AgentMemory, ExchangeRecord, PurchaseOrder, RefundRecord,
    ReorderRecommendation, SupplierQuote,
)
from db.session import AsyncSessionLocal
from notifications.dispatch import send_email, send_whatsapp
from pipeline import run_customer_support_agent_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Items in these post-decision statuses are "approved but maybe not yet
# executed" — what the sweep looks for.
POST_DECISION = {
    "reorder":  (ReorderRecommendation, ["approved"]),
    "quote":    (SupplierQuote,          ["accepted"]),
    "po":       (PurchaseOrder,          ["approved"]),
    "refund":   (RefundRecord,           ["approved"]),
    "exchange": (ExchangeRecord,         ["completed"]),
}

# An approved item that never claims gets re-enqueued by the sweep. Once a
# claim exists, backoff governs how long until a failed/stuck claim can be
# retried (mirrors Celery-style retry without making every task retry-happy).
RUNNING_STALE_MINUTES = 30   # claim marked running but older than this -> reclaim (worker likely died)
FAILED_BACKOFF_HOURS   = 1   # claim marked failed -> wait at least this before retrying


# ══════════════════════════════════════════════════════════════════════════════
# Claim bookkeeping (AgentMemory kind="approval_execution")
# ══════════════════════════════════════════════════════════════════════════════

async def _find_claim(session, brand_id: str, kind: str, entity_id: str) -> Optional[AgentMemory]:
    stmt = (
        select(AgentMemory)
        .where(AgentMemory.brand_id == brand_id,
               AgentMemory.agent == "approvals",
               AgentMemory.kind == "approval_execution")
        .order_by(AgentMemory.created_at.desc())
        .limit(50)
    )
    for row in (await session.execute(stmt)).scalars().all():
        try:
            data = json.loads(row.content)
        except (TypeError, ValueError):
            continue
        if data.get("kind") == kind and str(data.get("id")) == str(entity_id):
            return row
    return None


async def _claim(session, brand_id: str, kind: str, entity_id: str) -> Optional[AgentMemory]:
    """Claim the right to execute. Returns None when the item should be
    skipped (already done, or in retry backoff)."""
    now = datetime.now(timezone.utc)
    existing = await _find_claim(session, brand_id, kind, entity_id)

    if existing is not None:
        try:
            data = json.loads(existing.content)
        except (TypeError, ValueError):
            data = {}
        status = data.get("status")
        claimed_at = None
        try:
            claimed_at = datetime.fromisoformat(data.get("claimed_at", ""))
        except (TypeError, ValueError):
            pass

        if status == "done":
            return None
        if status == "running" and claimed_at and (now - claimed_at) < timedelta(minutes=RUNNING_STALE_MINUTES):
            return None
        if status == "failed" and claimed_at and (now - claimed_at) < timedelta(hours=FAILED_BACKOFF_HOURS):
            return None

        # Reclaim a stale/failed claim.
        existing.content = json.dumps({
            "kind": kind, "id": entity_id, "status": "running",
            "claimed_at": now.isoformat(), "detail": "",
        })
        return existing

    claim = AgentMemory(
        brand_id=brand_id, agent="approvals", kind="approval_execution",
        content=json.dumps({
            "kind": kind, "id": entity_id, "status": "running",
            "claimed_at": now.isoformat(), "detail": "",
        }),
    )
    session.add(claim)
    return claim


async def _finish(session, claim: AgentMemory, status: str, detail: Any) -> None:
    data = {}
    try:
        data = json.loads(claim.content)
    except (TypeError, ValueError):
        pass
    claim.content = json.dumps({
        "kind": data.get("kind"), "id": data.get("id"), "status": status,
        "claimed_at": data.get("claimed_at") or datetime.now(timezone.utc).isoformat(),
        "detail": detail if isinstance(detail, str) else json.dumps(detail, default=str)[:4000],
    })


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _reference_unit_cost(session, brand_id: str, sku: str, supplier_id: Optional[str]) -> Optional[float]:
    """Best-effort unit price for a reorder rec from the latest quote for
    that SKU (+ supplier when known). Falls back to None -> PO without a
    unit cost."""
    stmt = (
        select(SupplierQuote)
        .where(SupplierQuote.brand_id == brand_id,
               SupplierQuote.sku == sku,
               SupplierQuote.status.in_(["accepted", "estimated"]))
        .order_by(SupplierQuote.created_at.desc())
        .limit(10)
    )
    for q in (await session.execute(stmt)).scalars().all():
        if supplier_id and str(q.supplier_id) != str(supplier_id):
            continue
        return q.unit_price
    return None


async def _notify_supplier(session, brand_id: str, supplier_id: str, subject: str, message: str) -> dict:
    supplier = await supplier_crud.get_supplier_by_id(session, brand_id, supplier_id)
    if not supplier:
        return {"error": "supplier not found"}
    results = []
    if supplier.get("contact_whatsapp"):
        results.append(await send_whatsapp(supplier["contact_whatsapp"], message))
    if supplier.get("contact_email"):
        results.append(await send_email(supplier["contact_email"], f"[FashionOS] {subject}", message))
    if not results:
        return {"error": f"No contact info on file for supplier '{supplier['name']}'."}
    return {"sent": any(r.get("sent") for r in results), "supplier": supplier["name"], "results": results}


def _run_claim(brand_id: str, kind: str, entity_id: str, work):
    """Shared executor body: claim -> run `work(session, row)` -> mark done.
    `work` must raise on failure; the claim is then marked failed and the
    exception propagates (Celery logs it, the sweep retries later)."""
    async def _body():
        async with AsyncSessionLocal() as session:
            claim = await _claim(session, brand_id, kind, entity_id)
            if claim is None:
                logger.info("[approval:exec] %s %s already claimed/skipped for brand=%s", kind, entity_id, brand_id)
                return {"status": "skipped"}
            await session.commit()  # persist the claim before doing real work

            try:
                result = await work(session)
                await _finish(session, claim, "done", result)
                await session.commit()
                return {"status": "done", **result}
            except Exception as e:
                logger.exception("[approval:exec] %s %s failed for brand=%s", kind, entity_id, brand_id)
                await _finish(session, claim, "failed", str(e))
                await session.commit()
                raise

    return asyncio.run(_body())


# ══════════════════════════════════════════════════════════════════════════════
# Executors (one Celery task per kind)
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="tasks.approval_tasks.execute_reorder_approval")
def execute_reorder_approval(brand_id: str, reorder_id: str) -> dict:
    logger.info("Celery task execute_reorder_approval started for brand=%s reorder=%s", brand_id, reorder_id)

    async def _work(session):
        row = (await session.execute(
            select(ReorderRecommendation).where(
                ReorderRecommendation.brand_id == brand_id,
                ReorderRecommendation.id == uuid_mod.UUID(reorder_id),
            )
        )).scalar_one_or_none()
        if row is None:
            raise RuntimeError(f"Reorder recommendation {reorder_id} not found.")
        if not row.supplier_id:
            raise RuntimeError(f"Reorder {row.sku} has no supplier assigned — cannot place an order.")

        unit_cost = await _reference_unit_cost(session, brand_id, row.sku, str(row.supplier_id))
        result = await supplier_crud.create_purchase_order(
            session, brand_id, sku=row.sku, supplier_id=str(row.supplier_id),
            quantity=row.quantity, unit_cost=unit_cost,
        )
        if "error" in result:
            raise RuntimeError(result["error"])

        row.status = "ordered"
        row.purchase_order_id = uuid_mod.UUID(result["purchase_order_id"])

        notify = await _notify_supplier(
            session, brand_id, str(row.supplier_id),
            f"Purchase order — {row.sku}",
            row.supplier_message or f"Please proceed with our order for {row.sku} × {row.quantity}.",
        )
        return {"purchase_order_id": result["purchase_order_id"], "notified": notify}

    return _run_claim(brand_id, "reorder", reorder_id, _work)


@celery_app.task(name="tasks.approval_tasks.execute_quote_acceptance")
def execute_quote_acceptance(brand_id: str, quote_id: str) -> dict:
    logger.info("Celery task execute_quote_acceptance started for brand=%s quote=%s", brand_id, quote_id)

    async def _work(session):
        row = (await session.execute(
            select(SupplierQuote).where(
                SupplierQuote.brand_id == brand_id,
                SupplierQuote.id == uuid_mod.UUID(quote_id),
            )
        )).scalar_one_or_none()
        if row is None:
            raise RuntimeError(f"Supplier quote {quote_id} not found.")

        result = await supplier_crud.create_purchase_order(
            session, brand_id, sku=row.sku, supplier_id=str(row.supplier_id),
            quantity=row.quantity, unit_cost=row.unit_price,
        )
        if "error" in result:
            raise RuntimeError(result["error"])

        notify = await _notify_supplier(
            session, brand_id, str(row.supplier_id),
            f"Purchase order — {row.sku}",
            f"Please proceed with our order for {row.sku} × {row.quantity} at the accepted unit price of {row.unit_price:.2f}.",
        )
        return {"purchase_order_id": result["purchase_order_id"], "notified": notify}

    return _run_claim(brand_id, "quote", quote_id, _work)


@celery_app.task(name="tasks.approval_tasks.execute_po_approval")
def execute_po_approval(brand_id: str, po_id: str) -> dict:
    logger.info("Celery task execute_po_approval started for brand=%s po=%s", brand_id, po_id)

    async def _work(session):
        row = (await session.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.brand_id == brand_id,
                PurchaseOrder.id == uuid_mod.UUID(po_id),
            )
        )).scalar_one_or_none()
        if row is None:
            raise RuntimeError(f"Purchase order {po_id} not found.")
        if not row.supplier_id:
            raise RuntimeError(f"PO {po_id} has no supplier assigned.")

        notify = await _notify_supplier(
            session, brand_id, str(row.supplier_id),
            f"Purchase order confirmed — {row.sku}",
            f"Our purchase order for {row.sku} × {row.ordered_quantity} has been approved. "
            f"Please confirm receipt and the delivery timeline.",
        )
        return {"notified": notify}

    return _run_claim(brand_id, "po", po_id, _work)


@celery_app.task(name="tasks.approval_tasks.execute_refund_approval")
def execute_refund_approval(brand_id: str, refund_id: str) -> dict:
    logger.info("Celery task execute_refund_approval started for brand=%s refund=%s", brand_id, refund_id)

    async def _load() -> dict:
        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                select(RefundRecord).where(
                    RefundRecord.brand_id == brand_id,
                    RefundRecord.id == uuid_mod.UUID(refund_id),
                )
            )).scalar_one_or_none()
            if row is None:
                return {}
            return {
                "order_id": str(row.shopify_order_id), "amount": row.amount,
                "reason": row.reason or "Approved by brand owner.",
                "ticket_id": str(row.ticket_id) if row.ticket_id else None,
                "refund_id": str(row.id),
            }

    def _work(session):
        data = asyncio.run(_load())
        if not data:
            raise RuntimeError(f"Refund record {refund_id} not found.")
        task = {
            "task_type": "execute_approved_refund",
            "priority": "high",
            "trigger": "approval_execution",
            "refund_id": refund_id,
            "order_id": data["order_id"],
            "refund_amount": data["amount"],
            "reason": data["reason"],
            "ticket_id": data["ticket_id"],
            "issue": (
                f"The brand owner approved a refund of {data['amount']:.2f} for order "
                f"#{data['order_id']}. Issue it now via create_refund (look up the order's "
                f"line items first), then log it with record_refund using status='issued'. "
                f"Notify the customer it's done."
            ),
        }
        res = run_customer_support_agent_sync(brand_id, task)
        return {"agent_summary": res.get("summary", ""), "ticket": res.get("ticket", {})}

    async def _wrapper(session):
        return _work(session)

    return _run_claim(brand_id, "refund", refund_id, _wrapper)


@celery_app.task(name="tasks.approval_tasks.execute_exchange_approval")
def execute_exchange_approval(brand_id: str, exchange_id: str) -> dict:
    logger.info("Celery task execute_exchange_approval started for brand=%s exchange=%s", brand_id, exchange_id)

    async def _load() -> dict:
        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                select(ExchangeRecord).where(
                    ExchangeRecord.brand_id == brand_id,
                    ExchangeRecord.id == uuid_mod.UUID(exchange_id),
                )
            )).scalar_one_or_none()
            if row is None:
                return {}
            return {
                "order_id": str(row.shopify_order_id), "original_sku": row.original_sku,
                "new_sku": row.new_sku, "ticket_id": str(row.ticket_id) if row.ticket_id else None,
                "exchange_id": str(row.id),
            }

    def _work(session):
        data = asyncio.run(_load())
        if not data:
            raise RuntimeError(f"Exchange record {exchange_id} not found.")
        task = {
            "task_type": "execute_approved_exchange",
            "priority": "high",
            "trigger": "approval_execution",
            "exchange_id": exchange_id,
            "order_id": data["order_id"],
            "original_sku": data["original_sku"],
            "new_sku": data["new_sku"],
            "ticket_id": data["ticket_id"],
            "issue": (
                f"The brand owner approved the exchange of {data['original_sku']} → "
                f"{data['new_sku']} for order #{data['order_id']}. Notify the customer it's "
                f"approved and will be processed, and resolve the related ticket."
            ),
        }
        res = run_customer_support_agent_sync(brand_id, task)
        return {"agent_summary": res.get("summary", ""), "ticket": res.get("ticket", {})}

    async def _wrapper(session):
        return _work(session)

    return _run_claim(brand_id, "exchange", exchange_id, _wrapper)


EXECUTORS = {
    "reorder":  execute_reorder_approval,
    "quote":    execute_quote_acceptance,
    "po":       execute_po_approval,
    "refund":   execute_refund_approval,
    "exchange": execute_exchange_approval,
}


# ══════════════════════════════════════════════════════════════════════════════
# Periodic safety net — re-enqueue anything approved but never executed.
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="tasks.approval_tasks.sweep_unexecuted_approvals")
def sweep_unexecuted_approvals() -> int:
    """Beat job — finds post-decision items (approved/accepted/completed) that
    still have no fresh execution claim and enqueues their executor. The
    executor's own claim/backoff logic makes this safe to run repeatedly."""
    logger.info("Celery task sweep_unexecuted_approvals triggered")

    async def _targets() -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        async with AsyncSessionLocal() as session:
            for kind, (model, statuses) in POST_DECISION.items():
                rows = (await session.execute(
                    select(model).where(model.brand_id.isnot(None), model.status.in_(statuses))
                )).scalars().all()
                for r in rows:
                    out.append((r.brand_id, kind, str(r.id)))
        return out

    targets = asyncio.run(_targets())
    enqueued = 0
    for brand_id, kind, entity_id in targets:
        try:
            EXECUTORS[kind].delay(brand_id, entity_id)
            enqueued += 1
        except Exception:
            logger.exception("Sweep failed to enqueue %s %s for brand=%s", kind, entity_id, brand_id)
    logger.info("Sweep enqueued %d of %d post-decision items", enqueued, len(targets))
    return enqueued
