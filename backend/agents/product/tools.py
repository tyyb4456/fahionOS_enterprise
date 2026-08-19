"""
Internal tools for the Product / Merchandising Agent's ReAct loop —
everything that isn't a live Shopify call (those come from shopify-mcp,
see mcp_client.py). Each factory below binds `brand_id` in a closure so the
LLM never has to supply it — same reasoning as agents/common/tool_scoping.py.

Four flavors of tool live here:
  - lookups (read our own + other agents' tables — Sales' variant-level
    revenue breakdown, Research's opportunities/trends/competitor reads,
    Inventory's alerts, Marketing's insights/campaigns, Finance's margin
    math, Supplier's on-file suppliers)
  - deterministic helpers (agents/product/analytics.py — opportunity
    scoring, initial production quantity, variant-mix ranking: things that
    should be computed, not guessed by the LLM)
  - creative generation (generate_product_copy — a dedicated,
    higher-temperature LLM call for description/SEO/tags, same separation
    reasoning as Marketing's generate_social_caption)
  - operational writes (create_product_proposal, update_proposal_status,
    update_product_lifecycle_stage, create_collection,
    add_product_to_collection, notify_brand_owner) — real, immediate DB
    changes made mid-ReAct-loop. Actually creating/publishing/archiving the
    product on Shopify itself is a separate MCP tool (create_product /
    update_product_details / add_product_variant, see mcp_client.py) — the
    LLM calls that directly, then update_proposal_status /
    update_product_lifecycle_stage to record what happened.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.common.notify_tools import make_notify_brand_owner_tool
from db import crud_product as crud
from db.session import AsyncSessionLocal

from . import analytics
from . import memory as rag

logger = logging.getLogger(__name__)

PRODUCT_ANALYSIS_MODEL = os.getenv("PRODUCT_ANALYSIS_MODEL", "claude-sonnet-5")


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_search_catalog_tool(brand_id),
        _make_variant_performance_tool(brand_id),
        _make_research_opportunities_tool(brand_id),
        _make_market_trends_tool(brand_id),
        _make_competitor_analysis_tool(brand_id),
        _make_inventory_signals_tool(brand_id),
        _make_marketing_signals_tool(brand_id),
        _make_margin_lookup_tool(brand_id),
        _make_supplier_feasibility_tool(brand_id),
        _make_score_opportunity_tool(),
        _make_production_quantity_tool(),
        _make_variant_mix_tool(),
        _make_product_copy_tool(brand_id),
        _make_create_proposal_tool(brand_id),
        _make_update_proposal_status_tool(brand_id),
        _make_lifecycle_update_tool(brand_id),
        _make_create_collection_tool(brand_id),
        _make_add_to_collection_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
        make_notify_brand_owner_tool(brand_id, agent_name="Product Agent"),
    ]


class _NoArgs(BaseModel):
    pass


# ── search_our_catalog ────────────────────────────────────────────────────

class _CatalogSearchArgs(BaseModel):
    query: str = Field(description="Product name, category, or tag to check against our own catalog, e.g. 'cargo pants'.")


def _make_search_catalog_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.search_our_catalog(session, brand_id, query)

    return StructuredTool.from_function(
        name="search_our_catalog",
        description=(
            "Check whether we already sell something like this before proposing it as a new product — "
            "always call this before create_product_proposal. If we already sell it, this is a variant/"
            "pricing/promotion question, not a launch opportunity."
        ),
        args_schema=_CatalogSearchArgs,
        coroutine=_run,
    )


# ── get_variant_performance ────────────────────────────────────────────────

class _VariantPerfArgs(BaseModel):
    product_title: str = Field(description="Product title (fuzzy match), e.g. 'Oversized Hoodie'.")
    days: int = Field(default=90, description="Look-back window in days.")


def _make_variant_performance_tool(brand_id: str) -> StructuredTool:
    async def _run(product_title: str, days: int = 90) -> list[dict]:
        async with AsyncSessionLocal() as session:
            breakdown = await crud.get_variant_performance(session, brand_id, product_title, days=days)
        return analytics.rank_variant_mix(breakdown)

    return StructuredTool.from_function(
        name="get_variant_performance",
        description=(
            "Revenue/unit share per color/size variant of a product, with a keep/cut/expand "
            "recommendation for each — the real numbers behind a variant-mix decision (e.g. 'Black is "
            "45% of sales, Red is under 5% — cut candidate'). Use before recommending which variants to "
            "keep, expand, or discontinue."
        ),
        args_schema=_VariantPerfArgs,
        coroutine=_run,
    )


# ── get_research_opportunities / get_market_trends / get_competitor_analysis ─

class _StatusFilterArgs(BaseModel):
    status: Optional[str] = Field(default=None, description="Optional status filter: 'proposed' | 'approved' | 'rejected'. Omit for all.")


def _make_research_opportunities_tool(brand_id: str) -> StructuredTool:
    async def _run(status: Optional[str] = None) -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_research_opportunities(session, brand_id, status=status)

    return StructuredTool.from_function(
        name="get_research_opportunities",
        description="Read the Research Agent's proposed product opportunities (external trend + competitor evidence) — the usual trigger for a new product proposal here. Don't re-research the web yourself; Research already did that.",
        args_schema=_StatusFilterArgs,
        coroutine=_run,
    )


def _make_market_trends_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_market_trends(session, brand_id)

    return StructuredTool.from_function(
        name="get_market_trends",
        description="Read the Research Agent's recorded market trends (growth %, confidence) — use growth_pct as the market_demand signal for score_product_opportunity.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_competitor_analysis_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_competitor_analysis(session, brand_id)

    return StructuredTool.from_function(
        name="get_competitor_analysis",
        description="Read the Research Agent's competitor analyses — count how many named competitors already sell something similar before scoring competition.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


# ── get_inventory_signals / get_marketing_signals ─────────────────────────

def _make_inventory_signals_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_inventory_signals(session, brand_id)

    return StructuredTool.from_function(
        name="get_inventory_signals",
        description="Read the Inventory Agent's open alerts — overstock signals dead-stock risk worth a retirement/clearance review; stockout on a bestseller signals a variant worth expanding.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_marketing_signals_tool(brand_id: str) -> StructuredTool:
    async def _run() -> dict:
        async with AsyncSessionLocal() as session:
            return await crud.get_marketing_signals(session, brand_id)

    return StructuredTool.from_function(
        name="get_marketing_signals",
        description="Read the Marketing Agent's recent insights and active campaigns — tells you what customers are actually responding to right now.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


# ── get_margin_for_sku / check_supplier_feasibility ───────────────────────

class _SkuArgs(BaseModel):
    sku: str = Field(description="SKU to check margin for.")


def _make_margin_lookup_tool(brand_id: str) -> StructuredTool:
    async def _run(sku: str) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.get_margin_for_sku(session, brand_id, sku)
        return result or {"error": f"SKU '{sku}' not found."}

    return StructuredTool.from_function(
        name="get_margin_for_sku",
        description="Real gross margin (price vs on-file cost_price) for one existing SKU — useful as a reference price point for a new, similar product.",
        args_schema=_SkuArgs,
        coroutine=_run,
    )


class _SupplierFeasibilityArgs(BaseModel):
    query: str = Field(default="", description="Supplier name or product/category keyword to match against supplier notes. Leave blank to list all on-file suppliers.")


def _make_supplier_feasibility_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str = "") -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.find_feasible_suppliers(session, brand_id, query=query)

    return StructuredTool.from_function(
        name="check_supplier_feasibility",
        description=(
            "Which on-file suppliers (with lead time, MOQ, reliability, and their latest quote if any) "
            "could plausibly make a proposed product. Use the lead time + reliability as inputs to "
            "score_product_opportunity's supplier_feasibility. If nothing matches, say so — the Supplier "
            "Agent owns actually sourcing a new one, not this agent."
        ),
        args_schema=_SupplierFeasibilityArgs,
        coroutine=_run,
    )


# ── deterministic helpers ──────────────────────────────────────────────────

class _ScoreOpportunityArgs(BaseModel):
    growth_pct: Optional[float] = Field(default=None, description="Demand growth % from get_market_trends, e.g. 42.0 for 42%. Omit if unknown.")
    competitor_count: int = Field(default=0, description="How many competitors (from get_competitor_analysis) already sell this.")
    brand_fit: float = Field(description="0-1 — your own assessment of how well this fits the brand's identity/positioning, informed by retrieve_policy. Don't default this blindly.")
    supplier_lead_time_days: Optional[int] = Field(default=None, description="From check_supplier_feasibility, if a feasible supplier was found.")
    supplier_reliability: Optional[float] = Field(default=None, description="0-1, from check_supplier_feasibility.")
    unit_cost: Optional[float] = Field(default=None, description="Estimated or quoted unit cost, if known.")
    target_price: Optional[float] = Field(default=None, description="Proposed selling price.")


def _make_score_opportunity_tool() -> StructuredTool:
    async def _run(
        brand_fit: float, growth_pct: Optional[float] = None, competitor_count: int = 0,
        supplier_lead_time_days: Optional[int] = None, supplier_reliability: Optional[float] = None,
        unit_cost: Optional[float] = None, target_price: Optional[float] = None,
    ) -> dict:
        return analytics.score_product_opportunity(
            growth_pct, competitor_count, brand_fit,
            supplier_lead_time_days=supplier_lead_time_days, supplier_reliability=supplier_reliability,
            unit_cost=unit_cost, target_price=target_price,
        )

    return StructuredTool.from_function(
        name="score_product_opportunity",
        description=(
            "Turn market/brand/competition/supplier/margin signals into a composite opportunity score "
            "and a recommended true/false — use this instead of eyeballing whether a product is worth "
            "proposing. Call this before create_product_proposal."
        ),
        args_schema=_ScoreOpportunityArgs,
        coroutine=_run,
    )


class _ProductionQtyArgs(BaseModel):
    estimated_monthly_demand_units: float = Field(description="Your estimate of units/month once launched — ground this in variant/category sales velocity or the trend's growth signal, not a guess.")
    moq: Optional[int] = Field(default=None, description="Supplier's minimum order quantity, if known.")
    launch_months_cover: int = Field(default=2, description="How many months of demand the initial production run should cover.")


def _make_production_quantity_tool() -> StructuredTool:
    async def _run(estimated_monthly_demand_units: float, moq: Optional[int] = None, launch_months_cover: int = 2) -> dict:
        return analytics.estimate_initial_production_quantity(estimated_monthly_demand_units, moq=moq, launch_months_cover=launch_months_cover)

    return StructuredTool.from_function(
        name="estimate_initial_production_quantity",
        description="Compute a recommended initial production quantity from an estimated monthly demand and the supplier's MOQ, instead of guessing a round number.",
        args_schema=_ProductionQtyArgs,
        coroutine=_run,
    )


class _VariantMixArgs(BaseModel):
    variant_sales: List[dict] = Field(description="Raw breakdown, e.g. [{'variant': 'Black', 'units': 450, 'revenue': 1800000}, ...].")


def _make_variant_mix_tool() -> StructuredTool:
    async def _run(variant_sales: List[dict]) -> list[dict]:
        return analytics.rank_variant_mix(variant_sales)

    return StructuredTool.from_function(
        name="analyze_variant_mix",
        description="Rank a custom set of variants by revenue/unit share with a keep/cut/expand call for each. Usually get_variant_performance already does this for you — use this only for a custom list.",
        args_schema=_VariantMixArgs,
        coroutine=_run,
    )


# ── generate_product_copy (creative LLM call) ─────────────────────────────

async def _brand_context_snippet(brand_id: str, query: str) -> str:
    chunks = await rag.retrieve_policies(brand_id, query)
    if not chunks:
        return "(no brand strategy/design guidelines on file — default to a clean, confident, on-brand tone.)"
    return "\n---\n".join(chunks)


class _ProductCopyOutput(BaseModel):
    description: str = Field(description="Product description, ready to publish.")
    seo_title: str = Field(description="SEO-friendly page title, under 60 characters.")
    seo_description: str = Field(description="SEO meta description, under 160 characters.")
    tags: List[str] = Field(default_factory=list, description="5-10 Shopify product tags.")


class _ProductCopyArgs(BaseModel):
    product_name: str = Field(description="Proposed product name.")
    category: str = Field(default="", description="e.g. 'hoodies', 'cargo pants'.")
    key_features: str = Field(default="", description="Fabric, fit, notable details.")
    target_audience: str = Field(default="", description="Who this is for.")


def _make_product_copy_tool(brand_id: str) -> StructuredTool:
    async def _run(product_name: str, category: str = "", key_features: str = "", target_audience: str = "") -> dict:
        voice = await _brand_context_snippet(brand_id, f"brand strategy and design guidelines for {category or 'this product'}")
        model = ChatAnthropic(model=PRODUCT_ANALYSIS_MODEL, temperature=0.6).with_structured_output(_ProductCopyOutput)
        result: _ProductCopyOutput = await model.ainvoke(
            f"Brand strategy / design guidelines:\n{voice}\n\n"
            f"Write product listing copy for: {product_name}\n"
            f"Category: {category or '(unspecified)'}\n"
            f"Key features: {key_features or '(none specified)'}\n"
            f"Target audience: {target_audience or '(general)'}\n\n"
            "Write a description ready to publish, an SEO title, an SEO meta description, and 5-10 tags."
        )
        return result.model_dump()

    return StructuredTool.from_function(
        name="generate_product_copy",
        description=(
            "Write on-brand product listing copy — description, SEO title/description, and tags — for a "
            "proposed product. Pulls brand strategy/design guidelines in automatically. NOTE: there is no "
            "product image generation wired into this environment — real imagery still needs a real "
            "sample/photo before publishing live."
        ),
        args_schema=_ProductCopyArgs,
        coroutine=_run,
    )


# ── create_product_proposal (operational write) ────────────────────────────

class _CreateProposalArgs(BaseModel):
    product_name: str
    category: str = ""
    description: str = ""
    variants: List[str] = Field(default_factory=list, description="Proposed color/style variants.")
    sizes: List[str] = Field(default_factory=list, description="Proposed sizes.")
    target_price: Optional[float] = None
    market_demand: float = Field(description="From score_product_opportunity.")
    brand_fit: float = Field(description="From score_product_opportunity.")
    competition: float = Field(description="From score_product_opportunity.")
    supplier_feasibility: float = Field(description="From score_product_opportunity.")
    expected_margin: Optional[float] = Field(default=None, description="From score_product_opportunity.")
    composite_score: float = Field(description="From score_product_opportunity.")
    recommended_initial_quantity: Optional[int] = Field(default=None, description="From estimate_initial_production_quantity.")
    reason: str = Field(description="Why this is (or isn't) a good opportunity — cite the actual evidence.")
    source_opportunity_id: Optional[str] = Field(default=None, description="Research's opportunity_id, if this came from get_research_opportunities.")
    status: str = Field(default="proposed", description="'proposed' (default) or 'approved' if your analysis clearly supports launching now.")


def _make_create_proposal_tool(brand_id: str) -> StructuredTool:
    async def _run(
        product_name: str, market_demand: float, brand_fit: float, competition: float,
        supplier_feasibility: float, composite_score: float, reason: str,
        category: str = "", description: str = "", variants: Optional[List[str]] = None,
        sizes: Optional[List[str]] = None, target_price: Optional[float] = None,
        expected_margin: Optional[float] = None, recommended_initial_quantity: Optional[int] = None,
        source_opportunity_id: Optional[str] = None, status: str = "proposed",
    ) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.create_product_proposal(
                session, brand_id, product_name, category, description,
                variants or [], sizes or [], target_price, market_demand, brand_fit, competition,
                supplier_feasibility, expected_margin, composite_score, recommended_initial_quantity,
                reason, source_opportunity_id=source_opportunity_id, status=status,
            )
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="create_product_proposal",
        description=(
            "Formally propose a new product — visible immediately on the dashboard. Always call "
            "search_our_catalog and score_product_opportunity first; don't propose something we already "
            "sell or that scores poorly without saying so in `reason`."
        ),
        args_schema=_CreateProposalArgs,
        coroutine=_run,
    )


# ── update_proposal_status (operational write) ─────────────────────────────

class _UpdateProposalArgs(BaseModel):
    proposal_id: str = Field(description="proposal_id from create_product_proposal.")
    status: str = Field(description="'proposed' | 'approved' | 'rejected' | 'in_development' | 'launched'.")
    shopify_product_id: Optional[int] = Field(default=None, description="Set this once create_product (shopify-mcp) actually created the Shopify product — pass its product_id back here.")
    note: str = Field(default="", description="Why the status changed.")


def _make_update_proposal_status_tool(brand_id: str) -> StructuredTool:
    async def _run(proposal_id: str, status: str, shopify_product_id: Optional[int] = None, note: str = "") -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.update_proposal_status(session, brand_id, proposal_id, status, shopify_product_id=shopify_product_id, note=note)
            if "error" not in result:
                await session.commit()
        return result

    return StructuredTool.from_function(
        name="update_proposal_status",
        description="Move a product proposal through its status (approved/rejected/in_development/launched). Call this right after create_product (shopify-mcp) succeeds, passing back its product_id.",
        args_schema=_UpdateProposalArgs,
        coroutine=_run,
    )


# ── update_product_lifecycle_stage (operational write) ────────────────────

class _LifecycleArgs(BaseModel):
    product_ref: str = Field(description="Product title or SKU — this agent's own tracking key for the product.")
    stage: str = Field(description="'idea'|'proposal'|'approved'|'development'|'sampling'|'production'|'ready'|'launch'|'growth'|'mature'|'declining'|'clearance'|'archived'.")
    performance_score: Optional[float] = Field(default=None, description="0-1, your read on how well it's performing at this stage, if applicable.")
    notes: str = Field(default="", description="What you observed and why the stage changed.")


def _make_lifecycle_update_tool(brand_id: str) -> StructuredTool:
    async def _run(product_ref: str, stage: str, performance_score: Optional[float] = None, notes: str = "") -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.upsert_product_lifecycle(session, brand_id, product_ref, stage, performance_score=performance_score, notes=notes)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="update_product_lifecycle_stage",
        description="Record where a product sits in its lifecycle (idea through archived) — one row per product, upserted. Use this to track a product's journey and flag when growth/mature products start declining.",
        args_schema=_LifecycleArgs,
        coroutine=_run,
    )


# ── create_collection / add_product_to_collection (operational writes) ────

class _CreateCollectionArgs(BaseModel):
    name: str
    season: str = ""
    theme: str = ""
    product_names: List[str] = Field(default_factory=list, description="Products to include — existing catalog titles and/or proposed product_names.")
    launch_date: Optional[str] = Field(default=None, description="ISO date, e.g. '2026-11-01'.")
    status: str = Field(default="planning", description="'planning' | 'active' | 'archived'.")


def _make_create_collection_tool(brand_id: str) -> StructuredTool:
    async def _run(name: str, season: str = "", theme: str = "", product_names: Optional[List[str]] = None, launch_date: Optional[str] = None, status: str = "planning") -> dict:
        from datetime import date as _date
        parsed = None
        if launch_date:
            try:
                parsed = _date.fromisoformat(launch_date)
            except ValueError:
                return {"error": f"Couldn't parse launch_date='{launch_date}' as ISO date."}
        async with AsyncSessionLocal() as session:
            result = await crud.create_collection(session, brand_id, name, season, theme, product_names or [], launch_date=parsed, status=status)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="create_collection",
        description="Plan a themed collection (e.g. a seasonal drop) grouping hero + supporting products — visible immediately on the dashboard.",
        args_schema=_CreateCollectionArgs,
        coroutine=_run,
    )


class _AddToCollectionArgs(BaseModel):
    collection_id: str
    product_name: str


def _make_add_to_collection_tool(brand_id: str) -> StructuredTool:
    async def _run(collection_id: str, product_name: str) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.add_product_to_collection(session, brand_id, collection_id, product_name)
            if "error" not in result:
                await session.commit()
        return result

    return StructuredTool.from_function(
        name="add_product_to_collection",
        description="Add one more product to an existing collection.",
        args_schema=_AddToCollectionArgs,
        coroutine=_run,
    )


# ── retrieve_policy / search_agent_memory (RAG) ────────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'brand positioning and target customer' or 'past collection performance'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description=(
            "Search brand-specific strategy/design documents (brand strategy, design guidelines, target "
            "customer, past collection specs, pricing philosophy) for guidance relevant to your query — "
            "always check this before judging brand_fit or proposing pricing."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )


def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description="Search notes this agent kept from previous runs (e.g. 'customers prefer neutral colors', 'limited drops generate higher urgency') for anything relevant now.",
        args_schema=_QueryArgs,
        coroutine=_run,
    )