"""
Finance Agent — read/write layer.

Three kinds of tables live here:
  - cross-agent read tables — SalesOrder/OrderLineItem/Return (Shopify
    mirror), ProductVariant/Product (for cost_price / margin),
    PurchaseOrder/Supplier (Inventory's own tables, read for PO cost
    evaluation), SalesInsight/SalesReport (Sales' outputs), InventoryAlert
    (Inventory's outputs), MarketingInsight/MarketingCampaign (Marketing's
    outputs) — read, not owned, same "shared Postgres, read another
    agent's facts instead of recomputing them" pattern already used by
    db/crud_marketing.py.
  - Expense — operational, dashboard/seed-populated overhead ledger (same
    role as Inventory's Supplier/Warehouse), plus record_expense lets the
    agent log a confirmed cost mid-run.
  - AI-output tables this agent owns — FinancialReport, FinancialForecast,
    FinancialInsight, BudgetRecommendation, RiskAssessment, + the shared
    AgentExecutionLog/AgentMemory via db/crud_common.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    BudgetRecommendation, Expense, FinancialForecast, FinancialInsight,
    FinancialReport, InventoryAlert, MarketingCampaign, MarketingInsight,
    Product, ProductVariant, PurchaseOrder, Return, RiskAssessment,
    SalesInsight, SalesOrder, SalesReport, Supplier,
)

logger = logging.getLogger(__name__)

TIME_RANGE_DAYS = {
    "today": 1, "yesterday": 1, "last_7_days": 7, "last_14_days": 14,
    "last_30_days": 30, "last_90_days": 90,
}


def _window_for(time_range: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if time_range == "yesterday":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        return start, end
    days = TIME_RANGE_DAYS.get(time_range, 30)
    return now - timedelta(days=days), now


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(session: AsyncSession, brand_id: str, time_range: str = "last_30_days") -> dict[str, Any]:
    logger.info("Building finance context for brand=%s time_range=%s", brand_id, time_range)
    start, end = _window_for(time_range)

    revenue, expenses_total, refunds_total = await _revenue_expenses_refunds(session, brand_id, start, end)
    profit = revenue - expenses_total - refunds_total
    margin = round((profit / revenue) * 100, 2) if revenue else 0.0

    profit_summary = {
        "period": time_range, "start": start.isoformat(), "end": end.isoformat(),
        "revenue": round(revenue, 2), "expenses": round(expenses_total, 2),
        "refunds": round(refunds_total, 2), "profit": round(profit, 2), "margin_pct": margin,
    }

    return {
        "profit_summary": profit_summary,
        "inventory_valuation": await _inventory_valuation(session, brand_id),
        "recent_expenses": await _recent_expenses(session, brand_id, limit=15),
        "open_purchase_order_costs": await _open_purchase_order_costs(session, brand_id),
        "sales_insights": await _recent_sales_insights(session, brand_id, limit=8),
        "latest_sales_report": await _latest_sales_report(session, brand_id),
        "open_inventory_alerts": await _open_inventory_alerts(session, brand_id, limit=10),
        "marketing_insights": await _recent_marketing_insights(session, brand_id, limit=8),
        "recent_campaigns": await _recent_campaigns_with_status(session, brand_id, limit=5),
        "previous_financial_reports": await _recent_financial_reports(session, brand_id, limit=3),
        "open_risk_assessments": await _open_risk_assessments(session, brand_id, limit=10),
    }


async def _revenue_expenses_refunds(session: AsyncSession, brand_id: str, start: datetime, end: datetime) -> tuple[float, float, float]:
    revenue_stmt = select(func.coalesce(func.sum(SalesOrder.total_price), 0.0)).where(
        SalesOrder.brand_id == brand_id, SalesOrder.created_at >= start, SalesOrder.created_at < end,
        SalesOrder.financial_status == "paid",
    )
    revenue = float((await session.execute(revenue_stmt)).scalar_one())

    expenses_stmt = select(func.coalesce(func.sum(Expense.amount), 0.0)).where(
        Expense.brand_id == brand_id, Expense.incurred_at >= start, Expense.incurred_at < end,
    )
    expenses_total = float((await session.execute(expenses_stmt)).scalar_one())

    refunds_stmt = select(func.coalesce(func.sum(Return.refund_amount), 0.0)).where(
        Return.brand_id == brand_id, Return.refunded_at.is_not(None),
        Return.refunded_at >= start, Return.refunded_at < end,
    )
    refunds_total = float((await session.execute(refunds_stmt)).scalar_one())

    return revenue, expenses_total, refunds_total


async def _inventory_valuation(session: AsyncSession, brand_id: str) -> dict:
    stmt = (
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.brand_id == brand_id, Product.status == "active")
    )
    variants = (await session.execute(stmt)).scalars().all()
    total_value = 0.0
    missing_cost = 0
    for v in variants:
        if v.cost_price is None:
            missing_cost += 1
            continue
        total_value += v.cost_price * v.inventory_quantity
    return {
        "total_inventory_value": round(total_value, 2),
        "variant_count": len(variants),
        "variants_missing_cost_price": missing_cost,
    }


async def _recent_expenses(session: AsyncSession, brand_id: str, limit: int = 15) -> list[dict]:
    stmt = select(Expense).where(Expense.brand_id == brand_id).order_by(Expense.incurred_at.desc()).limit(limit)
    return [
        {"id": str(e.id), "category": e.category, "description": e.description, "amount": e.amount,
         "recurring": e.recurring, "incurred_at": e.incurred_at.isoformat()}
        for e in (await session.execute(stmt)).scalars().all()
    ]


async def _open_purchase_order_costs(session: AsyncSession, brand_id: str) -> list[dict]:
    stmt = select(PurchaseOrder).where(
        PurchaseOrder.brand_id == brand_id, PurchaseOrder.status.in_(["pending", "shipped"]),
    )
    pos = (await session.execute(stmt)).scalars().all()
    results = []
    for po in pos:
        cost_stmt = select(ProductVariant.cost_price).where(
            ProductVariant.brand_id == brand_id, ProductVariant.sku == po.sku,
        )
        cost_price = (await session.execute(cost_stmt)).scalar_one_or_none()
        total_cost = round(cost_price * po.ordered_quantity, 2) if cost_price is not None else None
        results.append({
            "purchase_order_id": str(po.id), "sku": po.sku, "ordered_quantity": po.ordered_quantity,
            "unit_cost": cost_price, "total_cost": total_cost,
            "expected_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
            "status": po.status,
        })
    return results


async def _recent_sales_insights(session: AsyncSession, brand_id: str, limit: int = 8) -> list[dict]:
    stmt = select(SalesInsight).where(SalesInsight.brand_id == brand_id).order_by(SalesInsight.created_at.desc()).limit(limit)
    return [
        {"category": i.category, "severity": i.severity, "message": i.message, "confidence": i.confidence}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def _latest_sales_report(session: AsyncSession, brand_id: str) -> Optional[dict]:
    stmt = select(SalesReport).where(SalesReport.brand_id == brand_id).order_by(SalesReport.created_at.desc()).limit(1)
    report = (await session.execute(stmt)).scalar_one_or_none()
    if not report:
        return None
    return {"period": report.period, "summary": report.summary, "kpis": report.kpis}


async def _open_inventory_alerts(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    stmt = select(InventoryAlert).where(
        InventoryAlert.brand_id == brand_id, InventoryAlert.resolved == False,  # noqa: E712
    ).order_by(InventoryAlert.created_at.desc()).limit(limit)
    return [
        {"type": a.type, "severity": a.severity, "sku": a.sku, "message": a.message}
        for a in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_marketing_insights(session: AsyncSession, brand_id: str, limit: int = 8) -> list[dict]:
    stmt = select(MarketingInsight).where(MarketingInsight.brand_id == brand_id).order_by(MarketingInsight.created_at.desc()).limit(limit)
    return [
        {"insight": i.insight, "confidence": i.confidence, "priority": i.priority}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_campaigns_with_status(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = select(MarketingCampaign).where(MarketingCampaign.brand_id == brand_id).order_by(MarketingCampaign.created_at.desc()).limit(limit)
    return [
        {"name": c.name, "platform": c.platform, "budget": c.budget, "status": c.status}
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_financial_reports(session: AsyncSession, brand_id: str, limit: int = 3) -> list[dict]:
    stmt = select(FinancialReport).where(FinancialReport.brand_id == brand_id).order_by(FinancialReport.created_at.desc()).limit(limit)
    return [
        {"period": r.period, "revenue": r.revenue, "expenses": r.expenses, "profit": r.profit,
         "margin": r.margin, "created_at": r.created_at.isoformat()}
        for r in (await session.execute(stmt)).scalars().all()
    ]


async def _open_risk_assessments(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    stmt = select(RiskAssessment).where(
        RiskAssessment.brand_id == brand_id, RiskAssessment.resolved == False,  # noqa: E712
    ).order_by(RiskAssessment.created_at.desc()).limit(limit)
    return [
        {"risk": r.risk, "severity": r.severity, "related_amount": r.related_amount, "recommendation": r.recommendation}
        for r in (await session.execute(stmt)).scalars().all()
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/finance/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def get_profit_report(session: AsyncSession, brand_id: str, time_range: str = "last_30_days") -> dict:
    start, end = _window_for(time_range)
    revenue, expenses_total, refunds_total = await _revenue_expenses_refunds(session, brand_id, start, end)
    profit = revenue - expenses_total - refunds_total
    margin = round((profit / revenue) * 100, 2) if revenue else 0.0
    return {
        "period": time_range, "revenue": round(revenue, 2), "expenses": round(expenses_total, 2),
        "refunds": round(refunds_total, 2), "profit": round(profit, 2), "margin_pct": margin,
    }


async def get_expense_breakdown(session: AsyncSession, brand_id: str, days: int = 30) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(Expense.category, func.sum(Expense.amount).label("total"), func.count(Expense.id).label("count"))
        .where(Expense.brand_id == brand_id, Expense.incurred_at >= since)
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    )
    rows = (await session.execute(stmt)).all()
    return [{"category": r.category, "total": round(float(r.total or 0), 2), "count": int(r.count)} for r in rows]


async def get_inventory_valuation(session: AsyncSession, brand_id: str) -> dict:
    return await _inventory_valuation(session, brand_id)


async def get_cash_position_and_series(session: AsyncSession, brand_id: str, days: int = 30) -> tuple[float, list[dict]]:
    """Returns (current_cash_proxy, daily_net_cash_flow[oldest..newest]).
    current_cash_proxy is a running net (revenue - expenses - refunds)
    over the window — this codebase has no real bank/Stripe balance
    integration, so this is the best available proxy (see
    agents/finance/analytics.py's docstring)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    revenue_stmt = (
        select(func.date(SalesOrder.created_at).label("day"), func.sum(SalesOrder.total_price).label("revenue"))
        .where(SalesOrder.brand_id == brand_id, SalesOrder.created_at >= since, SalesOrder.financial_status == "paid")
        .group_by(func.date(SalesOrder.created_at))
    )
    revenue_by_day: dict[str, float] = {}
    for r in (await session.execute(revenue_stmt)).all():
        key = r.day.isoformat() if hasattr(r.day, "isoformat") else str(r.day)
        revenue_by_day[key] = float(r.revenue or 0)

    expense_stmt = (
        select(func.date(Expense.incurred_at).label("day"), func.sum(Expense.amount).label("total"))
        .where(Expense.brand_id == brand_id, Expense.incurred_at >= since)
        .group_by(func.date(Expense.incurred_at))
    )
    expense_by_day: dict[str, float] = {}
    for r in (await session.execute(expense_stmt)).all():
        key = r.day.isoformat() if hasattr(r.day, "isoformat") else str(r.day)
        expense_by_day[key] = float(r.total or 0)

    refund_stmt = (
        select(func.date(Return.refunded_at).label("day"), func.sum(Return.refund_amount).label("total"))
        .where(Return.brand_id == brand_id, Return.refunded_at.is_not(None), Return.refunded_at >= since)
        .group_by(func.date(Return.refunded_at))
    )
    refund_by_day: dict[str, float] = {}
    for r in (await session.execute(refund_stmt)).all():
        key = r.day.isoformat() if hasattr(r.day, "isoformat") else str(r.day)
        refund_by_day[key] = float(r.total or 0)

    series = []
    running_cash = 0.0
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        net = revenue_by_day.get(d, 0.0) - expense_by_day.get(d, 0.0) - refund_by_day.get(d, 0.0)
        running_cash += net
        series.append({"date": d, "net_cash_flow": round(net, 2)})

    return round(running_cash, 2), series


async def get_variant_costs_and_prices(session: AsyncSession, brand_id: str) -> list[dict]:
    stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.brand_id == brand_id, Product.status == "active")
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"sku": v.sku, "title": p.title, "price": v.price, "cost_price": v.cost_price,
         "inventory_quantity": v.inventory_quantity}
        for v, p in rows
    ]


async def get_purchase_order_cost(session: AsyncSession, brand_id: str, purchase_order_id: str) -> Optional[dict]:
    try:
        po_uuid = uuid.UUID(purchase_order_id)
    except ValueError:
        return None
    stmt = select(PurchaseOrder).where(PurchaseOrder.brand_id == brand_id, PurchaseOrder.id == po_uuid)
    po = (await session.execute(stmt)).scalar_one_or_none()
    if not po:
        return None

    cost_stmt = select(ProductVariant.cost_price).where(ProductVariant.brand_id == brand_id, ProductVariant.sku == po.sku)
    cost_price = (await session.execute(cost_stmt)).scalar_one_or_none()

    supplier_name = None
    if po.supplier_id:
        supplier = (await session.execute(select(Supplier).where(Supplier.id == po.supplier_id))).scalar_one_or_none()
        supplier_name = supplier.name if supplier else None

    total_cost = round(cost_price * po.ordered_quantity, 2) if cost_price is not None else None
    return {
        "purchase_order_id": str(po.id), "sku": po.sku, "ordered_quantity": po.ordered_quantity,
        "unit_cost": cost_price, "total_cost": total_cost, "supplier_name": supplier_name,
        "status": po.status, "expected_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
    }


async def get_sales_insights(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _recent_sales_insights(session, brand_id, limit=limit)


async def get_inventory_alerts(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _open_inventory_alerts(session, brand_id, limit=limit)


async def get_marketing_insights(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _recent_marketing_insights(session, brand_id, limit=limit)


# ── operational writes — real, immediate DB changes made mid-ReAct-loop by
# agents/finance/tools.py. Callers commit; these functions only add+flush,
# same convention as the rest of this codebase's Step 7 persistence helpers. ──

async def record_expense(
    session: AsyncSession, brand_id: str, category: str, description: str,
    amount: float, incurred_at: datetime, recurring: bool = False,
) -> dict:
    logger.info("Recording expense for brand=%s category=%s amount=%.2f", brand_id, category, amount)
    row = Expense(brand_id=brand_id, category=category, description=description,
                  amount=amount, incurred_at=incurred_at, recurring=recurring)
    session.add(row)
    await session.flush()
    return {"expense_id": str(row.id), "category": category, "amount": amount, "incurred_at": incurred_at.isoformat()}


async def create_budget_recommendation(
    session: AsyncSession, brand_id: str, department: str,
    current_budget: Optional[float], recommended_budget: float, reason: str,
) -> dict:
    logger.info("Creating budget recommendation for brand=%s department=%s", brand_id, department)
    row = BudgetRecommendation(brand_id=brand_id, department=department, current_budget=current_budget,
                                recommended_budget=recommended_budget, reason=reason)
    session.add(row)
    await session.flush()
    return {"budget_recommendation_id": str(row.id), "department": department, "recommended_budget": recommended_budget}


async def create_risk_assessment(
    session: AsyncSession, brand_id: str, risk: str, severity: str,
    recommendation: str, related_amount: Optional[float] = None,
) -> dict:
    logger.info("Creating risk assessment for brand=%s severity=%s", brand_id, severity)
    row = RiskAssessment(brand_id=brand_id, risk=risk, severity=severity, recommendation=recommendation,
                          related_amount=related_amount, resolved=False)
    session.add(row)
    await session.flush()
    return {"risk_assessment_id": str(row.id), "severity": severity}


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (AI-generated intelligence only)
# ══════════════════════════════════════════════════════════════════════════════

async def save_financial_report(
    session: AsyncSession, brand_id: str, period: str, summary: str,
    revenue: float, expenses: float, profit: float, margin: float, kpis: dict,
) -> None:
    logger.info("Saving financial report for brand=%s period=%s", brand_id, period)
    session.add(FinancialReport(brand_id=brand_id, period=period, summary=summary, revenue=revenue,
                                 expenses=expenses, profit=profit, margin=margin, kpis=kpis or {}))
    await session.flush()


async def save_cashflow_forecast(session: AsyncSession, brand_id: str, forecast: dict, forecast_days: int) -> None:
    if not forecast:
        return
    logger.info("Saving cashflow forecast for brand=%s", brand_id)
    session.add(FinancialForecast(
        brand_id=brand_id, forecast_date=date.today(), forecast_days=forecast_days,
        cash_today=forecast.get("cash_today", 0.0), predicted_cash=forecast.get("predicted_cash", 0.0),
        predicted_revenue=forecast.get("predicted_revenue", 0.0), predicted_expenses=forecast.get("predicted_expenses", 0.0),
        risk=forecast.get("risk", "low"), confidence=forecast.get("confidence", 0.5),
    ))
    await session.flush()


async def save_financial_insights(session: AsyncSession, brand_id: str, insights: list[dict]) -> None:
    logger.info("Saving %d financial insights for brand=%s", len(insights), brand_id)
    for i in insights:
        session.add(FinancialInsight(
            brand_id=brand_id, category=i.get("category", "profitability"),
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
    (so future runs can retrieve it by meaning, see agents/finance/memory.py)."""
    from db import crud_common
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.finance import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_financial_reports(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    stmt = select(FinancialReport).where(FinancialReport.brand_id == brand_id).order_by(FinancialReport.created_at.desc()).limit(limit)
    return [
        {"id": str(r.id), "period": r.period, "summary": r.summary, "revenue": r.revenue, "expenses": r.expenses,
         "profit": r.profit, "margin": r.margin, "kpis": r.kpis, "created_at": r.created_at.isoformat()}
        for r in (await session.execute(stmt)).scalars().all()
    ]


async def list_financial_forecasts(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    stmt = select(FinancialForecast).where(FinancialForecast.brand_id == brand_id).order_by(FinancialForecast.created_at.desc()).limit(limit)
    return [
        {"id": str(f.id), "forecast_date": f.forecast_date.isoformat(), "forecast_days": f.forecast_days,
         "cash_today": f.cash_today, "predicted_cash": f.predicted_cash, "predicted_revenue": f.predicted_revenue,
         "predicted_expenses": f.predicted_expenses, "risk": f.risk, "confidence": f.confidence}
        for f in (await session.execute(stmt)).scalars().all()
    ]


async def list_financial_insights(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(FinancialInsight).where(FinancialInsight.brand_id == brand_id).order_by(FinancialInsight.created_at.desc()).limit(limit)
    return [
        {"id": str(i.id), "category": i.category, "severity": i.severity, "message": i.message,
         "confidence": i.confidence, "created_at": i.created_at.isoformat()}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def list_budget_recommendations(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(BudgetRecommendation).where(BudgetRecommendation.brand_id == brand_id).order_by(BudgetRecommendation.created_at.desc()).limit(limit)
    return [
        {"id": str(b.id), "department": b.department, "current_budget": b.current_budget,
         "recommended_budget": b.recommended_budget, "reason": b.reason, "created_at": b.created_at.isoformat()}
        for b in (await session.execute(stmt)).scalars().all()
    ]


async def list_risk_assessments(session: AsyncSession, brand_id: str, resolved: bool = False, limit: int = 30) -> list[dict]:
    stmt = (
        select(RiskAssessment)
        .where(RiskAssessment.brand_id == brand_id, RiskAssessment.resolved == resolved)
        .order_by(RiskAssessment.created_at.desc())
        .limit(limit)
    )
    return [
        {"id": str(r.id), "risk": r.risk, "severity": r.severity, "related_amount": r.related_amount,
         "recommendation": r.recommendation, "resolved": r.resolved, "created_at": r.created_at.isoformat()}
        for r in (await session.execute(stmt)).scalars().all()
    ]


async def list_expenses(session: AsyncSession, brand_id: str, limit: int = 50) -> list[dict]:
    stmt = select(Expense).where(Expense.brand_id == brand_id).order_by(Expense.incurred_at.desc()).limit(limit)
    return [
        {"id": str(e.id), "category": e.category, "description": e.description, "amount": e.amount,
         "recurring": e.recurring, "incurred_at": e.incurred_at.isoformat()}
        for e in (await session.execute(stmt)).scalars().all()
    ]