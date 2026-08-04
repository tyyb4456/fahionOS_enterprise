"""
Internal tools for the Marketing Agent's ReAct loop — everything that
isn't a live Shopify/Meta call (those come from shopify-mcp / meta-mcp,
see mcp_client.py). Each factory below binds `brand_id` in a closure so
the LLM never has to supply it — same reasoning as tool_scoping.py.

Four flavors of tool live here:
  - lookups (read our own + other agents' tables)
  - deterministic helpers (agents/marketing/analytics.py — audience
    scoring, posting time, hashtags: things that should be computed, not
    guessed)
  - creative generation (a dedicated, higher-temperature LLM call per
    content type, with brand-voice guidelines pulled in automatically) —
    kept separate from the main reasoning model (which stays temperature=0
    for reliable tool orchestration, see graph.py) so creative quality and
    planning reliability don't trade off against each other
  - operational writes (schedule_content, notify_brand_owner) — these
    change real state immediately, mid-loop, the same way Shopify's
    set_inventory_level does, rather than waiting for persist_node
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from db import crud_marketing as crud
from db.session import AsyncSessionLocal

from agents.common.notify_tools import make_notify_brand_owner_tool

from . import analytics
from . import memory as rag

MARKETING_CONTENT_MODEL = os.getenv("MARKETING_CONTENT_MODEL", "claude-sonnet-5")


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_check_stock_tool(brand_id),
        _make_sales_insights_tool(brand_id),
        _make_inventory_alerts_tool(brand_id),
        _make_customer_segments_tool(brand_id),
        _make_recent_campaigns_tool(brand_id),
        _make_select_audience_tool(brand_id),
        _make_posting_time_tool(brand_id),
        _make_hashtag_tool(),
        _make_caption_tool(brand_id),
        _make_email_tool(brand_id),
        _make_sms_tool(brand_id),
        _make_schedule_content_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
        make_notify_brand_owner_tool(brand_id, agent_name="Marketing Agent"),
    ]


# ── check_product_stock ───────────────────────────────────────────────────

class _SkuArgs(BaseModel):
    sku: str = Field(description="SKU to check before featuring it in a campaign or post.")


def _make_check_stock_tool(brand_id: str) -> StructuredTool:
    async def _run(sku: str) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.check_product_stock(session, brand_id, sku)
        return result or {"error": f"SKU '{sku}' not found in synced product data."}

    return StructuredTool.from_function(
        name="check_product_stock",
        description=(
            "The authoritative safe-to-promote check for one SKU — current stock plus any "
            "open Inventory Agent alert. Always call this before featuring a specific product "
            "in a campaign, post, or ad. Never promote something this flags as unsafe."
        ),
        args_schema=_SkuArgs,
        coroutine=_run,
    )


# ── get_sales_insights / get_inventory_alerts / get_customer_segments /
#    get_recent_campaigns ────────────────────────────────────────────────

class _NoArgs(BaseModel):
    pass


def _make_sales_insights_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_recent_sales_insights(session, brand_id)

    return StructuredTool.from_function(
        name="get_sales_insights",
        description="Read the Sales Agent's recent insights (best/worst sellers, anomalies, opportunities) — don't recompute this yourself.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_inventory_alerts_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_inventory_alerts(session, brand_id)

    return StructuredTool.from_function(
        name="get_inventory_alerts",
        description="Read the Inventory Agent's open alerts (stockout risk, overstock, etc.) — check this before deciding what to promote.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_customer_segments_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_customer_segments(session, brand_id)

    return StructuredTool.from_function(
        name="get_customer_segments",
        description="Read the Sales Agent's customer segments (VIP/Loyal/New/At Risk/Inactive) for targeting.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


def _make_recent_campaigns_tool(brand_id: str) -> StructuredTool:
    async def _run() -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.list_recent_campaigns(session, brand_id)

    return StructuredTool.from_function(
        name="get_recent_campaigns",
        description="This brand's own recent campaigns — check before proposing something redundant with what's already running.",
        args_schema=_NoArgs,
        coroutine=_run,
    )


# ── select_target_audience ────────────────────────────────────────────────

class _AudienceArgs(BaseModel):
    goal: str = Field(description="The campaign goal, e.g. 'increase hoodie sales' or 'win back lapsed customers'.")


def _make_select_audience_tool(brand_id: str) -> StructuredTool:
    async def _run(goal: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            segments = await crud.get_customer_segments(session, brand_id)
        return analytics.score_audiences(goal, segments)

    return StructuredTool.from_function(
        name="select_target_audience",
        description=(
            "Rank this brand's actual customer segments against a campaign goal instead of "
            "guessing who to target. Falls back to a general-audience recommendation if no "
            "segments exist yet."
        ),
        args_schema=_AudienceArgs,
        coroutine=_run,
    )


# ── find_best_posting_time ───────────────────────────────────────────────

class _PlatformArgs(BaseModel):
    platform: str = Field(description="'instagram' | 'facebook' | 'tiktok' | 'email' | 'sms'.")


def _make_posting_time_tool(brand_id: str) -> StructuredTool:
    async def _run(platform: str) -> dict:
        async with AsyncSessionLocal() as session:
            history = await crud.get_content_performance_history(session, brand_id, platform=platform)
        return analytics.best_posting_time(platform, history)

    return StructuredTool.from_function(
        name="find_best_posting_time",
        description="Best day/time to post on a platform, based on this brand's own engagement history (with a sane default if there's no history yet).",
        args_schema=_PlatformArgs,
        coroutine=_run,
    )


# ── generate_hashtags ─────────────────────────────────────────────────────

class _HashtagArgs(BaseModel):
    topic: str = Field(description="What the post is about, e.g. 'winter hoodie collection'.")
    platform: str = Field(default="instagram", description="'instagram' | 'tiktok' | 'facebook'.")
    product_tags: List[str] = Field(default_factory=list, description="Optional Shopify product tags to fold in.")
    count: int = Field(default=8, description="How many hashtags to return.")


def _make_hashtag_tool() -> StructuredTool:
    async def _run(topic: str, platform: str = "instagram", product_tags: Optional[List[str]] = None, count: int = 8) -> list[str]:
        return analytics.suggest_hashtags(topic, platform, product_tags, count)

    return StructuredTool.from_function(
        name="generate_hashtags",
        description="Deterministic hashtag suggestions from a topic + optional product tags, rounded out with platform-appropriate evergreen tags.",
        args_schema=_HashtagArgs,
        coroutine=_run,
    )


# ── creative generation — shared brand-voice fetch + a dedicated,
# higher-temperature model call per content type ──────────────────────────

async def _brand_voice_snippet(brand_id: str, query: str) -> str:
    chunks = await rag.retrieve_policies(brand_id, query)
    if not chunks:
        return "(no brand guidelines on file — default to a clean, confident, non-pushy tone.)"
    return "\n---\n".join(chunks)


def _content_model(temperature: float = 0.7) -> ChatAnthropic:
    return ChatAnthropic(model=MARKETING_CONTENT_MODEL, temperature=temperature)


class _CaptionOutput(BaseModel):
    caption: str = Field(description="The post caption, ready to publish.")
    hashtags: List[str] = Field(default_factory=list, description="3-10 relevant hashtags.")


class _CaptionArgs(BaseModel):
    platform: str = Field(description="'instagram' | 'facebook' | 'tiktok' | 'threads'.")
    topic: str = Field(description="What the post is about — a product, a campaign theme, an event.")
    tone: str = Field(default="on-brand", description="Optional tone override, e.g. 'playful', 'luxury', 'urgent'.")
    campaign_goal: str = Field(default="", description="Optional — what this post is meant to achieve.")


def _make_caption_tool(brand_id: str) -> StructuredTool:
    async def _run(platform: str, topic: str, tone: str = "on-brand", campaign_goal: str = "") -> dict:
        voice = await _brand_voice_snippet(brand_id, f"brand voice and tone for {platform} content")
        model = _content_model().with_structured_output(_CaptionOutput)
        result: _CaptionOutput = await model.ainvoke(
            f"Brand voice guidelines:\n{voice}\n\n"
            f"Write a {platform} caption about: {topic}\n"
            f"Tone: {tone}\n"
            f"Campaign goal: {campaign_goal or '(none specified)'}\n\n"
            "Keep it native to the platform (concise for Instagram/Threads, punchier for "
            "TikTok). Don't be discount-first unless the goal is explicitly a sale. Return "
            "3-8 relevant hashtags separately."
        )
        return result.model_dump()

    return StructuredTool.from_function(
        name="generate_social_caption",
        description="Write an on-brand social caption + hashtags for a platform/topic. Pulls brand voice guidelines in automatically.",
        args_schema=_CaptionArgs,
        coroutine=_run,
    )


class _EmailOutput(BaseModel):
    subject: str
    preview_text: str
    body: str
    cta: str


class _EmailArgs(BaseModel):
    goal: str = Field(description="What this email should achieve, e.g. 'promote the winter hoodie collection to VIP customers'.")
    topic: str = Field(description="What the email is about.")
    audience: str = Field(default="all subscribers", description="Who this is for.")


def _make_email_tool(brand_id: str) -> StructuredTool:
    async def _run(goal: str, topic: str, audience: str = "all subscribers") -> dict:
        voice = await _brand_voice_snippet(brand_id, "brand voice and tone for email campaigns")
        model = _content_model().with_structured_output(_EmailOutput)
        result: _EmailOutput = await model.ainvoke(
            f"Brand voice guidelines:\n{voice}\n\n"
            f"Write a marketing email.\nGoal: {goal}\nAudience: {audience}\nTopic: {topic}\n\n"
            "Include a short, specific subject line, a preview_text (~50 chars), a body "
            "(3-5 short paragraphs, scannable), and one clear CTA."
        )
        return result.model_dump()

    return StructuredTool.from_function(
        name="generate_email_campaign",
        description="Write an on-brand marketing email (subject/preview/body/CTA). Pulls brand voice guidelines in automatically.",
        args_schema=_EmailArgs,
        coroutine=_run,
    )


class _SmsOutput(BaseModel):
    text: str


class _SmsArgs(BaseModel):
    offer: str = Field(description="The offer or message, e.g. '20% off hoodies today only'.")
    audience: str = Field(default="all subscribers", description="Who this is for.")


def _make_sms_tool(brand_id: str) -> StructuredTool:
    async def _run(offer: str, audience: str = "all subscribers") -> dict:
        voice = await _brand_voice_snippet(brand_id, "brand voice for SMS / flash-sale messaging")
        model = _content_model().with_structured_output(_SmsOutput)
        result: _SmsOutput = await model.ainvoke(
            f"Brand voice guidelines:\n{voice}\n\n"
            f"Write a marketing SMS. Offer: {offer}\nAudience: {audience}\n\n"
            "Hard limit: under 160 characters, one clear CTA, no more than one emoji."
        )
        return {"text": result.text[:160]}

    return StructuredTool.from_function(
        name="generate_sms_campaign",
        description="Write a short, on-brand marketing SMS (hard-capped at 160 characters).",
        args_schema=_SmsArgs,
        coroutine=_run,
    )


# ── schedule_content (operational write) ─────────────────────────────────

class _ScheduleArgs(BaseModel):
    platform: str = Field(description="'instagram' | 'facebook' | 'tiktok' | 'email' | 'sms' | 'blog'.")
    content_type: str = Field(description="'post' | 'story' | 'reel' | 'email' | 'sms' | 'blog'.")
    scheduled_for: str = Field(description="ISO8601 datetime to publish at, e.g. '2026-08-10T15:00:00Z'.")
    caption: str = Field(default="", description="For social posts.")
    hashtags: List[str] = Field(default_factory=list)
    image_url: str = Field(default="", description="Required for Instagram/Facebook image posts.")
    subject: str = Field(default="", description="For email.")
    body: str = Field(default="", description="For email/blog.")
    cta: str = Field(default="", description="For email.")
    sms_text: str = Field(default="", description="For SMS.")
    campaign_id: Optional[str] = Field(default=None, description="Optional linked campaign id.")


def _make_schedule_content_tool(brand_id: str) -> StructuredTool:
    async def _run(
        platform: str, content_type: str, scheduled_for: str,
        caption: str = "", hashtags: Optional[List[str]] = None, image_url: str = "",
        subject: str = "", body: str = "", cta: str = "", sms_text: str = "",
        campaign_id: Optional[str] = None,
    ) -> dict:
        try:
            when = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
        except ValueError:
            return {"error": f"Couldn't parse scheduled_for='{scheduled_for}' as ISO8601."}
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

        content = {
            "caption": caption, "hashtags": hashtags or [], "image_url": image_url,
            "subject": subject, "body": body, "cta": cta, "sms_text": sms_text,
        }

        async with AsyncSessionLocal() as session:
            result = await crud.create_scheduled_content(
                session, brand_id, platform, content_type, content, when, campaign_id=campaign_id,
            )
            await session.commit()
        return result

    return StructuredTool.from_function(
        name="schedule_content",
        description=(
            "Queue a piece of content to publish later. For Instagram this gets "
            "auto-published at the scheduled time by a background job (needs image_url). "
            "For email/SMS this stages the content — actual sending needs an ESP/SMS "
            "gateway that isn't connected yet, so treat it as 'prepared', not 'sent'."
        ),
        args_schema=_ScheduleArgs,
        coroutine=_run,
    )


# ── retrieve_policy / search_agent_memory (RAG) ───────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'tone rules for discount campaigns'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description="Search brand-specific marketing documents (brand voice, content rules, campaign strategy) for guidance relevant to your query.",
        args_schema=_QueryArgs,
        coroutine=_run,
    )


def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description="Search notes this agent kept from previous runs (e.g. what content format performed best last time) for anything relevant now.",
        args_schema=_QueryArgs,
        coroutine=_run,
    )
