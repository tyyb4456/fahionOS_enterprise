"""
Product / Merchandising Agent — read/write layer.

Table ownership:
  - reads but doesn't own: Product/ProductVariant (Shopify catalog mirror),
    OrderLineItem/SalesOrder (variant-level sales breakdown), Return
    (Shopify refund/return records — return-reason pattern signal),
    ExchangeRecord/SupportTicket/SupportInsight (Customer Support Agent's
    outputs — see the "Customer feedback" section below), InventoryAlert
    (Inventory's outputs), ProductOpportunity/MarketTrend/CompetitorAnalysis
    (Research's outputs), MarketingInsight/MarketingCampaign (Marketing's
    outputs), Supplier/SupplierQuote (Supplier's outputs). Reading another
    agent's AI-output tables directly instead of recomputing the same
    analysis is the established pattern here — see the note already in
    agents/marketing/tools.py / db/crud_marketing.py.
  - owns outright: ProductProposal, Collection, ProductLifecycle,
    MerchandisingInsight, + the shared AgentExecutionLog/AgentMemory via
    db/crud_common.py.

ProductProposal.source_opportunity_id is a light FK into Research's own
ProductOpportunity table — the same "shared Postgres, reference across
agents' tables instead of duplicating them" pattern already used by
ReorderRecommendation.purchase_order_id and Supplier's shared writes into
Inventory's own tables.

Customer feedback signal (confirmed against the real Customer Support
Agent schema — db/models.py / db/crud_customer_support.py):
  - Return.return_reason (Shopify-synced refund note, has a real `sku`
    column) — categorized via agents/product/analytics.py's keyword
    matcher into sizing/defect/wrong_item/changed_mind/shipping/other.
  - ExchangeRecord.original_sku -> new_sku — the strongest sizing-
    confusion signal available: a SKU customers keep exchanging OUT of is
    hard evidence, not inferred from free text.
  - SupportInsight where category="product" — Customer Support's own
    already-computed analysis; read directly rather than re-deriving
    anything from raw ticket/conversation text (same pattern as reading
    Research's MarketTrend/ProductOpportunity elsewhere in this agent).
  - SupportTicket.issue_type volume, as lightweight overall context.
    Deliberately NOT broken down per-SKU: SupportTicket has no sku column,
    and RefundRecord (which has amount/reason) is only order-level too —
    forcing either into a per-product breakdown via a shopify_order_id
    join would silently misattribute a refund/ticket to every line item
    on that order. Left out rather than faking precision the schema
    doesn't support.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Collection, CompetitorAnalysis, ExchangeRecord, InventoryAlert,
    MarketingCampaign, MarketingInsight, MarketTrend, MerchandisingInsight,
    OrderLineItem, Product, ProductLifecycle, ProductOpportunity,
    ProductProposal, ProductVariant, Return, SalesOrder, Supplier,
    SupplierQuote, SupportInsight, SupportTicket,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Context Builder
# ══════════════════════════════════════════════════════════════════════════════

async def get_business_context(session: AsyncSession, brand_id: str, category: Optional[str] = None) -> dict[str, Any]:
    logger.info("Building product context for brand=%s category=%s", brand_id, category)
    return {
        "catalog": await _catalog_summary(session, brand_id, category=category),
        "variant_sales_breakdown": await _variant_sales_breakdown(session, brand_id, days=60),
        "inventory_signals": await _open_inventory_signals(session, brand_id, limit=10),
        "research_opportunities": await _research_opportunities(session, brand_id, limit=10),
        "market_trends": await _recent_market_trends(session, brand_id, limit=8),
        "competitor_analysis": await _recent_competitor_analysis(session, brand_id, limit=5),
        "marketing_insights": await _recent_marketing_insights(session, brand_id, limit=6),
        "active_campaigns": await _active_campaigns(session, brand_id, limit=5),
        "margin_snapshot": await _margin_snapshot(session, brand_id, limit=10),
        "supplier_snapshot": await _supplier_snapshot(session, brand_id, limit=10),
        "previous_proposals": await _recent_proposals(session, brand_id, limit=8),
        "previous_collections": await _recent_collections(session, brand_id, limit=5),
        "product_lifecycle_snapshot": await _lifecycle_snapshot(session, brand_id, limit=15),
        "customer_feedback_signals": await _customer_feedback_signals(session, brand_id, days=90),
    }


async def _catalog_summary(session: AsyncSession, brand_id: str, category: Optional[str] = None, limit: int = 30) -> list[dict]:
    stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.brand_id == brand_id, Product.status == "active")
    )
    if category:
        stmt = stmt.where((Product.category.ilike(f"%{category}%")) | (Product.tags.ilike(f"%{category}%")))
    stmt = stmt.order_by(ProductVariant.inventory_quantity.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "sku": v.sku, "title": p.title, "variant_title": v.title, "category": p.category,
            "tags": p.tags, "price": v.price, "cost_price": v.cost_price,
            "inventory_quantity": v.inventory_quantity, "image_url": p.image_url,
        }
        for v, p in rows
    ]


async def _variant_sales_breakdown(
    session: AsyncSession, brand_id: str, product_title: Optional[str] = None, days: int = 60,
) -> list[dict]:
    """Revenue/units per product+variant over the window — the data behind
    "Black = 45% of sales, Cream = 27%" style variant-mix decisions. Not
    something any other agent computes at this granularity."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            OrderLineItem.name, OrderLineItem.sku,
            func.sum(OrderLineItem.quantity).label("units"),
            func.sum(OrderLineItem.price * OrderLineItem.quantity).label("revenue"),
        )
        .join(SalesOrder, SalesOrder.id == OrderLineItem.order_id)
        .where(
            SalesOrder.brand_id == brand_id, SalesOrder.created_at >= since,
            SalesOrder.financial_status == "paid",
        )
    )
    if product_title:
        stmt = stmt.where(OrderLineItem.name.ilike(f"%{product_title}%"))
    stmt = stmt.group_by(OrderLineItem.name, OrderLineItem.sku).order_by(func.sum(OrderLineItem.price * OrderLineItem.quantity).desc())
    rows = (await session.execute(stmt)).all()
    return [
        {"variant": r.name, "sku": r.sku, "units": int(r.units or 0), "revenue": round(float(r.revenue or 0), 2)}
        for r in rows
    ]


async def _open_inventory_signals(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    stmt = (
        select(InventoryAlert)
        .where(
            InventoryAlert.brand_id == brand_id, InventoryAlert.resolved == False,  # noqa: E712
            InventoryAlert.type.in_(["overstock", "stockout_risk", "velocity_spike", "sales_agent_flag"]),
        )
        .order_by(InventoryAlert.created_at.desc())
        .limit(limit)
    )
    return [
        {"type": a.type, "severity": a.severity, "sku": a.sku, "message": a.message}
        for a in (await session.execute(stmt)).scalars().all()
    ]


async def _research_opportunities(session: AsyncSession, brand_id: str, status: Optional[str] = "proposed", limit: int = 10) -> list[dict]:
    stmt = select(ProductOpportunity).where(ProductOpportunity.brand_id == brand_id)
    if status:
        stmt = stmt.where(ProductOpportunity.status == status)
    stmt = stmt.order_by(ProductOpportunity.created_at.desc()).limit(limit)
    return [
        {
            "opportunity_id": str(o.id), "product": o.product, "market_score": o.market_score,
            "competition": o.competition, "priority": o.priority, "reason": o.reason, "status": o.status,
        }
        for o in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_market_trends(session: AsyncSession, brand_id: str, limit: int = 8) -> list[dict]:
    stmt = select(MarketTrend).where(MarketTrend.brand_id == brand_id).order_by(MarketTrend.created_at.desc()).limit(limit)
    return [
        {"trend": t.trend, "category": t.category, "growth_pct": t.growth_pct, "confidence": t.confidence, "summary": t.summary}
        for t in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_competitor_analysis(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = select(CompetitorAnalysis).where(CompetitorAnalysis.brand_id == brand_id).order_by(CompetitorAnalysis.created_at.desc()).limit(limit)
    return [
        {"competitor": c.competitor, "products": c.products, "pricing_summary": c.pricing_summary, "promotions": c.promotions, "summary": c.summary}
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_marketing_insights(session: AsyncSession, brand_id: str, limit: int = 6) -> list[dict]:
    stmt = select(MarketingInsight).where(MarketingInsight.brand_id == brand_id).order_by(MarketingInsight.created_at.desc()).limit(limit)
    return [
        {"insight": i.insight, "confidence": i.confidence, "priority": i.priority}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def _active_campaigns(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = (
        select(MarketingCampaign)
        .where(MarketingCampaign.brand_id == brand_id, MarketingCampaign.status.in_(["launched", "scheduled"]))
        .order_by(MarketingCampaign.created_at.desc())
        .limit(limit)
    )
    return [
        {"name": c.name, "goal": c.goal, "platform": c.platform, "target_audience": c.target_audience}
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def _margin_snapshot(session: AsyncSession, brand_id: str, limit: int = 10) -> dict:
    from agents.finance import analytics as finance_analytics

    stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.brand_id == brand_id, Product.status == "active")
    )
    rows = (await session.execute(stmt)).all()
    variants = [
        {"sku": v.sku, "title": p.title, "price": v.price, "cost_price": v.cost_price, "inventory_quantity": v.inventory_quantity}
        for v, p in rows
    ]
    return finance_analytics.rank_products_by_margin(variants, top_n=limit)


async def _supplier_snapshot(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    stmt = select(Supplier).where(Supplier.brand_id == brand_id).limit(limit)
    return [
        {
            "supplier_id": str(s.id), "name": s.name, "lead_time_days": s.lead_time_days,
            "minimum_order_qty": s.minimum_order_qty, "reliability_score": s.reliability_score,
            "quality_score": s.quality_score,
        }
        for s in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_proposals(session: AsyncSession, brand_id: str, limit: int = 8) -> list[dict]:
    stmt = select(ProductProposal).where(ProductProposal.brand_id == brand_id).order_by(ProductProposal.created_at.desc()).limit(limit)
    return [
        {
            "id": str(p.id), "product_name": p.product_name, "category": p.category, "status": p.status,
            "composite_score": p.composite_score, "target_price": p.target_price,
        }
        for p in (await session.execute(stmt)).scalars().all()
    ]


async def _recent_collections(session: AsyncSession, brand_id: str, limit: int = 5) -> list[dict]:
    stmt = select(Collection).where(Collection.brand_id == brand_id).order_by(Collection.created_at.desc()).limit(limit)
    return [
        {"id": str(c.id), "name": c.name, "season": c.season, "status": c.status, "product_names": c.product_names}
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def _lifecycle_snapshot(session: AsyncSession, brand_id: str, limit: int = 15) -> list[dict]:
    stmt = select(ProductLifecycle).where(ProductLifecycle.brand_id == brand_id).order_by(ProductLifecycle.stage_updated_at.desc()).limit(limit)
    return [
        {"product_ref": l.product_ref, "stage": l.stage, "performance_score": l.performance_score, "notes": l.notes}
        for l in (await session.execute(stmt)).scalars().all()
    ]


# ── Customer feedback signal (real Customer Support Agent tables) ─────────

async def _return_pattern_signals(session: AsyncSession, brand_id: str, days: int = 90, limit_products: int = 15) -> list[dict]:
    """Return.return_reason (Shopify-synced refund note, db/models.py,
    populated by api/routers/shopify_webhook.py) categorized and grouped
    by product. Real sku column, no join guesswork needed."""
    from agents.product import analytics as product_analytics

    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(Return.sku, Return.product_name, Return.return_reason).where(
        Return.brand_id == brand_id, Return.refunded_at.is_not(None), Return.refunded_at >= since,
    )
    rows = (await session.execute(stmt)).all()
    returns = [{"sku": r.sku, "product_name": r.product_name, "return_reason": r.return_reason or ""} for r in rows]
    return product_analytics.summarize_return_patterns(returns)[:limit_products]


async def _exchange_pattern_signals(session: AsyncSession, brand_id: str, days: int = 90, limit_skus: int = 15) -> list[dict]:
    """ExchangeRecord.original_sku -> new_sku (Customer Support Agent's
    create_exchange, db/crud_customer_support.py), grouped by the SKU
    customers exchanged OUT of. This is the strongest sizing-confusion
    signal available — a real, repeated exchange pattern, not an inferred
    one from free text."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(ExchangeRecord.original_sku, ExchangeRecord.new_sku, func.count().label("count"))
        .where(ExchangeRecord.brand_id == brand_id, ExchangeRecord.created_at >= since)
        .group_by(ExchangeRecord.original_sku, ExchangeRecord.new_sku)
    )
    rows = (await session.execute(stmt)).all()

    by_original: dict[str, dict] = {}
    for r in rows:
        entry = by_original.setdefault(
            r.original_sku, {"original_sku": r.original_sku, "total_exchanges": 0, "exchanged_to": []},
        )
        entry["total_exchanges"] += r.count
        entry["exchanged_to"].append({"sku": r.new_sku, "count": r.count})

    ranked = sorted(by_original.values(), key=lambda e: -e["total_exchanges"])
    for entry in ranked:
        entry["exchanged_to"].sort(key=lambda x: -x["count"])
    return ranked[:limit_skus]


async def _support_insight_signals(session: AsyncSession, brand_id: str, limit: int = 10) -> list[dict]:
    """Customer Support Agent's own SupportInsight rows where
    category='product' — read their analysis directly rather than
    re-deriving anything from raw ticket/conversation text, same pattern
    as reading Research's MarketTrend/ProductOpportunity elsewhere in
    this agent."""
    stmt = (
        select(SupportInsight)
        .where(SupportInsight.brand_id == brand_id, SupportInsight.category == "product")
        .order_by(SupportInsight.created_at.desc())
        .limit(limit)
    )
    return [
        {"severity": i.severity, "message": i.message, "confidence": i.confidence}
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def _ticket_volume_by_issue_type(session: AsyncSession, brand_id: str, days: int = 90) -> list[dict]:
    """Lightweight overall ticket volume by issue_type — SupportTicket has
    no sku column, so this is deliberately NOT broken down per-product
    (see module docstring). Useful only as general context, e.g. "12
    return tickets, 8 product_question tickets in the last 90 days"."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(SupportTicket.issue_type, func.count().label("count"))
        .where(SupportTicket.brand_id == brand_id, SupportTicket.created_at >= since)
        .group_by(SupportTicket.issue_type)
        .order_by(func.count().desc())
    )
    rows = (await session.execute(stmt)).all()
    return [{"issue_type": r.issue_type, "count": r.count} for r in rows]


async def _customer_feedback_signals(session: AsyncSession, brand_id: str, days: int = 90) -> dict:
    return {
        "return_reason_patterns": await _return_pattern_signals(session, brand_id, days=days),
        "exchange_patterns_by_sku": await _exchange_pattern_signals(session, brand_id, days=days),
        "support_insights_product": await _support_insight_signals(session, brand_id),
        "support_ticket_volume_by_type": await _ticket_volume_by_issue_type(session, brand_id, days=days),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tool-backed lookups (called on-demand from the ReAct loop, see
# agents/product/tools.py)
# ══════════════════════════════════════════════════════════════════════════════

async def search_our_catalog(session: AsyncSession, brand_id: str, query: str, limit: int = 15) -> list[dict]:
    """Check whether we already sell something like this before proposing
    it as new — same role as Research's search_our_catalog, kept as its
    own local query rather than a cross-crud-module call (every agent's
    crud module queries other agents' tables directly, not through their
    crud functions)."""
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


async def get_variant_performance(session: AsyncSession, brand_id: str, product_title: str, days: int = 90) -> list[dict]:
    return await _variant_sales_breakdown(session, brand_id, product_title=product_title, days=days)


async def get_research_opportunities(session: AsyncSession, brand_id: str, status: Optional[str] = None, limit: int = 20) -> list[dict]:
    return await _research_opportunities(session, brand_id, status=status, limit=limit)


async def get_market_trends(session: AsyncSession, brand_id: str, limit: int = 15) -> list[dict]:
    return await _recent_market_trends(session, brand_id, limit=limit)


async def get_competitor_analysis(session: AsyncSession, brand_id: str, limit: int = 15) -> list[dict]:
    return await _recent_competitor_analysis(session, brand_id, limit=limit)


async def get_inventory_signals(session: AsyncSession, brand_id: str, limit: int = 20) -> list[dict]:
    return await _open_inventory_signals(session, brand_id, limit=limit)


async def get_marketing_signals(session: AsyncSession, brand_id: str) -> dict:
    return {
        "insights": await _recent_marketing_insights(session, brand_id, limit=15),
        "active_campaigns": await _active_campaigns(session, brand_id, limit=10),
    }


async def get_margin_for_sku(session: AsyncSession, brand_id: str, sku: str) -> Optional[dict]:
    from agents.finance import analytics as finance_analytics

    stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.brand_id == brand_id, ProductVariant.sku == sku)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    variant, product = row
    margin_pct = finance_analytics.calculate_margin(variant.cost_price, variant.price)
    return {
        "sku": sku, "title": product.title, "price": variant.price,
        "cost_price": variant.cost_price, "margin_pct": margin_pct,
    }


async def find_feasible_suppliers(session: AsyncSession, brand_id: str, query: str = "", limit: int = 10) -> list[dict]:
    """Which on-file suppliers could plausibly make this — same read
    Supplier Agent's own find_suppliers does, kept local per the
    'query other agents' tables directly' convention."""
    stmt = select(Supplier).where(Supplier.brand_id == brand_id)
    if query:
        stmt = stmt.where(Supplier.name.ilike(f"%{query}%") | Supplier.notes.ilike(f"%{query}%"))
    stmt = stmt.limit(limit)
    suppliers = (await session.execute(stmt)).scalars().all()
    results = []
    for s in suppliers:
        quote_stmt = (
            select(SupplierQuote)
            .where(SupplierQuote.brand_id == brand_id, SupplierQuote.supplier_id == s.id)
            .order_by(SupplierQuote.created_at.desc())
            .limit(1)
        )
        latest_quote = (await session.execute(quote_stmt)).scalar_one_or_none()
        results.append({
            "supplier_id": str(s.id), "name": s.name, "lead_time_days": s.lead_time_days,
            "minimum_order_qty": s.minimum_order_qty, "reliability_score": s.reliability_score,
            "quality_score": s.quality_score,
            "latest_quote_unit_price": latest_quote.unit_price if latest_quote else None,
        })
    return results


async def get_customer_feedback_signals(session: AsyncSession, brand_id: str, days: int = 90) -> dict:
    return await _customer_feedback_signals(session, brand_id, days=days)


# ── operational writes — real, immediate DB changes made mid-ReAct-loop by
# agents/product/tools.py. Callers commit; these functions only add+flush,
# same convention as every other agent's Step 7 / operational-write helpers. ──

async def create_product_proposal(
    session: AsyncSession, brand_id: str, product_name: str, category: str, description: str,
    variants: list[str], sizes: list[str], target_price: Optional[float],
    market_demand: float, brand_fit: float, competition: float, supplier_feasibility: float,
    expected_margin: Optional[float], composite_score: float, recommended_initial_quantity: Optional[int],
    reason: str, source_opportunity_id: Optional[str] = None, status: str = "proposed",
) -> dict:
    logger.info("Creating product proposal for brand=%s product=%s score=%.2f", brand_id, product_name, composite_score)
    src_uuid = None
    if source_opportunity_id:
        try:
            src_uuid = uuid.UUID(source_opportunity_id)
        except ValueError:
            src_uuid = None

    proposal = ProductProposal(
        brand_id=brand_id, product_name=product_name, category=category, description=description,
        variants=variants, sizes=sizes, target_price=target_price,
        market_demand=market_demand, brand_fit=brand_fit, competition=competition,
        supplier_feasibility=supplier_feasibility, expected_margin=expected_margin,
        composite_score=composite_score, recommended_initial_quantity=recommended_initial_quantity,
        status=status, reason=reason, source_opportunity_id=src_uuid,
    )
    session.add(proposal)
    await session.flush()
    return {"proposal_id": str(proposal.id), "product_name": product_name, "status": status, "composite_score": composite_score}


async def update_proposal_status(
    session: AsyncSession, brand_id: str, proposal_id: str, status: str,
    shopify_product_id: Optional[int] = None, note: str = "",
) -> dict:
    try:
        pid = uuid.UUID(proposal_id)
    except ValueError:
        return {"error": f"Invalid proposal_id '{proposal_id}'."}

    proposal = (await session.execute(
        select(ProductProposal).where(ProductProposal.brand_id == brand_id, ProductProposal.id == pid)
    )).scalar_one_or_none()
    if not proposal:
        return {"error": f"No product proposal '{proposal_id}' found for this brand."}

    proposal.status = status
    if shopify_product_id is not None:
        proposal.shopify_product_id = shopify_product_id
    if note:
        proposal.reason = f"{proposal.reason}\n[{status}] {note}".strip()
    proposal.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return {"proposal_id": proposal_id, "status": status, "shopify_product_id": proposal.shopify_product_id}


async def upsert_product_lifecycle(
    session: AsyncSession, brand_id: str, product_ref: str, stage: str,
    performance_score: Optional[float] = None, next_review_date: Optional[date] = None, notes: str = "",
) -> dict:
    existing = (await session.execute(
        select(ProductLifecycle).where(ProductLifecycle.brand_id == brand_id, ProductLifecycle.product_ref == product_ref)
    )).scalar_one_or_none()

    if existing:
        existing.stage = stage
        if performance_score is not None:
            existing.performance_score = performance_score
        if next_review_date is not None:
            existing.next_review_date = next_review_date
        if notes:
            existing.notes = notes
        existing.stage_updated_at = datetime.now(timezone.utc)
    else:
        existing = ProductLifecycle(
            brand_id=brand_id, product_ref=product_ref, stage=stage,
            performance_score=performance_score, next_review_date=next_review_date, notes=notes,
        )
        session.add(existing)

    await session.flush()
    return {"product_ref": product_ref, "stage": stage, "performance_score": existing.performance_score}


async def create_collection(
    session: AsyncSession, brand_id: str, name: str, season: str, theme: str,
    product_names: list[str], launch_date: Optional[date] = None, status: str = "planning",
) -> dict:
    logger.info("Creating collection for brand=%s name=%s", brand_id, name)
    row = Collection(
        brand_id=brand_id, name=name, season=season, theme=theme,
        product_names=product_names, launch_date=launch_date, status=status,
    )
    session.add(row)
    await session.flush()
    return {"collection_id": str(row.id), "name": name, "product_count": len(product_names)}


async def add_product_to_collection(session: AsyncSession, brand_id: str, collection_id: str, product_name: str) -> dict:
    try:
        cid = uuid.UUID(collection_id)
    except ValueError:
        return {"error": f"Invalid collection_id '{collection_id}'."}

    collection = (await session.execute(
        select(Collection).where(Collection.brand_id == brand_id, Collection.id == cid)
    )).scalar_one_or_none()
    if not collection:
        return {"error": f"No collection '{collection_id}' found for this brand."}

    names = list(collection.product_names or [])
    if product_name not in names:
        names.append(product_name)
    collection.product_names = names
    collection.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return {"collection_id": collection_id, "product_names": names}


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Persistence Layer (AI-generated intelligence only — the routine,
# always-attempted per-run output; mirrors Research's trends/insights split)
# ══════════════════════════════════════════════════════════════════════════════

async def save_proposals(session: AsyncSession, brand_id: str, proposals: list[dict]) -> list[str]:
    logger.info("Saving %d product proposals for brand=%s", len(proposals), brand_id)
    ids = []
    for p in proposals:
        result = await create_product_proposal(
            session, brand_id,
            product_name=p.get("product_name", "Untitled product"),
            category=p.get("category", ""), description=p.get("description", ""),
            variants=p.get("variants", []), sizes=p.get("sizes", []),
            target_price=p.get("target_price"), market_demand=p.get("market_demand", 0.5),
            brand_fit=p.get("brand_fit", 0.5), competition=p.get("competition", 0.5),
            supplier_feasibility=p.get("supplier_feasibility", 0.5),
            expected_margin=p.get("expected_margin"),
            composite_score=p.get("expected_demand_score", 0.5),
            recommended_initial_quantity=p.get("recommended_initial_quantity"),
            reason=p.get("reason", ""), status=p.get("status", "proposed"),
        )
        ids.append(result["proposal_id"])
    return ids


async def save_collections(session: AsyncSession, brand_id: str, collections: list[dict]) -> list[str]:
    logger.info("Saving %d collections for brand=%s", len(collections), brand_id)
    ids = []
    for c in collections:
        launch_date = None
        if c.get("launch_date"):
            try:
                launch_date = date.fromisoformat(c["launch_date"])
            except ValueError:
                launch_date = None
        result = await create_collection(
            session, brand_id, name=c.get("name", "Untitled collection"),
            season=c.get("season", ""), theme=c.get("theme", ""),
            product_names=c.get("product_names", []), launch_date=launch_date,
            status=c.get("status", "planning"),
        )
        ids.append(result["collection_id"])
    return ids


async def save_lifecycle_updates(session: AsyncSession, brand_id: str, updates: list[dict]) -> None:
    logger.info("Saving %d lifecycle updates for brand=%s", len(updates), brand_id)
    for u in updates:
        product_ref = u.get("product_ref")
        if not product_ref:
            continue
        await upsert_product_lifecycle(
            session, brand_id, product_ref=product_ref, stage=u.get("stage", "idea"),
            performance_score=u.get("performance_score"), notes=u.get("notes", ""),
        )


async def save_merchandising_insights(session: AsyncSession, brand_id: str, insights: list[dict]) -> None:
    logger.info("Saving %d merchandising insights for brand=%s", len(insights), brand_id)
    for i in insights:
        session.add(MerchandisingInsight(
            brand_id=brand_id, category=i.get("category", "opportunity"),
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
    (so future runs can retrieve it by meaning, see agents/product/memory.py)."""
    from db import crud_common
    await crud_common.save_agent_memory_record(session, brand_id, agent, content, kind=kind)

    from agents.product import memory as rag  # local import avoids a load-time cycle
    await rag.store_memory(brand_id, content, kind=kind)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard reads
# ══════════════════════════════════════════════════════════════════════════════

async def list_proposals(session: AsyncSession, brand_id: str, status: Optional[str] = None, limit: int = 30) -> list[dict]:
    stmt = select(ProductProposal).where(ProductProposal.brand_id == brand_id)
    if status:
        stmt = stmt.where(ProductProposal.status == status)
    stmt = stmt.order_by(ProductProposal.created_at.desc()).limit(limit)
    return [
        {
            "id": str(p.id), "product_name": p.product_name, "category": p.category,
            "description": p.description, "variants": p.variants, "sizes": p.sizes,
            "target_price": p.target_price, "market_demand": p.market_demand, "brand_fit": p.brand_fit,
            "competition": p.competition, "supplier_feasibility": p.supplier_feasibility,
            "expected_margin": p.expected_margin, "composite_score": p.composite_score,
            "recommended_initial_quantity": p.recommended_initial_quantity, "status": p.status,
            "reason": p.reason, "shopify_product_id": p.shopify_product_id,
            "created_at": p.created_at.isoformat(),
        }
        for p in (await session.execute(stmt)).scalars().all()
    ]


async def list_collections(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(Collection).where(Collection.brand_id == brand_id).order_by(Collection.created_at.desc()).limit(limit)
    return [
        {
            "id": str(c.id), "name": c.name, "season": c.season, "theme": c.theme,
            "product_names": c.product_names, "launch_date": c.launch_date.isoformat() if c.launch_date else None,
            "status": c.status, "created_at": c.created_at.isoformat(),
        }
        for c in (await session.execute(stmt)).scalars().all()
    ]


async def list_lifecycle(session: AsyncSession, brand_id: str, stage: Optional[str] = None, limit: int = 50) -> list[dict]:
    stmt = select(ProductLifecycle).where(ProductLifecycle.brand_id == brand_id)
    if stage:
        stmt = stmt.where(ProductLifecycle.stage == stage)
    stmt = stmt.order_by(ProductLifecycle.stage_updated_at.desc()).limit(limit)
    return [
        {
            "product_ref": l.product_ref, "stage": l.stage, "performance_score": l.performance_score,
            "next_review_date": l.next_review_date.isoformat() if l.next_review_date else None,
            "notes": l.notes, "stage_updated_at": l.stage_updated_at.isoformat(),
        }
        for l in (await session.execute(stmt)).scalars().all()
    ]


async def list_merchandising_insights(session: AsyncSession, brand_id: str, limit: int = 30) -> list[dict]:
    stmt = select(MerchandisingInsight).where(MerchandisingInsight.brand_id == brand_id).order_by(MerchandisingInsight.created_at.desc()).limit(limit)
    return [
        {"id": str(i.id), "category": i.category, "severity": i.severity, "message": i.message,
         "confidence": i.confidence, "created_at": i.created_at.isoformat()}
        for i in (await session.execute(stmt)).scalars().all()
    ]