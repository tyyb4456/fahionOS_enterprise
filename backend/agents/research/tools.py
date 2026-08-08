"""
Internal tools for the Research Agent's ReAct loop — everything that isn't
a live external-web call (those come from research-mcp, see mcp_client.py)
or a live Shopify catalog check (a read-only subset of shopify-mcp, also
via mcp_client.py). Each factory below binds `brand_id` in a closure so the
LLM never has to supply it — same reasoning as agents/common/tool_scoping.py.

Four flavors of tool live here:
  - internal lookups (read our own + other agents' tables — sales insights,
    inventory signals, active campaigns, our own catalog)
  - deterministic helpers (agents/research/analytics.py::score_product_opportunity
    — turn raw signals into a market_score instead of the LLM eyeballing one)
  - LLM-backed analysis (analyze_customer_sentiment, brainstorm_keyword_opportunities
    — dedicated calls, same separation-of-concerns reasoning as Marketing's
    generate_social_caption: keep the main reasoning model's tool-orchestration
    loop deterministic-ish, push generative/extractive work into its own call)
  - operational writes (create_product_opportunity, record_competitor_analysis,
    record_pricing_insight, notify_brand_owner) — conditional, mid-loop, real
    rows, same role as Finance's record_expense/create_budget_recommendation/
    assess_financial_risk. Trends + insights are NOT here — those are the
    routine per-run output written by persist_node from the structured
    decision, same as Inventory's forecasts/alerts.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.common.notify_tools import make_notify_brand_owner_tool
from db import crud_research as crud
from db.session import AsyncSessionLocal

from . import analytics
from . import memory as rag

logger = logging.getLogger(__name__)

RESEARCH_ANALYSIS_MODEL = os.getenv("RESEARCH_ANALYSIS_MODEL", "claude-sonnet-5")


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_sales_insights_tool(brand_id),
        _make_inventory_signals_tool(brand_id),
        _make_active_campaigns_tool(brand_id),
        _make_catalog_search_tool(brand_id),
        _make_score_opportunity_tool(),
        _make_sentiment_tool(),
        _make_keyword_tool(),
        _make_product_opportunity_tool(brand_id),
        _make_competitor_analysis_tool(brand_id),
        _make_pricing_insight_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
        make_notify_brand_owner_tool(brand_id, agent_name="Research Agent"),
    ]


# ── internal lookups ──────────────────────────────────────────────────────

class _NoArgs(BaseModel):
    pass


def _make_sales_insights_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_sales_insights(session, brand_id)

    return StructuredTool.from_function(
        name="get_sales_insights",
        description="Read the Sales Agent's recent insights (best/worst sellers, anomalies, opportunities) — grounds external trends against what's actually happening internally.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_inventory_signals_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_inventory_signals(session, brand_id)

    return StructuredTool.from_function(
        name="get_inventory_signals",
        description="Read the Inventory Agent's open stockout/overstock/velocity alerts — overstock signals dead-stock risk worth a discontinue recommendation; stockout signals a category worth doubling down on.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_active_campaigns_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_active_campaigns(session, brand_id)

    return StructuredTool.from_function(
        name="get_active_campaigns",
        description="This brand's currently live/scheduled marketing campaigns — check before recommending something that's already being pursued.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


class _CatalogSearchArgs(BaseModel):
    query: str = Field(description="Product name, category, or tag to search our own catalog for, e.g. 'oversized hoodie'.")


def _make_catalog_search_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.search_catalog(session, brand_id, query)

    return StructuredTool.from_function(
        name="search_our_catalog",
        description=(
            "Check whether we already sell something like this before calling it a 'product "
            "opportunity' — matches against our own product titles/categories/tags. Always call "
            "this before create_product_opportunity."
        ),
        args_schema=_CatalogSearchArgs,
        coroutine=_run,
    )


# ── score_product_opportunity (deterministic helper) ─────────────────────

class _ScoreOpportunityArgs(BaseModel):
    growth_pct: Optional[float] = Field(default=None, description="External demand growth % signal if you have one (e.g. from google_trends_search interest-over-time, or a competitor's reported growth). Omit if unknown.")
    competitor_count: int = Field(default=0, description="How many researched competitors are already selling this.")
    we_already_sell: bool = Field(default=False, description="Set True if search_our_catalog found a matching product.")


def _make_score_opportunity_tool() -> StructuredTool:
    async def _run(growth_pct: Optional[float] = None, competitor_count: int = 0, we_already_sell: bool = False) -> dict:
        return analytics.score_product_opportunity(growth_pct, competitor_count, we_already_sell)

    return StructuredTool.from_function(
        name="score_product_opportunity",
        description="Turn growth/competition signals into a market_score, competition level, and priority instead of eyeballing them yourself. Run this before create_product_opportunity.",
        args_schema=_ScoreOpportunityArgs,
        coroutine=_run,
    )


# ── LLM-backed analysis ────────────────────────────────────────────────────

def _analysis_model(temperature: float = 0.2) -> ChatAnthropic:
    return ChatAnthropic(model=RESEARCH_ANALYSIS_MODEL, temperature=temperature)


class _SentimentOutput(BaseModel):
    overall_sentiment: str = Field(description="'positive' | 'mixed' | 'negative'.")
    top_complaints: List[str] = Field(default_factory=list)
    top_praises: List[str] = Field(default_factory=list)
    desired_features: List[str] = Field(default_factory=list)


class _SentimentArgs(BaseModel):
    texts: List[str] = Field(description="Raw review/feedback snippets to analyze — from web_search results, fetch_page_content, or internal return/refund reasons.")
    topic: str = Field(default="", description="Optional — what product/category these relate to.")


def _make_sentiment_tool() -> StructuredTool:
    async def _run(texts: List[str], topic: str = "") -> dict:
        if not texts:
            return {"error": "No text provided to analyze."}
        model = _analysis_model().with_structured_output(_SentimentOutput)
        joined = "\n---\n".join(texts[:30])
        result: _SentimentOutput = await model.ainvoke(
            f"Analyze this customer feedback{f' about {topic}' if topic else ''}. Extract overall "
            f"sentiment, the top recurring complaints, the top recurring praises, and any features "
            f"customers explicitly say they want.\n\n{joined}"
        )
        return result.model_dump()

    return StructuredTool.from_function(
        name="analyze_customer_sentiment",
        description="Extract sentiment, complaints, praises, and desired features from a batch of raw review/feedback text (from web_search, fetch_page_content, or internal return reasons).",
        args_schema=_SentimentArgs,
        coroutine=_run,
    )


class _KeywordOutput(BaseModel):
    keywords: List[str] = Field(default_factory=list)
    rationale: str = ""


class _KeywordArgs(BaseModel):
    topic: str = Field(description="The product/trend/category to brainstorm keyword opportunities for.")
    seed_terms: List[str] = Field(default_factory=list, description="Optional terms already known to be relevant, e.g. from google_trends_search rising_related_queries.")


def _make_keyword_tool() -> StructuredTool:
    async def _run(topic: str, seed_terms: Optional[List[str]] = None) -> dict:
        model = _analysis_model(temperature=0.4).with_structured_output(_KeywordOutput)
        result: _KeywordOutput = await model.ainvoke(
            f"Brainstorm 8-12 realistic, specific search/marketing keyword opportunities for: {topic}\n"
            f"Known related terms: {', '.join(seed_terms or []) or '(none)'}\n"
            "Favor specific, purchase-intent phrases over generic ones."
        )
        return result.model_dump()

    return StructuredTool.from_function(
        name="brainstorm_keyword_opportunities",
        description=(
            "Ideate specific marketing/SEO keyword phrases for a topic. This is ideation, not "
            "verified search-volume data — pair with google_trends_search for real numbers where "
            "it matters, and say so in your summary."
        ),
        args_schema=_KeywordArgs,
        coroutine=_run,
    )


# ── operational writes (conditional, mid-loop, real rows) ─────────────────

class _ProductOpportunityArgs(BaseModel):
    product: str = Field(description="The product/category being proposed, e.g. 'Oversized cargo hoodie'.")
    market_score: float = Field(description="From score_product_opportunity — don't guess this.")
    competition: str = Field(description="'low' | 'medium' | 'high' — from score_product_opportunity.")
    priority: str = Field(description="'low' | 'medium' | 'high' — from score_product_opportunity.")
    reason: str = Field(description="Why this is a real opportunity — cite the specific evidence (trend %, competitor names, search data).")


def _make_product_opportunity_tool(brand_id: str) -> StructuredTool:
    async def _run(product: str, market_score: float, competition: str, priority: str, reason: str) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.create_product_opportunity(session, brand_id, product, market_score, competition, priority, reason)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="create_product_opportunity",
        description=(
            "Formally propose a product/category the brand doesn't currently sell — visible "
            "immediately on the dashboard for the founder/product team to review. Only call this "
            "after search_our_catalog confirms we don't already sell it and score_product_opportunity "
            "backs the score — not for every passing idea."
        ),
        args_schema=_ProductOpportunityArgs,
        coroutine=_run,
    )


class _CompetitorAnalysisArgs(BaseModel):
    competitor: str = Field(description="Competitor/brand name.")
    products: List[str] = Field(default_factory=list, description="Notable products/collections they're running.")
    pricing_summary: str = Field(default="", description="e.g. 'Average hoodie price Rs. 3,250, 10% below us.'")
    promotions: str = Field(default="", description="Any active sales/discounts/launches.")
    summary: str = Field(description="Your overall read on what this competitor is doing and why it matters.")


def _make_competitor_analysis_tool(brand_id: str) -> StructuredTool:
    async def _run(competitor: str, summary: str, products: Optional[List[str]] = None, pricing_summary: str = "", promotions: str = "") -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.record_competitor_analysis(session, brand_id, competitor, products or [], pricing_summary, promotions, summary)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="record_competitor_analysis",
        description="Formally record a competitor finding worth tracking — visible on the dashboard. Base this on actual web_search/fetch_page_content results, never invent a competitor's numbers.",
        args_schema=_CompetitorAnalysisArgs,
        coroutine=_run,
    )


class _PricingInsightArgs(BaseModel):
    product: str = Field(description="Our product/category this pricing insight concerns.")
    competitor_price: Optional[float] = Field(default=None, description="Competitor's price, if found via check_competitor_price/fetch_page_content.")
    competitor_name: str = Field(default="", description="Which competitor.")
    recommended_price: Optional[float] = Field(default=None, description="Your recommended price, if you have a clear reason to suggest one.")
    reason: str = Field(description="Why — cite the actual competitor data.")
    our_price: Optional[float] = Field(default=None, description="Our current price, if known (from get_product_by_sku/list_products).")


def _make_pricing_insight_tool(brand_id: str) -> StructuredTool:
    async def _run(product: str, reason: str, competitor_price: Optional[float] = None, competitor_name: str = "",
                    recommended_price: Optional[float] = None, our_price: Optional[float] = None) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.record_pricing_insight(session, brand_id, product, competitor_price, competitor_name, recommended_price, reason, our_price)
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="record_pricing_insight",
        description=(
            "Formally record a pricing finding (a competitor's price, and optionally a recommended "
            "price for us) — visible on the dashboard for Finance/Sales to act on. This never changes "
            "our actual Shopify price itself; that stays with Sales/Pricing."
        ),
        args_schema=_PricingInsightArgs,
        coroutine=_run,
    )


# ── retrieve_policy / search_agent_memory (RAG) ────────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'our brand positioning and target audience'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description=(
            "Search brand-specific strategy documents (brand strategy, target audience, business "
            "goals, market position) so recommendations actually fit the brand — e.g. don't propose "
            "a mass-market product for a premium-positioned brand."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )


def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description="Search notes this agent kept from previous runs (e.g. lead times between a platform trend and a real sales lift) for anything relevant now.",
        args_schema=_QueryArgs,
        coroutine=_run,
    )