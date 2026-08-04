"""
Inventory Agent — read/write layer.

Two kinds of tables live here:
  - synced tables (Product, ProductVariant, SalesOrder, OrderLineItem, Return,
    Supplier, Warehouse, PurchaseOrder, SeasonalEvent) — populated by
    api/routers/shopify_webhooks.py (+ manual seed data for suppliers/
    warehouses/seasonal events). Read-only from the agent's perspective.
  - AI-output tables (InventoryForecast, ReorderRecommendation, InventoryAlert,
    AgentExecutionLog, AgentMemory) — written only by the agent. This is what
    "Persistence Layer" means in the design doc: we never duplicate Shopify's
    inventory, we store our own decisions.

create_purchase_order + get_supplier_by_id are the operational additions:
the agent now WRITES a real purchase_orders row (not just a recommendation)
via agents/inventory/tools.py, mid-ReAct-loop, the same way it corrects
Shopify stock via set_inventory_level.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AgentExecutionLog, AgentMemory, InventoryAlert, InventoryForecast,
    OrderLineItem, Product, ProductVariant, PurchaseOrder,
    ReorderRecommendation, SalesOrder, SeasonalEvent, Supplier, Warehouse,
)

LOW_STOCK_THRESHOLD_DEFAULT = 25


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(
    session: AsyncSession,
    brand_id: str,
    low_stock_threshold: int = LOW_STOCK_THRESHOLD_DEFAULT,
    max_products: int = 40,
) -> dict[str, Any]:
    """
    Assemble the snapshot handed to the reasoning loop. Deliberately bounded
    in size (lowest-stock products first, capped lists) — anything beyond
    this the agent can pull with a tool call instead of us dumping the whole
    catalog into the prompt every run.
    """
    variants_stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.brand_id == brand_id, Product.status == "active")
        .order_by(ProductVariant.inventory_quantity.asc())
        .limit(max_products)
    )
    rows = (await session.execute(variants_stmt)).all()
    products = [
        {
            "sku": v.sku,
            "title": p.title,
            "variant_title": v.title,
            "price": v.price,
            "inventory_quantity": v.inventory_quantity,
            "low_stock": v.inventory_quantity <= low_stock_threshold,
        }
        for v, p in rows
    ]

    since = datetime.now(timezone.utc) - timedelta(days=14)
    sales_stmt = (
        select(
            OrderLineItem.sku,
            func.sum(OrderLineItem.quantity).label("units"),
            func.count(func.distinct(SalesOrder.id)).label("orders"),
        )
        .join(SalesOrder, SalesOrder.id == OrderLineItem.order_id)
        .where(SalesOrder.brand_id == brand_id, SalesOrder.created_at >= since)
        .group_by(OrderLineItem.sku)
        .order_by(func.sum(OrderLineItem.quantity).desc())
        .limit(max_products)
    )
    sales_rows = (await session.execute(sales_stmt)).all()
    sales_summary = [
        {"sku": r.sku, "units_last_14_days": int(r.units), "orders": int(r.orders)}
        for r in sales_rows
    ]

    po_stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.brand_id == brand_id, PurchaseOrder.status.in_(["pending", "shipped"]))
        .order_by(PurchaseOrder.expected_delivery.asc())
    )
    open_pos = [
        {
            "sku": po.sku,
            "supplier_id": str(po.supplier_id) if po.supplier_id else None,
            "ordered_quantity": po.ordered_quantity,
            "expected_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
            "status": po.status,
        }
        for po in (await session.execute(po_stmt)).scalars().all()
    ]

    suppliers = [
        {
            "supplier_id": str(s.id),
            "name": s.name,
            "lead_time_days": s.lead_time_days,
            "minimum_order_qty": s.minimum_order_qty,
            "reliability_score": s.reliability_score,
        }
        for s in (await session.execute(select(Supplier).where(Supplier.brand_id == brand_id))).scalars().all()
    ]

    warehouses = [
        {"name": w.name, "capacity": w.capacity, "current_utilization": w.current_utilization}
        for w in (await session.execute(select(Warehouse).where(Warehouse.brand_id == brand_id))).scalars().all()
    ]

    today = date.today()
    horizon = today + timedelta(days=60)
    seasonal_stmt = select(SeasonalEvent).where(
        SeasonalEvent.end_date >= today,
        SeasonalEvent.start_date <= horizon,
        (SeasonalEvent.brand_id == brand_id) | (SeasonalEvent.brand_id.is_(None)),
    )
    seasonal = [
        {
            "name": e.name,
            "start_date": e.start_date.isoformat(),
            "end_date": e.end_date.isoformat(),
            "expected_demand_multiplier": e.expected_demand_multiplier,
        }
        for e in (await session.execute(seasonal_stmt)).scalars().all()
    ]

    return {
        "products": products,
        "sales_summary": sales_summary,
        "open_purchase_orders": open_pos,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "upcoming_seasonal_events": seasonal,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/inventory/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def get_sku_sales_history(
    session: AsyncSession, brand_id: str, sku: str, days: int = 21
) -> tuple[Optional[int], list[float]]:
    """Returns (current_stock, daily_units_sold[oldest..newest]) for a SKU."""
    variant_stmt = (
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.brand_id == brand_id, ProductVariant.sku == sku)
    )
    variant = (await session.execute(variant_stmt)).scalar_one_or_none()
    if variant is None:
        return None, []

    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            func.date(SalesOrder.created_at).label("day"),
            func.sum(OrderLineItem.quantity).label("units"),
        )
        .join(SalesOrder, SalesOrder.id == OrderLineItem.order_id)
        .where(SalesOrder.brand_id == brand_id, OrderLineItem.sku == sku, SalesOrder.created_at >= since)
        .group_by(func.date(SalesOrder.created_at))
        .order_by(func.date(SalesOrder.created_at).asc())
    )
    rows = (await session.execute(stmt)).all()
    # func.date(...) comes back as a native `date` via asyncpg/Postgres but as
    # a plain string via SQLite — normalize to ISO strings so the lookup
    # below works regardless of driver.
    by_day: dict[str, int] = {}
    for r in rows:
        key = r.day.isoformat() if hasattr(r.day, "isoformat") else str(r.day)
        by_day[key] = int(r.units)

    history: list[float] = []
    for i in range(days):
        d = (since + timedelta(days=i)).date()
        history.append(float(by_day.get(d.isoformat(), 0)))

    return variant.inventory_quantity, history


async def find_supplier(session: AsyncSession, brand_id: str, name_or_id: str) -> Optional[dict]:
    stmt = select(Supplier).where(Supplier.brand_id == brand_id, Supplier.name.ilike(f"%{name_or_id}%"))
    supplier = (await session.execute(stmt)).scalars().first()
    if not supplier:
        return None
    return {
        "supplier_id": str(supplier.id),
        "name": supplier.name,
        "lead_time_days": supplier.lead_time_days,
        "minimum_order_qty": supplier.minimum_order_qty,
        "reliability_score": supplier.reliability_score,
        "contact_email": supplier.contact_email,
        "contact_whatsapp": supplier.contact_whatsapp,
    }


async def get_supplier_by_id(session: AsyncSession, brand_id: str, supplier_id: str) -> Optional[dict]:
    """Exact-id lookup — used by create_purchase_order, which is handed the
    supplier_id find_supplier / get_supplier_details already returned."""
    try:
        sid = uuid.UUID(supplier_id)
    except ValueError:
        return None
    stmt = select(Supplier).where(Supplier.brand_id == brand_id, Supplier.id == sid)
    supplier = (await session.execute(stmt)).scalar_one_or_none()
    if not supplier:
        return None
    return {
        "supplier_id": str(supplier.id),
        "name": supplier.name,
        "lead_time_days": supplier.lead_time_days,
        "minimum_order_qty": supplier.minimum_order_qty,
        "reliability_score": supplier.reliability_score,
        "contact_email": supplier.contact_email,
        "contact_whatsapp": supplier.contact_whatsapp,
    }


async def get_warehouses(session: AsyncSession, brand_id: str, name_filter: Optional[str] = None) -> list[dict]:
    stmt = select(Warehouse).where(Warehouse.brand_id == brand_id)
    if name_filter:
        stmt = stmt.where(Warehouse.name.ilike(f"%{name_filter}%"))
    return [
        {"name": w.name, "capacity": w.capacity, "current_utilization": w.current_utilization}
        for w in (await session.execute(stmt)).scalars().all()
    ]


# ── operational write — a real purchase order, not a recommendation.
# Caller (agents/inventory/tools.py) commits; this only adds+flushes, same
# convention as the rest of this file's Step 7 helpers. ────────────────────

async def create_purchase_order(
    session: AsyncSession, brand_id: str, sku: str, supplier_id: str,
    quantity: int, expected_delivery: date,
) -> dict:
    po = PurchaseOrder(
        brand_id=brand_id, supplier_id=uuid.UUID(supplier_id), sku=sku,
        ordered_quantity=quantity, expected_delivery=expected_delivery, status="pending",
    )
    session.add(po)
    await session.flush()
    return {
        "purchase_order_id": str(po.id), "sku": sku, "supplier_id": supplier_id,
        "quantity": quantity, "expected_delivery": expected_delivery.isoformat(), "status": "pending",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (AI-generated intelligence only)
# ══════════════════════════════════════════════════════════════════════════════

async def save_forecasts(session: AsyncSession, brand_id: str, forecasts: list[dict]) -> None:
    today = date.today()
    for f in forecasts:
        session.add(InventoryForecast(
            brand_id=brand_id,
            sku=f.get("sku", ""),
            forecast_date=today,
            forecast_days=f.get("forecast_days", 30),
            predicted_units_sold=f.get("predicted_units_sold", 0),
            predicted_stock_remaining=f.get("predicted_stock_remaining", 0),
            days_until_stockout=f.get("days_until_stockout"),
            confidence=f.get("confidence", 0.5),
        ))
    await session.flush()


async def save_recommendations(session: AsyncSession, brand_id: str, recommendations: list[dict]) -> None:
    for r in recommendations:
        po_id = r.get("purchase_order_id")
        session.add(ReorderRecommendation(
            brand_id=brand_id,
            sku=r.get("sku", ""),
            supplier_id=r.get("supplier_id") or None,
            quantity=r.get("quantity", 0),
            urgency=r.get("urgency", "normal"),
            reason=r.get("reason", ""),
            supplier_message=r.get("supplier_message", ""),
            status=r.get("status", "ordered"),
            purchase_order_id=uuid.UUID(po_id) if po_id else None,
        ))
    await session.flush()


async def save_alerts(session: AsyncSession, brand_id: str, alerts: list[dict]) -> None:
    for a in alerts:
        session.add(InventoryAlert(
            brand_id=brand_id,
            type=a.get("type", "general"),
            severity=a.get("severity", "low"),
            sku=a.get("sku"),
            message=a.get("message", ""),
            resolved=False,
        ))
    await session.flush()


async def log_execution(
    session: AsyncSession,
    brand_id: str,
    agent: str,
    task_type: str,
    status: str,
    duration_ms: float,
    tools_used: list[str],
    token_usage: dict,
    summary: str,
) -> None:
    from db import crud_common
    await crud_common.log_execution(
        session, brand_id, agent, task_type, status, duration_ms, tools_used, token_usage, summary,
    )


async def save_agent_memory(
    session: AsyncSession, brand_id: str, agent: str, content: str, kind: str = "run_summary"
) -> None:
    """Structured copy in Postgres (audit trail) + semantic copy in Chroma
    (so future runs can retrieve it by meaning, see agents/inventory/memory.py)."""
    from db import crud_common
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.inventory import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_alerts(session: AsyncSession, brand_id: str, resolved: bool = False) -> list[dict]:
    stmt = (
        select(InventoryAlert)
        .where(InventoryAlert.brand_id == brand_id, InventoryAlert.resolved == resolved)
        .order_by(InventoryAlert.created_at.desc())
    )
    return [
        {
            "id": str(a.id), "type": a.type, "severity": a.severity, "sku": a.sku,
            "message": a.message, "resolved": a.resolved, "created_at": a.created_at.isoformat(),
        }
        for a in (await session.execute(stmt)).scalars().all()
    ]


async def list_recommendations(
    session: AsyncSession, brand_id: str, status: str = "pending_approval"
) -> list[dict]:
    stmt = (
        select(ReorderRecommendation)
        .where(ReorderRecommendation.brand_id == brand_id, ReorderRecommendation.status == status)
        .order_by(ReorderRecommendation.created_at.desc())
    )
    return [
        {
            "id": str(r.id), "sku": r.sku,
            "supplier_id": str(r.supplier_id) if r.supplier_id else None,
            "quantity": r.quantity, "urgency": r.urgency, "reason": r.reason,
            "supplier_message": r.supplier_message, "status": r.status,
            "purchase_order_id": str(r.purchase_order_id) if r.purchase_order_id else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in (await session.execute(stmt)).scalars().all()
    ]
