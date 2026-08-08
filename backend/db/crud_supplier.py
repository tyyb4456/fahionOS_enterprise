"""
Supplier Agent — read/write layer.

Supplier Agent is the brand's Procurement / Supply Chain Manager: it reads
Inventory's unresolved sourcing needs (open alerts + reorder
recommendations Inventory itself couldn't or didn't order), finds and
scores suppliers, requests/compares quotes, negotiates, creates purchase
orders, tracks shipments, and updates supplier performance scores.

Table ownership:
  - reads but doesn't own: ProductVariant (Shopify catalog mirror, for
    cost_price reference pricing), InventoryAlert/ReorderRecommendation
    (Inventory Agent's own outputs — sourcing triggers).
  - shared write with Inventory Agent: PurchaseOrder. Inventory can still
    place its own POs directly (agents/inventory/tools.py::create_purchase_order,
    unchanged); Supplier Agent writes into the SAME table when it closes a
    sourcing loop itself — the same "shared Postgres, no duplicate tables"
    pattern already used by Sales' create_inventory_flag (writes into
    Inventory's own InventoryAlert table).
  - shared write on Supplier: this agent is the one that actually updates
    reliability_score/quality_score based on real delivery/quality
    outcomes; Inventory only ever reads Supplier, never writes it.
  - owns outright: SupplierQuote, NegotiationRecord, ShipmentTracking,
    SupplierInsight, + the shared AgentExecutionLog/AgentMemory via
    db/crud_common.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    InventoryAlert, NegotiationRecord, ProductVariant, PurchaseOrder,
    ReorderRecommendation, ShipmentTracking, Supplier, SupplierInsight,
    SupplierQuote,
)

from agents.supplier import analytics

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(session: AsyncSession, brand_id: str) -> dict[str, Any]:
    logger.info("Building supplier context for brand=%s", brand_id)
    sourcing_needs = await _sourcing_needs(session, brand_id)
    open_alerts = await _open_high_severity_alerts(session, brand_id)
    suppliers = await _all_suppliers(session, brand_id)
    open_pos = await _open_purchase_orders(session, brand_id)
    recent_quotes = await _recent_quotes(session, brand_id)
    recent_negotiations = await _recent_negotiations(session, brand_id)

    return {
        "sourcing_needs": sourcing_needs,
        "open_inventory_alerts": open_alerts,
        "suppliers": suppliers,
        "open_purchase_orders": open_pos,
        "recent_quotes": recent_quotes,
        "recent_negotiations": recent_negotiations,
    }


async def _sourcing_needs(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    """Inventory's own reorder recommendations it flagged but left as
    pending_approval — confirmed sourcing needs for this agent to pick up,
    instead of recomputing forecasts itself (Inventory already owns
    forecast_sku_demand)."""
    stmt = (
        select(ReorderRecommendation)
        .where(ReorderRecommendation.brand_id == brand_id, ReorderRecommendation.status == "pending_approval")
        .order_by(ReorderRecommendation.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "sku": r.sku, "quantity": r.quantity, "urgency": r.urgency, "reason": r.reason,
            "supplier_id": str(r.supplier_id) if r.supplier_id else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in (await session.execute(stmt)).scalars().all()
    ]


async def _open_high_severity_alerts(session: AsyncSession, brand_id: str, limit: int = 15) -> list[dict]:
    stmt = (
        select(InventoryAlert)
        .where(
            InventoryAlert.brand_id == brand_id, InventoryAlert.resolved == False,  # noqa: E712
            InventoryAlert.severity.in_(["high", "critical"]),
        )
        .order_by(InventoryAlert.created_at.desc())
        .limit(limit)
    )
    return [
        {"type": a.type, "severity": a.severity, "sku": a.sku, "message": a.message}
        for a in (await session.execute(stmt)).scalars().all()
    ]


async def _all_suppliers(session: AsyncSession, brand_id: str) -> list[dict]:
    stmt = select(Supplier).where(Supplier.brand_id == brand_id)
    return [
        {
            "supplier_id": str(s.id), "name": s.name, "lead_time_days": s.lead_time_days,
            "minimum_order_qty": s.minimum_order_qty, "reliability_score": s.reliability_score,
            "quality_score": s.quality_score,
        }
        for s in (await session.execute(stmt)).scalars().all()
    ]


async def _open_purchase_orders(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.brand_id == brand_id, PurchaseOrder.status.in_(["pending", "shipped"]))
        .order_by(PurchaseOrder.expected_delivery.asc())
        .limit(limit)
    )
    pos = (await session.execute(stmt)).scalars().all()
    result = []
    for po in pos:
        tracking_stmt = (
            select(ShipmentTracking)
            .where(ShipmentTracking.purchase_order_id == po.id)
            .order_by(ShipmentTracking.last_updated.desc())
            .limit(1)
        )
        tracking = (await session.execute(tracking_stmt)).scalar_one_or_none()
        result.append({
            "purchase_order_id": str(po.id), "sku": po.sku,
            "supplier_id": str(po.supplier_id) if po.supplier_id else None,
            "quantity": po.ordered_quantity, "total_cost": po.total_cost, "status": po.status,
            "expected_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
            "shipment_status": tracking.status if tracking else None,
            "current_location": tracking.current_location if tracking else None,
        })
    return result


async def _recent_quotes(session: AsyncSession, brand_id: str, limit: int = 15) -> list[dict]:
    stmt = select(SupplierQuote).where(SupplierQuote.brand_id == brand_id).order_by(SupplierQuote.created_at.desc()).limit(limit)
    return [
        {
            "sku": q.sku, "supplier_id": str(q.supplier_id), "unit_price": q.unit_price,
            "quantity": q.quantity, "moq": q.moq, "lead_time_days": q.lead_time_days, "status": q.status,
        }
        for q in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_negotiations(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    stmt = select(NegotiationRecord).where(NegotiationRecord.brand_id == brand_id).order_by(NegotiationRecord.created_at.desc()).limit(limit)
    return [
        {
            "supplier_id": str(n.supplier_id), "sku": n.sku, "initial_offer": n.initial_offer,
            "counter_offer": n.counter_offer, "final_price": n.final_price, "result": n.result,
        }
        for n in (await session.execute(stmt)).scalars().all()
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/supplier/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def find_suppliers(session: AsyncSession, brand_id: str, query: str = "", limit: int = 10) -> list[dict]:
    stmt = select(Supplier).where(Supplier.brand_id == brand_id)
    if query:
        stmt = stmt.where(Supplier.name.ilike(f"%{query}%"))
    stmt = stmt.limit(limit)
    return [
        {
            "supplier_id": str(s.id), "name": s.name, "lead_time_days": s.lead_time_days,
            "minimum_order_qty": s.minimum_order_qty, "reliability_score": s.reliability_score,
            "quality_score": s.quality_score, "contact_email": s.contact_email,
            "contact_whatsapp": s.contact_whatsapp, "notes": s.notes,
        }
        for s in (await session.execute(stmt)).scalars().all()
    ]


async def get_supplier_by_id(session: AsyncSession, brand_id: str, supplier_id: str) -> Optional[dict]:
    try:
        sid = uuid.UUID(supplier_id)
    except ValueError:
        return None
    stmt = select(Supplier).where(Supplier.brand_id == brand_id, Supplier.id == sid)
    s = (await session.execute(stmt)).scalar_one_or_none()
    if not s:
        return None
    return {
        "supplier_id": str(s.id), "name": s.name, "lead_time_days": s.lead_time_days,
        "minimum_order_qty": s.minimum_order_qty, "reliability_score": s.reliability_score,
        "quality_score": s.quality_score, "contact_email": s.contact_email,
        "contact_whatsapp": s.contact_whatsapp, "notes": s.notes,
    }


async def get_reference_cost_price(session: AsyncSession, brand_id: str, sku: str) -> Optional[float]:
    """Best-effort reference price for a SKU, from our own product cost
    data — used to bias request_quotes' estimate instead of guessing blind."""
    stmt = select(ProductVariant.cost_price).where(ProductVariant.brand_id == brand_id, ProductVariant.sku == sku)
    return (await session.execute(stmt)).scalar_one_or_none()


# ── request_quotes / compare_quotes ───────────────────────────────────────

async def create_quote_estimate(
    session: AsyncSession, brand_id: str, supplier_id: str, sku: str, quantity: int,
    reference_unit_price: Optional[float],
) -> dict:
    supplier = await get_supplier_by_id(session, brand_id, supplier_id)
    if not supplier:
        return {"error": f"No supplier with id '{supplier_id}' on file."}

    estimate = analytics.estimate_quote(
        reference_unit_price, quantity, supplier["minimum_order_qty"], supplier["lead_time_days"],
    )
    row = SupplierQuote(
        brand_id=brand_id, supplier_id=uuid.UUID(supplier_id), sku=sku, quantity=quantity,
        unit_price=estimate["unit_price"], moq=supplier["minimum_order_qty"],
        lead_time_days=supplier["lead_time_days"],
        valid_until=date.today() + timedelta(days=14), status="estimated",
    )
    session.add(row)
    await session.flush()
    return {
        "quote_id": str(row.id), "supplier_id": supplier_id, "supplier_name": supplier["name"],
        "sku": sku, **estimate,
    }


async def compare_quotes_for_sku(session: AsyncSession, brand_id: str, sku: str) -> list[dict]:
    stmt = select(SupplierQuote).where(SupplierQuote.brand_id == brand_id, SupplierQuote.sku == sku).order_by(SupplierQuote.created_at.desc())
    quotes = (await session.execute(stmt)).scalars().all()
    candidates = []
    for q in quotes:
        supplier = await get_supplier_by_id(session, brand_id, str(q.supplier_id))
        if not supplier:
            continue
        candidates.append({
            "quote_id": str(q.id), "supplier_id": str(q.supplier_id), "name": supplier["name"],
            "unit_price": q.unit_price, "lead_time_days": q.lead_time_days,
            "reliability_score": supplier["reliability_score"], "quality_score": supplier["quality_score"],
        })
    target = min((c["unit_price"] for c in candidates), default=None)
    return analytics.rank_suppliers(candidates, target_price=target)


# ── create_purchase_order (operational write — shared table with Inventory) ─

async def create_purchase_order(
    session: AsyncSession, brand_id: str, sku: str, supplier_id: str, quantity: int,
    unit_cost: Optional[float] = None, payment_terms: str = "",
) -> dict:
    supplier = await get_supplier_by_id(session, brand_id, supplier_id)
    if not supplier:
        return {"error": f"No supplier with id '{supplier_id}' on file."}

    expected_delivery = date.today() + timedelta(days=supplier["lead_time_days"])
    total_cost = round(unit_cost * quantity, 2) if unit_cost is not None else None

    po = PurchaseOrder(
        brand_id=brand_id, supplier_id=uuid.UUID(supplier_id), sku=sku,
        ordered_quantity=quantity, expected_delivery=expected_delivery, status="pending",
        unit_cost=unit_cost, total_cost=total_cost, payment_terms=payment_terms or None,
    )
    session.add(po)
    await session.flush()

    session.add(ShipmentTracking(
        brand_id=brand_id, purchase_order_id=po.id, status="manufacturing",
        estimated_arrival=expected_delivery,
    ))
    await session.flush()

    return {
        "purchase_order_id": str(po.id), "sku": sku, "supplier_id": supplier_id,
        "supplier_name": supplier["name"], "quantity": quantity, "unit_cost": unit_cost,
        "total_cost": total_cost, "expected_delivery": expected_delivery.isoformat(), "status": "pending",
    }


# ── shipment tracking ──────────────────────────────────────────────────────

async def upsert_shipment_status(
    session: AsyncSession, brand_id: str, purchase_order_id: str, status: str,
    current_location: Optional[str] = None, estimated_arrival: Optional[str] = None,
    tracking_number: Optional[str] = None, carrier: Optional[str] = None,
) -> dict:
    try:
        po_uuid = uuid.UUID(purchase_order_id)
    except ValueError:
        return {"error": f"Invalid purchase_order_id '{purchase_order_id}'."}

    po = (await session.execute(
        select(PurchaseOrder).where(PurchaseOrder.brand_id == brand_id, PurchaseOrder.id == po_uuid)
    )).scalar_one_or_none()
    if not po:
        return {"error": f"No purchase order '{purchase_order_id}' found for this brand."}

    tracking = (await session.execute(
        select(ShipmentTracking).where(ShipmentTracking.purchase_order_id == po_uuid).order_by(ShipmentTracking.last_updated.desc()).limit(1)
    )).scalar_one_or_none()

    parsed_eta = None
    if estimated_arrival:
        try:
            parsed_eta = date.fromisoformat(estimated_arrival)
        except ValueError:
            parsed_eta = None

    if tracking is None:
        tracking = ShipmentTracking(brand_id=brand_id, purchase_order_id=po_uuid, status=status)
        session.add(tracking)

    tracking.status = status
    tracking.current_location = current_location or tracking.current_location
    tracking.estimated_arrival = parsed_eta or tracking.estimated_arrival
    tracking.tracking_number = tracking_number or tracking.tracking_number
    tracking.carrier = carrier or tracking.carrier

    delivered_on_time = None
    if status == "delivered":
        today = date.today()
        po.status = "received"
        po.actual_delivery = today
        if po.expected_delivery:
            delivered_on_time = today <= po.expected_delivery

    await session.flush()
    return {
        "purchase_order_id": purchase_order_id, "status": status,
        "current_location": tracking.current_location,
        "estimated_arrival": tracking.estimated_arrival.isoformat() if tracking.estimated_arrival else None,
        "delivered_on_time": delivered_on_time,
        "supplier_id": str(po.supplier_id) if po.supplier_id else None,
    }


# ── negotiation ─────────────────────────────────────────────────────────────

async def record_negotiation(
    session: AsyncSession, brand_id: str, supplier_id: str, sku: Optional[str],
    initial_offer: Optional[float], counter_offer: Optional[float], final_price: Optional[float],
    result: str, notes: str,
) -> dict:
    row = NegotiationRecord(
        brand_id=brand_id, supplier_id=uuid.UUID(supplier_id), sku=sku,
        initial_offer=initial_offer, counter_offer=counter_offer, final_price=final_price,
        result=result, notes=notes,
    )
    session.add(row)
    await session.flush()
    return {"negotiation_id": str(row.id), "supplier_id": supplier_id, "result": result}


# ── supplier scoring ─────────────────────────────────────────────────────────

async def update_supplier_score(
    session: AsyncSession, brand_id: str, supplier_id: str,
    delivered_on_time: Optional[bool] = None, quality_issue: Optional[bool] = None,
    note: str = "",
) -> dict:
    try:
        sid = uuid.UUID(supplier_id)
    except ValueError:
        return {"error": f"Invalid supplier_id '{supplier_id}'."}

    supplier = (await session.execute(
        select(Supplier).where(Supplier.brand_id == brand_id, Supplier.id == sid)
    )).scalar_one_or_none()
    if not supplier:
        return {"error": f"No supplier with id '{supplier_id}' on file."}

    if delivered_on_time is not None:
        supplier.reliability_score = analytics.update_reliability_score(supplier.reliability_score, delivered_on_time)
    if quality_issue is not None:
        supplier.quality_score = analytics.update_reliability_score(supplier.quality_score, not quality_issue)

    await session.flush()

    if note:
        session.add(SupplierInsight(
            brand_id=brand_id, supplier_id=sid, category="performance",
            severity="low" if (delivered_on_time is not False and not quality_issue) else "medium",
            message=note, confidence=0.7,
        ))
        await session.flush()

    return {
        "supplier_id": supplier_id, "reliability_score": supplier.reliability_score,
        "quality_score": supplier.quality_score,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (AI-generated intelligence only)
# ══════════════════════════════════════════════════════════════════════════════

async def save_supplier_insights(session: AsyncSession, brand_id: str, insights: list[dict]) -> None:
    logger.info("Saving %d supplier insights for brand=%s", len(insights), brand_id)
    for i in insights:
        supplier_id = i.get("supplier_id")
        session.add(SupplierInsight(
            brand_id=brand_id,
            supplier_id=uuid.UUID(supplier_id) if supplier_id else None,
            category=i.get("category", "performance"), severity=i.get("severity", "low"),
            message=i.get("message", ""), confidence=i.get("confidence", 0.5),
        ))
    await session.flush()


async def log_execution(session: AsyncSession, brand_id: str, agent: str, task_type: str, status: str,
                         duration_ms: float, tools_used: list[str], token_usage: dict, summary: str) -> None:
    from db import crud_common
    await crud_common.log_execution(session, brand_id, agent, task_type, status, duration_ms, tools_used, token_usage, summary)


async def save_agent_memory(session: AsyncSession, brand_id: str, agent: str, content: str, kind: str = "run_summary") -> None:
    """Structured copy in Postgres (audit trail) + semantic copy in Chroma
    (so future runs can retrieve it by meaning, see agents/supplier/memory.py)."""
    from db import crud_common
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.supplier import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_purchase_orders(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    return await _open_purchase_orders(session, brand_id, limit=limit)


async def list_quotes(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    return await _recent_quotes(session, brand_id, limit=limit)


async def list_negotiations(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    return await _recent_negotiations(session, brand_id, limit=limit)


async def list_supplier_insights(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(SupplierInsight).where(SupplierInsight.brand_id == brand_id).order_by(SupplierInsight.created_at.desc()).limit(limit)
    return [
        {
            "id": str(i.id), "supplier_id": str(i.supplier_id) if i.supplier_id else None,
            "category": i.category, "severity": i.severity, "message": i.message,
            "confidence": i.confidence, "created_at": i.created_at.isoformat(),
        }
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def list_suppliers_scored(session: AsyncSession, brand_id: str) -> list[dict]:
    return await _all_suppliers(session, brand_id)