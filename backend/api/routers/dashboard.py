"""
FashionOS — Dashboard Aggregation API
======================================
GET /api/v1/dashboard?days=30

One consolidated payload for the Dashboard page — KPI numbers (with
period-over-period deltas), a revenue series (line) plus orders (bars),
per-agent output counts (bar), alert/ticket/expense/content breakdowns
(pie), the revenue forecast, top products, recent refunds, and the latest
agent runs — so the frontend renders instantly without fanning out dozens
of requests.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_brand
from db.models import (
    AgentExecutionLog,
    Brand,
    ContentPlan,
    Customer,
    CustomerFeedback,
    CustomerSegment,
    Expense,
    FinancialForecast,
    FinancialInsight,
    FinancialReport,
    InventoryAlert,
    InventoryForecast,
    MarketingCampaign,
    MarketingInsight,
    MarketTrend,
    NegotiationRecord,
    OrderLineItem,
    PricingIntelligence,
    Product,
    ProductOpportunity,
    ProductVariant,
    PurchaseOrder,
    ReorderRecommendation,
    ResearchInsight,
    Return,
    RiskAssessment,
    SalesAnomaly,
    SalesForecast,
    SalesInsight,
    SalesOrder,
    SalesReport,
    ScheduledContent,
    SupplierInsight,
    SupplierQuote,
    SupportConversation,
    SupportTicket,
)
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

AGENT_IDS = [
    "inventory",
    "sales",
    "marketing",
    "finance",
    "research",
    "supplier",
    "customer_support",
]


def _delta(cur, prev):
    """Period-over-period % change. None when the previous period is empty."""
    if prev:
        return round((cur - prev) / prev * 100, 1)
    return None


async def _count(
    session: AsyncSession,
    model,
    brand_id: str,
    where=None,
) -> int:
    q = select(func.count()).select_from(model).where(model.brand_id == brand_id)
    if where is not None:
        q = q.where(where)
    return int(await session.scalar(q) or 0)


async def _period_totals(
    session: AsyncSession,
    brand_id: str,
    start: datetime,
    end: datetime,
) -> tuple[int, float]:
    """(order_count, revenue) for a [start, end) window."""
    row = (
        await session.execute(
            select(
                func.count(SalesOrder.id),
                func.coalesce(func.sum(SalesOrder.total_price), 0.0),
            )
            .where(
                SalesOrder.brand_id == brand_id,
                SalesOrder.created_at >= start,
                SalesOrder.created_at < end,
            )
        )
    ).one()
    return int(row[0] or 0), float(row[1] or 0.0)


async def _period_expenses(
    session: AsyncSession,
    brand_id: str,
    start: datetime,
    end: datetime,
) -> float:
    return float(
        await session.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0.0))
            .where(
                Expense.brand_id == brand_id,
                Expense.incurred_at >= start,
                Expense.incurred_at < end,
            )
        ) or 0.0
    )


async def _period_new_customers(
    session: AsyncSession,
    brand_id: str,
    start: datetime,
    end: datetime,
) -> int:
    return int(
        await session.scalar(
            select(func.count(Customer.id))
            .where(
                Customer.brand_id == brand_id,
                Customer.first_order_at >= start,
                Customer.first_order_at < end,
            )
        ) or 0
    )


async def _period_refunds(
    session: AsyncSession,
    brand_id: str,
    start: datetime,
    end: datetime,
) -> tuple[int, float]:
    row = (
        await session.execute(
            select(
                func.count(Return.id),
                func.coalesce(func.sum(Return.refund_amount), 0.0),
            )
            .where(
                Return.brand_id == brand_id,
                Return.refunded_at >= start,
                Return.refunded_at < end,
            )
        )
    ).one()
    return int(row[0] or 0), float(row[1] or 0.0)


async def _agent_output_counts(session: AsyncSession, brand_id: str) -> dict:
    """Total records each agent has produced — the "what agents do" bar."""
    c = {}

    c["inventory"] = sum([
        await _count(session, InventoryAlert, brand_id),
        await _count(session, InventoryForecast, brand_id),
        await _count(session, ReorderRecommendation, brand_id),
    ])

    c["sales"] = sum([
        await _count(session, SalesReport, brand_id),
        await _count(session, SalesInsight, brand_id),
        await _count(session, SalesAnomaly, brand_id),
        await _count(session, CustomerSegment, brand_id),
    ])

    c["marketing"] = sum([
        await _count(session, MarketingCampaign, brand_id),
        await _count(session, ContentPlan, brand_id),
        await _count(session, ScheduledContent, brand_id),
        await _count(session, MarketingInsight, brand_id),
    ])

    c["finance"] = sum([
        await _count(session, FinancialReport, brand_id),
        await _count(session, FinancialInsight, brand_id),
        await _count(session, FinancialForecast, brand_id),
        await _count(session, RiskAssessment, brand_id),
    ])

    c["research"] = sum([
        await _count(session, MarketTrend, brand_id),
        await _count(session, ResearchInsight, brand_id),
        await _count(session, ProductOpportunity, brand_id),
        await _count(session, PricingIntelligence, brand_id),
    ])

    c["supplier"] = sum([
        await _count(session, PurchaseOrder, brand_id),
        await _count(session, SupplierQuote, brand_id),
        await _count(session, NegotiationRecord, brand_id),
        await _count(session, SupplierInsight, brand_id),
    ])

    c["customer_support"] = sum([
        await _count(session, SupportTicket, brand_id),
        await _count(session, SupportConversation, brand_id),
        await _count(session, CustomerFeedback, brand_id),
    ])

    return c


@router.get("")
async def dashboard(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
    days: int = Query(30, ge=7, le=90),
) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days - 1)
    prev_end = cutoff
    prev_start = cutoff - timedelta(days=days)
    today = now.date()

    # ── Revenue series (line) ─────────────────────────────────────────────────
    revenue_rows = (
        await session.execute(
            select(
                func.date(SalesOrder.created_at),
                func.count(SalesOrder.id),
                func.coalesce(func.sum(SalesOrder.total_price), 0.0),
            )
            .where(SalesOrder.brand_id == brand.brand_id, SalesOrder.created_at >= cutoff)
            .group_by(func.date(SalesOrder.created_at))
            .order_by(func.date(SalesOrder.created_at))
        )
    ).all()

    revenue_by_day = {}
    for day, orders, revenue in revenue_rows:
        revenue_by_day[day.isoformat()] = {
            "orders": int(orders),
            "revenue": round(float(revenue), 2),
        }

    revenue_series = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        revenue_series.append(revenue_by_day.get(
            d, {"date": d, "orders": 0, "revenue": 0.0}
        ))

    revenue_30d = round(sum(v["revenue"] for v in revenue_by_day.values()), 2)
    orders_30d = sum(v["orders"] for v in revenue_by_day.values())

    # ── Period-over-period deltas ────────────────────────────────────────────
    prev_orders, prev_revenue = await _period_totals(
        session, brand.brand_id, prev_start, prev_end
    )
    expenses_30d = await _period_expenses(session, brand.brand_id, cutoff, now)
    prev_expenses = await _period_expenses(session, brand.brand_id, prev_start, prev_end)
    new_customers = await _period_new_customers(session, brand.brand_id, cutoff, now)
    prev_new_customers = await _period_new_customers(session, brand.brand_id, prev_start, prev_end)
    refunds_count, refunds_amount = await _period_refunds(session, brand.brand_id, cutoff, now)
    prev_refunds, _ = await _period_refunds(session, brand.brand_id, prev_start, prev_end)

    aov = round(revenue_30d / orders_30d, 2) if orders_30d else 0.0
    prev_aov = round(prev_revenue / prev_orders, 2) if prev_orders else 0.0

    numbers = {
        "revenue_30d": revenue_30d,
        "orders_30d": orders_30d,
        "aov": aov,
        "customers": await _count(session, Customer, brand.brand_id),
        "new_customers": new_customers,
        "products": await _count(session, Product, brand.brand_id),
        "low_stock": await _count(
            session, ProductVariant, brand.brand_id,
            where=ProductVariant.inventory_quantity <= 5,
        ),
        "expenses_30d": round(expenses_30d, 2),
        "refunds_count": refunds_count,
        "refunds_amount": round(refunds_amount, 2),
        "alerts_open": await _count(
            session, InventoryAlert, brand.brand_id,
            where=InventoryAlert.resolved.is_(False),
        ),
        "campaigns": await _count(session, MarketingCampaign, brand.brand_id),
        "content": await _count(session, ScheduledContent, brand.brand_id),
        "tickets_open": await _count(
            session, SupportTicket, brand.brand_id,
            where=SupportTicket.status.in_(["open", "in_progress", "escalated"]),
        ),
        "runs": await _count(
            session, AgentExecutionLog, brand.brand_id,
            where=AgentExecutionLog.status == "completed",
        ),
    }

    deltas = {
        "revenue": _delta(revenue_30d, prev_revenue),
        "orders": _delta(orders_30d, prev_orders),
        "aov": _delta(aov, prev_aov),
        "customers": _delta(new_customers, prev_new_customers),
        "expenses": _delta(expenses_30d, prev_expenses),
        "refunds": _delta(refunds_count, prev_refunds),
    }

    # ── Revenue forecast (line) ───────────────────────────────────────────────
    latest = await session.scalar(
        select(func.max(SalesForecast.created_at))
        .where(SalesForecast.brand_id == brand.brand_id)
    )
    forecast_series = []
    if latest:
        rows = (
            await session.execute(
                select(
                    SalesForecast.forecast_date,
                    func.coalesce(func.sum(SalesForecast.predicted_revenue), 0.0),
                )
                .where(
                    SalesForecast.brand_id == brand.brand_id,
                    SalesForecast.created_at == latest,
                )
                .group_by(SalesForecast.forecast_date)
                .order_by(SalesForecast.forecast_date)
            )
        ).all()
        forecast_series = [
            {"date": d.isoformat(), "revenue": round(float(r), 2)}
            for d, r in rows
        ]

    # ── Bar: agent output counts ──────────────────────────────────────────────
    counts = await _agent_output_counts(session, brand.brand_id)
    agents = [
        {"id": aid, "label": aid.replace("_", " ").title(), "count": counts[aid]}
        for aid in AGENT_IDS
    ]

    # ── Top products (by revenue in window) ───────────────────────────────────
    top_rows = (
        await session.execute(
            select(
                OrderLineItem.sku,
                OrderLineItem.name,
                func.sum(OrderLineItem.quantity),
                func.coalesce(func.sum(OrderLineItem.quantity * OrderLineItem.price), 0.0),
            )
            .join(SalesOrder, SalesOrder.id == OrderLineItem.order_id)
            .where(
                SalesOrder.brand_id == brand.brand_id,
                SalesOrder.created_at >= cutoff,
            )
            .group_by(OrderLineItem.sku, OrderLineItem.name)
            .order_by(func.sum(OrderLineItem.quantity * OrderLineItem.price).desc())
            .limit(5)
        )
    ).all()
    top_products = [
        {
            "sku": sku,
            "name": name,
            "units": int(units or 0),
            "revenue": round(float(rev), 2),
        }
        for sku, name, units, rev in top_rows
    ]

    # ── Recent refunds ────────────────────────────────────────────────────────
    refund_rows = (
        await session.execute(
            select(Return)
            .where(Return.brand_id == brand.brand_id)
            .order_by(Return.refunded_at.desc().nulls_last())
            .limit(6)
        )
    ).scalars().all()
    recent_refunds = [
        {
            "product_name": r.product_name,
            "sku": r.sku,
            "quantity": r.quantity,
            "refund_amount": round(r.refund_amount, 2),
            "return_reason": r.return_reason,
            "refunded_at": r.refunded_at.isoformat() if r.refunded_at else None,
        }
        for r in refund_rows
    ]

    # ── Pie breakdowns ────────────────────────────────────────────────────────
    alert_rows = (
        await session.execute(
            select(InventoryAlert.severity, func.count())
            .where(
                InventoryAlert.brand_id == brand.brand_id,
                InventoryAlert.resolved.is_(False),
            )
            .group_by(InventoryAlert.severity)
        )
    ).all()
    alerts_pie = [
        {"name": sev, "value": int(n)} for sev, n in alert_rows
    ]

    ticket_rows = (
        await session.execute(
            select(SupportTicket.status, func.count())
            .where(SupportTicket.brand_id == brand.brand_id)
            .group_by(SupportTicket.status)
        )
    ).all()
    tickets_pie = [
        {"name": st, "value": int(n)} for st, n in ticket_rows
    ]

    expense_rows = (
        await session.execute(
            select(Expense.category, func.coalesce(func.sum(Expense.amount), 0.0))
            .where(Expense.brand_id == brand.brand_id, Expense.incurred_at >= cutoff)
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
    ).all()
    expenses_pie = [
        {"name": cat, "value": round(float(v), 2)} for cat, v in expense_rows
    ]

    content_rows = (
        await session.execute(
            select(ScheduledContent.platform, func.count())
            .where(
                ScheduledContent.brand_id == brand.brand_id,
                ScheduledContent.status.in_([
                    "scheduled", "published", "awaiting_integration",
                ]),
            )
            .group_by(ScheduledContent.platform)
        )
    ).all()
    content_pie = [
        {"name": plat, "value": int(n)} for plat, n in content_rows
    ]

    # ── Recent runs feed ──────────────────────────────────────────────────────
    run_rows = (
        await session.execute(
            select(AgentExecutionLog)
            .where(AgentExecutionLog.brand_id == brand.brand_id)
            .order_by(AgentExecutionLog.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
    activity = [
        {
            "agent": r.agent,
            "task": r.task,
            "status": r.status,
            "duration_ms": round(r.duration_ms or 0),
            "tools": r.tools_used or [],
            "created_at": r.created_at.isoformat(),
        }
        for r in run_rows
    ]

    return {
        "generated_at": now.isoformat(),
        "days": days,
        "numbers": numbers,
        "deltas": deltas,
        "revenue_series": revenue_series,
        "forecast_series": forecast_series,
        "agents": agents,
        "top_products": top_products,
        "recent_refunds": recent_refunds,
        "pie": {
            "alerts": alerts_pie,
            "tickets": tickets_pie,
            "expenses": expenses_pie,
            "content": content_pie,
        },
        "activity": activity,
    }
