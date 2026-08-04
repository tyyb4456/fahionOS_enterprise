"""
Marketing Agent — read/write layer.

Three kinds of tables live here:
  - tables this agent OWNS and writes to (MarketingCampaign, ContentPlan,
    ScheduledContent, MarketingInsight, AudienceSegment, ContentPerformance,
    + the shared AgentExecutionLog/AgentMemory via db/crud_common.py).
  - tables it reads but doesn't own — Product/ProductVariant (Shopify
    catalog mirror) for content material, and InventoryAlert/
    InventoryForecast (Inventory Agent's own outputs) / SalesInsight/
    SalesReport/CustomerSegment (Sales Agent's own outputs). Reading
    another agent's AI-output tables directly, instead of recomputing the
    same analysis, is the established pattern here — see the note already
    in agents/sales/prompts.py: "Other agents' facts ... live in the
    shared database — read them, don't recompute them."
  - SeasonalEvent, shared with Inventory's context builder, for the
    marketing calendar.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AudienceSegment, ContentPerformance, ContentPlan, CustomerSegment,
    InventoryAlert, InventoryForecast, MarketingCampaign, MarketingInsight,
    Product, ProductVariant, SalesInsight, SalesReport, ScheduledContent,
    SeasonalEvent,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(session: AsyncSession, brand_id: str, max_products: int = 30) -> dict[str, Any]:
    """
    Assemble the snapshot handed to the reasoning loop: candidate products
    (a rough cross-check only — check_product_stock is the authoritative
    per-SKU answer), Sales Agent's latest insights/KPIs, Inventory Agent's
    open alerts, customer segments, this agent's own recent campaigns, and
    the upcoming marketing calendar. Deeper digging happens via tools, same
    as Inventory/Sales.
    """
    logger.info("Building marketing context for brand=%s", brand_id)
    products = await _promotable_products(session, brand_id, limit=max_products)
    sales_insights = await _recent_sales_insights(session, brand_id, limit=8)
    latest_report = await _latest_sales_report(session, brand_id)
    inventory_alerts = await _open_inventory_alerts(session, brand_id, limit=10)
    customer_segments = await _customer_segments(session, brand_id)
    previous_campaigns = await _recent_campaigns(session, brand_id, limit=5)
    calendar = await _upcoming_calendar(session, brand_id)

    return {
        "products": products,
        "sales_insights": sales_insights,
        "latest_sales_report": latest_report,
        "inventory_alerts": inventory_alerts,
        "customer_segments": customer_segments,
        "previous_campaigns": previous_campaigns,
        "marketing_calendar": calendar,
    }


async def _promotable_products(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.brand_id == brand_id, Product.status == "active")
        .order_by(ProductVariant.inventory_quantity.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "sku": v.sku,
            "title": p.title,
            "variant_title": v.title,
            "price": v.price,
            "tags": p.tags,
            "image_url": p.image_url,
            "inventory_quantity": v.inventory_quantity,
            # quick heuristic flag only — check_product_stock (tool) cross-
            # references InventoryAlert for the authoritative answer
            "likely_safe_to_promote": v.inventory_quantity > 25,
        }
        for v, p in rows
    ]


async def _recent_sales_insights(session: AsyncSession, brand_id: str, limit: int = 8) -> list[dict]:
    stmt = (
        select(SalesInsight)
        .where(SalesInsight.brand_id == brand_id)
        .order_by(SalesInsight.created_at.desc())
        .limit(limit)
    )
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


async def _customer_segments(session: AsyncSession, brand_id: str) -> list[dict]:
    stmt = select(CustomerSegment).where(CustomerSegment.brand_id == brand_id)
    return [
        {"segment": s.segment, "customer_count": s.customer_count, "definition": s.definition}
        for s in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_campaigns(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = (
        select(MarketingCampaign)
        .where(MarketingCampaign.brand_id == brand_id)
        .order_by(MarketingCampaign.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "name": c.name, "goal": c.goal, "platform": c.platform, "status": c.status,
            "target_audience": c.target_audience, "created_at": c.created_at.isoformat(),
        }
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def _upcoming_calendar(session: AsyncSession, brand_id: str, horizon_days: int = 60) -> list[dict]:
    today = date.today()
    horizon = today + timedelta(days=horizon_days)
    stmt = select(SeasonalEvent).where(
        SeasonalEvent.end_date >= today,
        SeasonalEvent.start_date <= horizon,
        (SeasonalEvent.brand_id == brand_id) | (SeasonalEvent.brand_id.is_(None)),
    )
    return [
        {
            "name": e.name, "start_date": e.start_date.isoformat(), "end_date": e.end_date.isoformat(),
            "expected_demand_multiplier": e.expected_demand_multiplier,
        }
        for e in (await session.execute(stmt)).scalars().all()
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/marketing/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def check_product_stock(session: AsyncSession, brand_id: str, sku: str) -> Optional[dict]:
    """Authoritative promotability check — inventory_quantity + any open
    Inventory Agent alert for this exact SKU."""
    stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.brand_id == brand_id, ProductVariant.sku == sku)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    variant, product = row

    alert_stmt = select(InventoryAlert).where(
        InventoryAlert.brand_id == brand_id, InventoryAlert.sku == sku, InventoryAlert.resolved == False,  # noqa: E712
    ).order_by(InventoryAlert.created_at.desc()).limit(1)
    alert = (await session.execute(alert_stmt)).scalar_one_or_none()

    return {
        "sku": sku,
        "title": product.title,
        "image_url": product.image_url,
        "inventory_quantity": variant.inventory_quantity,
        "open_alert": {"type": alert.type, "severity": alert.severity, "message": alert.message} if alert else None,
        "safe_to_promote": variant.inventory_quantity > 10 and not (alert and alert.severity in ("high", "critical")),
    }


async def get_recent_sales_insights(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    return await _recent_sales_insights(session, brand_id, limit=limit)


async def get_inventory_alerts(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _open_inventory_alerts(session, brand_id, limit=limit)


async def get_customer_segments(session: AsyncSession, brand_id: str) -> list[dict]:
    return await _customer_segments(session, brand_id)


async def list_recent_campaigns(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    return await _recent_campaigns(session, brand_id, limit=limit)


async def get_content_performance_history(
    session: AsyncSession, brand_id: str, platform: Optional[str] = None, limit: int = 50
) -> list[dict]:
    stmt = select(ContentPerformance).where(ContentPerformance.brand_id == brand_id)
    if platform:
        stmt = stmt.where(ContentPerformance.platform == platform)
    stmt = stmt.order_by(ContentPerformance.recorded_at.desc()).limit(limit)
    return [
        {
            "platform": c.platform, "engagement": c.engagement, "ctr": c.ctr,
            "conversion": c.conversion, "roas": c.roas, "recorded_at": c.recorded_at.isoformat(),
        }
        for c in (await session.execute(stmt)).scalars().all()
    ]


# ── operational writes — real, immediate DB changes made mid-ReAct-loop by
# agents/marketing/tools.py, not deferred to persist_node (same reasoning
# as Shopify's set_inventory_level: the agent needs the row's real id back
# to reference/report on). Callers commit; these functions only add+flush,
# same convention as the rest of this codebase's Step 7 persistence helpers. ──

async def create_scheduled_content(
    session: AsyncSession, brand_id: str, platform: str, content_type: str,
    content: dict, scheduled_for: datetime, campaign_id: Optional[str] = None,
) -> dict:
    logger.info("Creating scheduled content for brand=%s platform=%s", brand_id, platform)
    row = ScheduledContent(
        brand_id=brand_id,
        campaign_id=campaign_id,
        platform=platform,
        content_type=content_type,
        content=content,
        scheduled_for=scheduled_for,
        status="scheduled",
    )
    session.add(row)
    await session.flush()
    return {"scheduled_content_id": str(row.id), "platform": platform, "scheduled_for": scheduled_for.isoformat()}


async def record_content_performance(
    session: AsyncSession, brand_id: str, scheduled_content_id, platform: str,
    engagement: int = 0, ctr: float = 0.0, conversion: float = 0.0, roas: Optional[float] = None,
) -> None:
    session.add(ContentPerformance(
        brand_id=brand_id, scheduled_content_id=scheduled_content_id, platform=platform,
        engagement=engagement, ctr=ctr, conversion=conversion, roas=roas,
    ))
    await session.flush()


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (AI-generated intelligence only)
# ══════════════════════════════════════════════════════════════════════════════

async def save_campaigns(session: AsyncSession, brand_id: str, campaigns: list[dict]) -> list[str]:
    logger.info("Saving %d campaigns for brand=%s", len(campaigns), brand_id)
    ids = []
    for c in campaigns:
        row = MarketingCampaign(
            brand_id=brand_id,
            name=c.get("campaign_name", "Untitled campaign"),
            goal=c.get("goal", ""),
            platform=c.get("platform", "multi-channel"),
            target_audience=c.get("target_audience", ""),
            budget=c.get("budget"),
            duration_days=c.get("duration_days", 7),
            status=c.get("status", "draft"),
        )
        session.add(row)
        await session.flush()
        ids.append(str(row.id))
    return ids


async def save_content_plan(session: AsyncSession, brand_id: str, topics: list[str], platforms: list[str]) -> None:
    if not topics and not platforms:
        return
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    session.add(ContentPlan(brand_id=brand_id, week_start=week_start, topics=topics, platforms=platforms))
    await session.flush()


async def save_marketing_insights(session: AsyncSession, brand_id: str, insights: list[dict]) -> None:
    logger.info("Saving %d marketing insights for brand=%s", len(insights), brand_id)
    for i in insights:
        session.add(MarketingInsight(
            brand_id=brand_id, insight=i.get("insight", ""),
            confidence=i.get("confidence", 0.5), priority=i.get("priority", "low"),
        ))
    await session.flush()


async def save_audience_recommendations(session: AsyncSession, brand_id: str, recommendations: list[dict]) -> None:
    logger.info("Saving %d audience recommendations for brand=%s", len(recommendations), brand_id)
    for r in recommendations:
        segment = r.get("segment", "")
        if not segment:
            continue
        existing = (await session.execute(
            select(AudienceSegment).where(AudienceSegment.brand_id == brand_id, AudienceSegment.segment == segment)
        )).scalar_one_or_none()
        if existing:
            existing.description = r.get("rationale", existing.description)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            session.add(AudienceSegment(
                brand_id=brand_id, segment=segment,
                description=r.get("rationale", ""), campaign_success="",
            ))
    await session.flush()


async def log_execution(session: AsyncSession, brand_id: str, agent: str, task_type: str, status: str,
                         duration_ms: float, tools_used: list[str], token_usage: dict, summary: str) -> None:
    from db import crud_common
    await crud_common.log_execution(session, brand_id, agent, task_type, status, duration_ms, tools_used, token_usage, summary)


async def save_agent_memory(session: AsyncSession, brand_id: str, agent: str, content: str, kind: str = "run_summary") -> None:
    """Structured copy in Postgres (audit trail) + semantic copy in Chroma
    (so future runs can retrieve it by meaning, see agents/marketing/memory.py)."""
    from db import crud_common
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.marketing import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_campaigns(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(MarketingCampaign).where(MarketingCampaign.brand_id == brand_id).order_by(MarketingCampaign.created_at.desc()).limit(limit)
    return [
        {
            "id": str(c.id), "name": c.name, "goal": c.goal, "platform": c.platform,
            "target_audience": c.target_audience, "budget": c.budget, "status": c.status,
            "meta_campaign_id": c.meta_campaign_id, "created_at": c.created_at.isoformat(),
        }
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def list_scheduled_content(session: AsyncSession, brand_id: str, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    stmt = select(ScheduledContent).where(ScheduledContent.brand_id == brand_id)
    if status:
        stmt = stmt.where(ScheduledContent.status == status)
    stmt = stmt.order_by(ScheduledContent.scheduled_for.desc()).limit(limit)
    return [
        {
            "id": str(s.id), "platform": s.platform, "content_type": s.content_type, "content": s.content,
            "scheduled_for": s.scheduled_for.isoformat(), "status": s.status,
            "published_ref_id": s.published_ref_id, "error": s.error,
        }
        for s in (await session.execute(stmt)).scalars().all()
    ]


async def list_marketing_insights(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(MarketingInsight).where(MarketingInsight.brand_id == brand_id).order_by(MarketingInsight.created_at.desc()).limit(limit)
    return [
        {"id": str(i.id), "insight": i.insight, "confidence": i.confidence, "priority": i.priority, "created_at": i.created_at.isoformat()}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def list_audience_segments(session: AsyncSession, brand_id: str) -> list[dict]:
    stmt = select(AudienceSegment).where(AudienceSegment.brand_id == brand_id).order_by(AudienceSegment.updated_at.desc())
    return [
        {"segment": s.segment, "description": s.description, "campaign_success": s.campaign_success, "updated_at": s.updated_at.isoformat()}
        for s in (await session.execute(stmt)).scalars().all()
    ]


async def list_content_plans(session: AsyncSession, brand_id: str, limit: int = 12) -> list[dict]:
    stmt = select(ContentPlan).where(ContentPlan.brand_id == brand_id).order_by(ContentPlan.week_start.desc()).limit(limit)
    return [
        {"id": str(p.id), "week_start": p.week_start.isoformat(), "topics": p.topics, "platforms": p.platforms}
        for p in (await session.execute(stmt)).scalars().all()
    ]


async def list_content_performance(session: AsyncSession, brand_id: str, limit: int = 50) -> list[dict]:
    return await get_content_performance_history(session, brand_id, limit=limit)
