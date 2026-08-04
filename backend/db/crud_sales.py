"""
Sales Agent — read/write layer.

Two kinds of tables, same split as db/crud_inventory.py:
  - synced tables (SalesOrder, OrderLineItem, Return, Customer) —
    populated by api/routers/shopify_webhook.py. Read-only from the
    agent's perspective.
  - AI-output tables (SalesReport, SalesInsight, SalesForecast,
    SalesAnomaly, CustomerSegment, + the shared AgentExecutionLog/
    AgentMemory via db/crud_common.py) — written only by this agent.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud_common
from db.models import (
    Customer, CustomerSegment, OrderLineItem, Return,
    SalesAnomaly, SalesForecast, SalesInsight, SalesOrder, SalesReport,
)

logger = logging.getLogger(__name__)

TIME_RANGE_DAYS = {
    "today": 1,
    "yesterday": 1,
    "last_7_days": 7,
    "last_14_days": 14,
    "last_30_days": 30,
    "last_90_days": 90,
}


def _window_for(time_range: str) -> tuple[datetime, datetime]:
    """Returns (start, end) in UTC for the requested period, exclusive of
    `end`. 'yesterday' is the one special case — everyone else is a
    trailing N-day window ending now."""
    now = datetime.now(timezone.utc)
    if time_range == "yesterday":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        return start, end
    days = TIME_RANGE_DAYS.get(time_range, 7)
    return now - timedelta(days=days), now


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(session: AsyncSession, brand_id: str, time_range: str = "last_7_days") -> dict[str, Any]:
    """
    Assemble the snapshot handed to the reasoning loop: revenue vs the prior
    equal-length period, top/worst products, returns, customer summary,
    discount usage, and a daily revenue series for trend/anomaly context.
    Bounded in size on purpose — deeper digging happens via tools.
    """
    logger.info("Building sales context for brand=%s time_range=%s", brand_id, time_range)
    start, end = _window_for(time_range)
    period_length = end - start
    prev_start, prev_end = start - period_length, start

    current_orders = await _orders_in_window(session, brand_id, start, end)
    previous_orders = await _orders_in_window(session, brand_id, prev_start, prev_end)
    current_returns = await _returns_in_window(session, brand_id, start, end)

    current_revenue = float(sum(o["total_price"] for o in current_orders))
    previous_revenue = float(sum(o["total_price"] for o in previous_orders))
    change_pct = (
        round(((current_revenue - previous_revenue) / previous_revenue) * 100, 2)
        if previous_revenue else None
    )

    line_items = await _line_items_in_window(session, brand_id, start, end)

    revenue_summary = {
        "period": time_range,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "revenue": round(current_revenue, 2),
        "orders": len(current_orders),
        "average_order_value": round(current_revenue / len(current_orders), 2) if current_orders else 0.0,
        "previous_period_revenue": round(previous_revenue, 2),
        "change_pct": change_pct,
    }

    top_products, worst_products = _rank_line_items(line_items, top_n=10)

    returns_summary = {
        "count": len(current_returns),
        "refund_amount": round(sum(r["refund_amount"] for r in current_returns), 2),
        "top_reasons": _top_return_reasons(current_returns, limit=5),
    }

    customer_summary = await _customer_summary(session, brand_id, start, end)
    discount_summary = _discount_summary(current_orders)

    daily_revenue = await _daily_revenue_series(session, brand_id, days=max(14, TIME_RANGE_DAYS.get(time_range, 7)))

    return {
        "revenue_summary": revenue_summary,
        "top_products": top_products,
        "worst_products": worst_products,
        "returns_summary": returns_summary,
        "customer_summary": customer_summary,
        "discount_summary": discount_summary,
        "daily_revenue_series": daily_revenue,
    }


async def _orders_in_window(session: AsyncSession, brand_id: str, start: datetime, end: datetime) -> list[dict]:
    stmt = select(SalesOrder).where(
        SalesOrder.brand_id == brand_id,
        SalesOrder.created_at >= start,
        SalesOrder.created_at < end,
        SalesOrder.financial_status == "paid",
    )
    orders = (await session.execute(stmt)).scalars().all()
    return [
        {
            "order_id": o.shopify_order_id,
            "customer_id": o.shopify_customer_id,
            "created_at": o.created_at,
            "total_price": o.total_price,
            "total_discounts": o.total_discounts,
            "discount_codes": o.discount_codes,
        }
        for o in orders
    ]


async def _returns_in_window(session: AsyncSession, brand_id: str, start: datetime, end: datetime) -> list[dict]:
    stmt = select(Return).where(
        Return.brand_id == brand_id,
        Return.refunded_at.is_not(None),
        Return.refunded_at >= start,
        Return.refunded_at < end,
    )
    returns = (await session.execute(stmt)).scalars().all()
    return [
        {
            "sku": r.sku, "product_name": r.product_name, "quantity": r.quantity,
            "refund_amount": r.refund_amount, "return_reason": r.return_reason or "",
        }
        for r in returns
    ]


async def _line_items_in_window(session: AsyncSession, brand_id: str, start: datetime, end: datetime) -> list[dict]:
    stmt = (
        select(OrderLineItem.sku, OrderLineItem.name, OrderLineItem.quantity, OrderLineItem.price)
        .join(SalesOrder, SalesOrder.id == OrderLineItem.order_id)
        .where(
            SalesOrder.brand_id == brand_id,
            SalesOrder.created_at >= start,
            SalesOrder.created_at < end,
            SalesOrder.financial_status == "paid",
        )
    )
    rows = (await session.execute(stmt)).all()
    return [{"sku": r.sku, "name": r.name, "quantity": r.quantity, "price": r.price} for r in rows]


def _rank_line_items(line_items: list[dict], top_n: int = 10) -> tuple[list[dict], list[dict]]:
    from agents.sales.analytics import rank_products_by_revenue
    return rank_products_by_revenue(line_items, top_n=top_n)


def _top_return_reasons(returns: list[dict], limit: int = 5) -> list[dict]:
    counts: dict[str, int] = {}
    for r in returns:
        reason = (r.get("return_reason") or "unspecified").strip() or "unspecified"
        counts[reason] = counts.get(reason, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [{"reason": reason, "count": count} for reason, count in ranked]


def _discount_summary(orders: list[dict]) -> list[dict]:
    # Shopify's order payload gives us a combined total_discounts, not a
    # per-code breakdown — split evenly across codes on the order as an
    # approximation when more than one code was stacked.
    by_code: dict[str, dict] = {}
    for o in orders:
        codes = [c.strip() for c in (o.get("discount_codes") or "").split(",") if c.strip()]
        for code in codes:
            row = by_code.setdefault(code, {"code": code, "orders": 0, "total_discount": 0.0})
            row["orders"] += 1
            row["total_discount"] += o.get("total_discounts", 0.0) / max(1, len(codes))
    for row in by_code.values():
        row["total_discount"] = round(row["total_discount"], 2)
    return sorted(by_code.values(), key=lambda r: -r["orders"])


async def _customer_summary(session: AsyncSession, brand_id: str, start: datetime, end: datetime) -> dict:
    total_stmt = select(func.count(Customer.id)).where(Customer.brand_id == brand_id)
    total_customers = (await session.execute(total_stmt)).scalar_one() or 0

    new_stmt = select(func.count(Customer.id)).where(
        Customer.brand_id == brand_id, Customer.first_order_at >= start, Customer.first_order_at < end,
    )
    new_customers = (await session.execute(new_stmt)).scalar_one() or 0

    repeat_stmt = select(func.count(Customer.id)).where(
        Customer.brand_id == brand_id, Customer.orders_count >= 2,
    )
    repeat_customers = (await session.execute(repeat_stmt)).scalar_one() or 0

    top_stmt = (
        select(Customer)
        .where(Customer.brand_id == brand_id)
        .order_by(Customer.total_spent.desc())
        .limit(5)
    )
    top_customers = [
        {"customer_id": str(c.shopify_customer_id), "email": c.email, "total_spent": c.total_spent, "orders_count": c.orders_count}
        for c in (await session.execute(top_stmt)).scalars().all()
    ]

    return {
        "total_customers": total_customers,
        "new_customers_in_period": new_customers,
        "repeat_customers": repeat_customers,
        "top_customers_by_ltv": top_customers,
    }


async def _daily_revenue_series(session: AsyncSession, brand_id: str, days: int = 14) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            func.date(SalesOrder.created_at).label("day"),
            func.sum(SalesOrder.total_price).label("revenue"),
            func.count(SalesOrder.id).label("orders"),
        )
        .where(SalesOrder.brand_id == brand_id, SalesOrder.created_at >= since, SalesOrder.financial_status == "paid")
        .group_by(func.date(SalesOrder.created_at))
        .order_by(func.date(SalesOrder.created_at).asc())
    )
    rows = (await session.execute(stmt)).all()
    by_day: dict[str, dict] = {}
    for r in rows:
        key = r.day.isoformat() if hasattr(r.day, "isoformat") else str(r.day)
        by_day[key] = {"revenue": float(r.revenue or 0), "orders": int(r.orders or 0)}

    series = []
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        entry = by_day.get(d, {"revenue": 0.0, "orders": 0})
        series.append({"date": d, **entry})
    return series


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/sales/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def get_daily_revenue_series(session: AsyncSession, brand_id: str, days: int = 30) -> list[dict]:
    return await _daily_revenue_series(session, brand_id, days=days)


async def get_product_performance(session: AsyncSession, brand_id: str, days: int = 14, top_n: int = 10) -> dict:
    start = datetime.now(timezone.utc) - timedelta(days=days)
    end = datetime.now(timezone.utc)
    line_items = await _line_items_in_window(session, brand_id, start, end)
    top, worst = _rank_line_items(line_items, top_n=top_n)
    return {"top_products": top, "worst_products": worst, "period_days": days}


async def get_customer_segments_data(session: AsyncSession, brand_id: str) -> list[dict]:
    stmt = select(Customer).where(Customer.brand_id == brand_id)
    customers = (await session.execute(stmt)).scalars().all()
    return [
        {
            "customer_id": str(c.shopify_customer_id),
            "email": c.email,
            "orders_count": c.orders_count,
            "total_spent": c.total_spent,
            "first_order_at": c.first_order_at,
            "last_order_at": c.last_order_at,
        }
        for c in customers
    ]


async def get_customer_by_identifier(session: AsyncSession, brand_id: str, identifier: str) -> Optional[dict]:
    stmt = select(Customer).where(
        Customer.brand_id == brand_id,
        (Customer.email.ilike(f"%{identifier}%")) | (Customer.shopify_customer_id == _safe_int(identifier)),
    )
    c = (await session.execute(stmt)).scalars().first()
    if not c:
        return None
    return {
        "customer_id": str(c.shopify_customer_id), "email": c.email,
        "name": f"{c.first_name or ''} {c.last_name or ''}".strip(),
        "country": c.country, "city": c.city,
        "orders_count": c.orders_count, "total_spent": c.total_spent,
        "first_order_at": c.first_order_at.isoformat() if c.first_order_at else None,
        "last_order_at": c.last_order_at.isoformat() if c.last_order_at else None,
    }


def _safe_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def get_cohort_orders(session: AsyncSession, brand_id: str, months_back: int = 6) -> dict[str, list[datetime]]:
    """Returns {customer_id: [order_created_at, ...]} over the requested
    window, for cohort_retention() in agents/sales/analytics.py."""
    since = datetime.now(timezone.utc) - timedelta(days=months_back * 31)
    stmt = select(SalesOrder.shopify_customer_id, SalesOrder.created_at).where(
        SalesOrder.brand_id == brand_id,
        SalesOrder.created_at >= since,
        SalesOrder.financial_status == "paid",
        SalesOrder.shopify_customer_id.is_not(None),
    )
    rows = (await session.execute(stmt)).all()
    by_customer: dict[str, list[datetime]] = {}
    for r in rows:
        by_customer.setdefault(str(r.shopify_customer_id), []).append(r.created_at)
    return by_customer


async def get_revenue_kpis(session: AsyncSession, brand_id: str, time_range: str = "last_7_days") -> dict:
    from agents.sales.analytics import calculate_revenue_kpis

    start, end = _window_for(time_range)
    orders = await _orders_in_window(session, brand_id, start, end)
    returns = await _returns_in_window(session, brand_id, start, end)

    customers_stmt = select(func.count(Customer.id)).where(Customer.brand_id == brand_id, Customer.orders_count >= 1)
    total_customers = (await session.execute(customers_stmt)).scalar_one() or 0
    repeat_stmt = select(func.count(Customer.id)).where(Customer.brand_id == brand_id, Customer.orders_count >= 2)
    repeat_customers = (await session.execute(repeat_stmt)).scalar_one() or 0

    kpis = calculate_revenue_kpis(orders, returns, repeat_customers, total_customers)
    kpis["period"] = time_range
    return kpis


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (AI-generated intelligence only)
# ══════════════════════════════════════════════════════════════════════════════

async def save_sales_report(session: AsyncSession, brand_id: str, period: str, summary: str, kpis: dict) -> None:
    logger.info("Saving sales report for brand=%s period=%s", brand_id, period)
    session.add(SalesReport(brand_id=brand_id, period=period, summary=summary, kpis=kpis))
    await session.flush()


async def save_sales_insights(session: AsyncSession, brand_id: str, insights: list[dict]) -> None:
    logger.info("Saving %d sales insights for brand=%s", len(insights), brand_id)
    for i in insights:
        session.add(SalesInsight(
            brand_id=brand_id,
            category=i.get("category", "revenue"),
            severity=i.get("severity", "low"),
            message=i.get("message", ""),
            confidence=i.get("confidence", 0.5),
        ))
    await session.flush()


async def save_sales_forecasts(session: AsyncSession, brand_id: str, forecasts: list[dict]) -> None:
    logger.info("Saving %d sales forecasts for brand=%s", len(forecasts), brand_id)
    for f in forecasts:
        forecast_date = f.get("forecast_date")
        if isinstance(forecast_date, str):
            try:
                forecast_date = date.fromisoformat(forecast_date)
            except ValueError:
                forecast_date = date.today()
        elif not isinstance(forecast_date, date):
            forecast_date = date.today()

        session.add(SalesForecast(
            brand_id=brand_id, forecast_date=forecast_date,
            predicted_revenue=f.get("predicted_revenue", 0.0),
            predicted_orders=f.get("predicted_orders", 0),
            confidence=f.get("confidence", 0.5),
        ))
    await session.flush()


async def save_sales_anomalies(session: AsyncSession, brand_id: str, anomalies: list[dict]) -> None:
    logger.info("Saving %d sales anomalies for brand=%s", len(anomalies), brand_id)
    for a in anomalies:
        session.add(SalesAnomaly(
            brand_id=brand_id, metric=a.get("metric", ""),
            expected=a.get("expected", 0.0), actual=a.get("actual", 0.0),
            severity=a.get("severity", "low"), message=a.get("message", ""),
        ))
    await session.flush()


async def save_customer_segments(session: AsyncSession, brand_id: str, segments: list[dict]) -> None:
    logger.info("Saving %d customer segments for brand=%s", len(segments), brand_id)
    for s in segments:
        existing = (await session.execute(
            select(CustomerSegment).where(
                CustomerSegment.brand_id == brand_id, CustomerSegment.segment == s.get("segment", "")
            )
        )).scalar_one_or_none()

        if existing:
            existing.customer_count = s.get("customer_count", 0)
            existing.definition = s.get("definition", "")
            existing.customer_ids = s.get("customer_ids", [])
            existing.updated_at = datetime.now(timezone.utc)
        else:
            session.add(CustomerSegment(
                brand_id=brand_id, segment=s.get("segment", ""),
                customer_count=s.get("customer_count", 0),
                definition=s.get("definition", ""),
                customer_ids=s.get("customer_ids", []),
            ))
    await session.flush()


async def log_execution(session: AsyncSession, brand_id: str, agent: str, task_type: str, status: str,
                         duration_ms: float, tools_used: list[str], token_usage: dict, summary: str) -> None:
    await crud_common.log_execution(session, brand_id, agent, task_type, status, duration_ms, tools_used, token_usage, summary)


async def save_agent_memory(session: AsyncSession, brand_id: str, agent: str, content: str, kind: str = "run_summary") -> None:
    """Structured copy in Postgres (audit trail) + semantic copy in Chroma."""
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.sales import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_insights(session: AsyncSession, brand_id: str, limit: int = 50) -> list[dict]:
    stmt = select(SalesInsight).where(SalesInsight.brand_id == brand_id).order_by(SalesInsight.created_at.desc()).limit(limit)
    return [
        {"id": str(i.id), "category": i.category, "severity": i.severity, "message": i.message,
         "confidence": i.confidence, "created_at": i.created_at.isoformat()}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def list_reports(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    stmt = select(SalesReport).where(SalesReport.brand_id == brand_id).order_by(SalesReport.created_at.desc()).limit(limit)
    return [
        {"id": str(r.id), "period": r.period, "summary": r.summary, "kpis": r.kpis, "created_at": r.created_at.isoformat()}
        for r in (await session.execute(stmt)).scalars().all()
    ]


async def list_forecasts(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(SalesForecast).where(SalesForecast.brand_id == brand_id).order_by(SalesForecast.forecast_date.desc()).limit(limit)
    return [
        {"id": str(f.id), "forecast_date": f.forecast_date.isoformat(), "predicted_revenue": f.predicted_revenue,
         "predicted_orders": f.predicted_orders, "confidence": f.confidence}
        for f in (await session.execute(stmt)).scalars().all()
    ]


async def list_anomalies(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(SalesAnomaly).where(SalesAnomaly.brand_id == brand_id).order_by(SalesAnomaly.created_at.desc()).limit(limit)
    return [
        {"id": str(a.id), "metric": a.metric, "expected": a.expected, "actual": a.actual,
         "severity": a.severity, "message": a.message, "created_at": a.created_at.isoformat()}
        for a in (await session.execute(stmt)).scalars().all()
    ]


async def list_customer_segments(session: AsyncSession, brand_id: str) -> list[dict]:
    stmt = select(CustomerSegment).where(CustomerSegment.brand_id == brand_id).order_by(CustomerSegment.customer_count.desc())
    return [
        {"segment": s.segment, "customer_count": s.customer_count, "definition": s.definition,
         "updated_at": s.updated_at.isoformat()}
        for s in (await session.execute(stmt)).scalars().all()
    ]