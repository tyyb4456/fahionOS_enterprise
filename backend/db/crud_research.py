"""
Research Agent — read/write layer.

Three kinds of tables, following the same split as the other agents'
crud_*.py modules:
  - tables it reads but doesn't own — Product/ProductVariant (catalog),
    SalesInsight (Sales Agent's own output), InventoryAlert (Inventory
    Agent's own output), MarketingCampaign (Marketing Agent's own output).
    Reading another agent's AI-output tables directly instead of
    recomputing the same analysis is the established pattern here — see
    the note already in agents/marketing/tools.py / db/crud_marketing.py.
  - AI-output tables it owns and writes every run via persist_node
    (MarketTrend, ResearchInsight) — the "routine analytical output" this
    agent always tries to produce, same role as Inventory's forecasts/
    alerts or Sales's insights/anomalies.
  - AI-output tables it writes conditionally, mid-ReAct-loop, via its own
    dedicated tools (ProductOpportunity, CompetitorAnalysis,
    PricingIntelligence) — same role as Finance's record_expense/
    create_budget_recommendation/assess_financial_risk: a deliberate
    "I'm formally recording this finding" action taken during reasoning,
    not something every run necessarily produces.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CompetitorAnalysis, InventoryAlert, MarketingCampaign, MarketTrend,
    PricingIntelligence, Product, ProductOpportunity, ResearchInsight,
    SalesInsight,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(session: AsyncSession, brand_id: str, category: Optional[str] = None) -> dict[str, Any]:
    logger.info("Building research context for brand=%s category=%s", brand_id, category)
    catalog = await _catalog_summary(session, brand_id, category=category)
    sales_insights = await _recent_sales_insights(session, brand_id, limit=8)
    inventory_signals = await _open_inventory_signals(session, brand_id, limit=10)
    active_campaigns = await _active_campaigns(session, brand_id, limit=5)
    previous_trends = await _recent_trends(session, brand_id, limit=5)
    previous_opportunities = await _recent_opportunities(session, brand_id, limit=5)

    return {
        "catalog": catalog,
        "sales_insights": sales_insights,
        "inventory_signals": inventory_signals,
        "active_campaigns": active_campaigns,
        "previous_trends": previous_trends,
        "previous_opportunities": previous_opportunities,
    }


async def _catalog_summary(session: AsyncSession, brand_id: str, category: Optional[str] = None, limit: int = 20) -> dict:
    stmt = select(Product).where(Product.brand_id == brand_id, Product.status == "active")
    if category:
        stmt = stmt.where((Product.category.ilike(f"%{category}%")) | (Product.tags.ilike(f"%{category}%")))
    rows = (await session.execute(stmt.limit(limit))).scalars().all()

    sample_products = [{"title": p.title, "category": p.category, "tags": p.tags} for p in rows]

    tag_counts: dict[str, int] = {}
    for p in rows:
        for t in (p.tags or "").split(","):
            t = t.strip()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda kv: -kv[1])[:20]

    return {
        "sample_products": sample_products,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
    }


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


async def _open_inventory_signals(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    stmt = (
        select(InventoryAlert)
        .where(
            InventoryAlert.brand_id == brand_id,
            InventoryAlert.resolved == False,  # noqa: E712
            InventoryAlert.type.in_(["overstock", "stockout_risk", "velocity_spike", "sales_agent_flag"]),
        )
        .order_by(InventoryAlert.created_at.desc())
        .limit(limit)
    )
    return [
        {"type": a.type, "severity": a.severity, "sku": a.sku, "message": a.message}
        for a in (await session.execute(stmt)).scalars().all()
    ]


async def _active_campaigns(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = (
        select(MarketingCampaign)
        .where(MarketingCampaign.brand_id == brand_id, MarketingCampaign.status.in_(["launched", "scheduled"]))
        .order_by(MarketingCampaign.created_at.desc())
        .limit(limit)
    )
    return [
        {"name": c.name, "goal": c.goal, "platform": c.platform, "target_audience": c.target_audience, "status": c.status}
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_trends(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = select(MarketTrend).where(MarketTrend.brand_id == brand_id).order_by(MarketTrend.created_at.desc()).limit(limit)
    return [
        {"trend": t.trend, "category": t.category, "growth_pct": t.growth_pct, "confidence": t.confidence, "created_at": t.created_at.isoformat()}
        for t in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_opportunities(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = select(ProductOpportunity).where(ProductOpportunity.brand_id == brand_id).order_by(ProductOpportunity.created_at.desc()).limit(limit)
    return [
        {"product": o.product, "market_score": o.market_score, "competition": o.competition, "priority": o.priority, "status": o.status}
        for o in (await session.execute(stmt)).scalars().all()
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/research/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def get_sales_insights(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _recent_sales_insights(session, brand_id, limit=limit)


async def get_inventory_signals(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _open_inventory_signals(session, brand_id, limit=limit)


async def get_active_campaigns(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _active_campaigns(session, brand_id, limit=limit)


async def search_catalog(session: AsyncSession, brand_id: str, query: str, limit: int = 15) -> list[dict]:
    """Used by the agent to answer 'do we already sell this?' before
    proposing a product opportunity — matches title, category, or tags."""
    stmt = (
        select(Product)
        .where(
            Product.brand_id == brand_id,
            (Product.title.ilike(f"%{query}%")) | (Product.category.ilike(f"%{query}%")) | (Product.tags.ilike(f"%{query}%")),
        )
        .limit(limit)
    )
    return [
        {"title": p.title, "status": p.status, "category": p.category, "tags": p.tags}
        for p in (await session.execute(stmt)).scalars().all()
    ]


# ── operational writes — conditional, mid-ReAct-loop, real DB rows (see
# agents/research/tools.py). Callers commit; these only add+flush, same
# convention as every other agent's Step 7 / operational-write helpers. ──

async def create_product_opportunity(
    session: AsyncSession, brand_id: str, product: str, market_score: float,
    competition: str, priority: str, reason: str,
) -> dict:
    logger.info("Creating product opportunity for brand=%s product=%s priority=%s", brand_id, product, priority)
    row = ProductOpportunity(
        brand_id=brand_id, product=product, market_score=market_score,
        competition=competition, priority=priority, reason=reason, status="proposed",
    )
    session.add(row)
    await session.flush()
    return {
        "opportunity_id": str(row.id), "product": product, "market_score": market_score,
        "competition": competition, "priority": priority, "status": "proposed",
    }


async def record_competitor_analysis(
    session: AsyncSession, brand_id: str, competitor: str, products: list[str],
    pricing_summary: str, promotions: str, summary: str,
) -> dict:
    logger.info("Recording competitor analysis for brand=%s competitor=%s", brand_id, competitor)
    row = CompetitorAnalysis(
        brand_id=brand_id, competitor=competitor, products=products,
        pricing_summary=pricing_summary, promotions=promotions, summary=summary,
    )
    session.add(row)
    await session.flush()
    return {"competitor_analysis_id": str(row.id), "competitor": competitor}


async def record_pricing_insight(
    session: AsyncSession, brand_id: str, product: str, competitor_price: Optional[float],
    competitor_name: str, recommended_price: Optional[float], reason: str, our_price: Optional[float] = None,
) -> dict:
    logger.info("Recording pricing insight for brand=%s product=%s", brand_id, product)
    row = PricingIntelligence(
        brand_id=brand_id, product=product, our_price=our_price, competitor_price=competitor_price,
        competitor_name=competitor_name, recommended_price=recommended_price, reason=reason,
    )
    session.add(row)
    await session.flush()
    return {"pricing_intelligence_id": str(row.id), "product": product}


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (routine AI-generated output — every run)
# ══════════════════════════════════════════════════════════════════════════════

async def save_trends(session: AsyncSession, brand_id: str, trends: list[dict]) -> None:
    logger.info("Saving %d trends for brand=%s", len(trends), brand_id)
    for t in trends:
        session.add(MarketTrend(
            brand_id=brand_id, trend=t.get("trend", ""), category=t.get("category"),
            growth_pct=t.get("growth_pct"), confidence=t.get("confidence", 0.5),
            source=t.get("source"), summary=t.get("summary", ""),
        ))
    await session.flush()


async def save_research_insights(session: AsyncSession, brand_id: str, insights: list[dict]) -> None:
    logger.info("Saving %d research insights for brand=%s", len(insights), brand_id)
    for i in insights:
        session.add(ResearchInsight(
            brand_id=brand_id, category=i.get("category", "trend"),
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
    (see agents/research/memory.py)."""
    from db import crud_common
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.research import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_trends(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(MarketTrend).where(MarketTrend.brand_id == brand_id).order_by(MarketTrend.created_at.desc()).limit(limit)
    return [
        {
            "id": str(t.id), "trend": t.trend, "category": t.category, "growth_pct": t.growth_pct,
            "confidence": t.confidence, "source": t.source, "summary": t.summary, "created_at": t.created_at.isoformat(),
        }
        for t in (await session.execute(stmt)).scalars().all()
    ]


async def list_competitor_analysis(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(CompetitorAnalysis).where(CompetitorAnalysis.brand_id == brand_id).order_by(CompetitorAnalysis.created_at.desc()).limit(limit)
    return [
        {
            "id": str(c.id), "competitor": c.competitor, "products": c.products,
            "pricing_summary": c.pricing_summary, "promotions": c.promotions,
            "summary": c.summary, "created_at": c.created_at.isoformat(),
        }
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def list_product_opportunities(session: AsyncSession, brand_id: str, status: Optional[str] = None, limit: int = 30) -> list[dict]:
    stmt = select(ProductOpportunity).where(ProductOpportunity.brand_id == brand_id)
    if status:
        stmt = stmt.where(ProductOpportunity.status == status)
    stmt = stmt.order_by(ProductOpportunity.created_at.desc()).limit(limit)
    return [
        {
            "id": str(o.id), "product": o.product, "market_score": o.market_score,
            "competition": o.competition, "priority": o.priority, "reason": o.reason,
            "status": o.status, "created_at": o.created_at.isoformat(),
        }
        for o in (await session.execute(stmt)).scalars().all()
    ]


async def list_pricing_intelligence(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(PricingIntelligence).where(PricingIntelligence.brand_id == brand_id).order_by(PricingIntelligence.created_at.desc()).limit(limit)
    return [
        {
            "id": str(p.id), "product": p.product, "our_price": p.our_price,
            "competitor_price": p.competitor_price, "competitor_name": p.competitor_name,
            "recommended_price": p.recommended_price, "reason": p.reason, "created_at": p.created_at.isoformat(),
        }
        for p in (await session.execute(stmt)).scalars().all()
    ]


async def list_research_insights(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(ResearchInsight).where(ResearchInsight.brand_id == brand_id).order_by(ResearchInsight.created_at.desc()).limit(limit)
    return [
        {"id": str(i.id), "category": i.category, "severity": i.severity, "message": i.message,
         "confidence": i.confidence, "created_at": i.created_at.isoformat()}
        for i in (await session.execute(stmt)).scalars().all()
    ]