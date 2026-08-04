"""
Operational loop for scheduled content — deliberately separate from the
agent's own reasoning graph (see tasks/marketing_tasks.py). Publishing
something that was already decided and queued by schedule_content() is
mechanical execution, not a new decision, so it doesn't need another LLM
call: just find due rows and call the right MCP tool directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from db.models import ScheduledContent
from db.session import AsyncSessionLocal

from .mcp_client import get_marketing_tools

logger = logging.getLogger(__name__)

# facebook/tiktok/email/sms need further integration (page posting vs IG
# media API, an ESP, an SMS gateway) that isn't wired into this environment
# yet — see agents/marketing/prompts.py. Those rows get parked as
# "awaiting_integration" rather than silently dropped.
_PUBLISHABLE_PLATFORMS = {"instagram"}


async def _find_tool(name: str):
    tools = await get_marketing_tools()
    for t in tools:
        if t.name == name:
            return t
    return None


async def publish_due_content() -> int:
    """Publish every ScheduledContent row whose scheduled_for has arrived.
    Returns the number successfully published."""
    now = datetime.now(timezone.utc)
    published = 0

    async with AsyncSessionLocal() as session:
        stmt = select(ScheduledContent).where(
            ScheduledContent.status == "scheduled", ScheduledContent.scheduled_for <= now,
        )
        due = (await session.execute(stmt)).scalars().all()

        publish_tool = await _find_tool("publish_instagram_post") if due else None

        for row in due:
            if row.platform not in _PUBLISHABLE_PLATFORMS:
                row.status = "awaiting_integration"
                continue

            content = row.content or {}
            image_url = content.get("image_url")
            caption = content.get("caption", "")

            if not image_url:
                row.status = "failed"
                row.error = "No image_url on the scheduled content — can't publish to Instagram without one."
                continue

            if publish_tool is None:
                row.status = "failed"
                row.error = "publish_instagram_post tool unavailable (is meta-mcp running?)."
                continue

            try:
                result = await publish_tool.ainvoke({"brand_id": row.brand_id, "image_url": image_url, "caption": caption})
            except Exception as exc:  # noqa: BLE001 — best-effort background sweep, one bad row shouldn't kill the run
                logger.warning("Failed to publish scheduled_content=%s: %s", row.id, exc, exc_info=True)
                row.status = "failed"
                row.error = str(exc)
                continue

            if isinstance(result, dict) and result.get("success"):
                row.status = "published"
                row.published_ref_id = result.get("media_id")
                row.published_at = now
                published += 1
            else:
                row.status = "failed"
                row.error = str(result.get("error")) if isinstance(result, dict) else str(result)

        await session.commit()

    return published


async def sync_content_performance() -> int:
    """For recently-published Instagram content, pull engagement insights
    and store a ContentPerformance row so find_best_posting_time has real
    data to learn from. Returns the number of rows synced."""
    from db import crud_marketing as crud

    cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
    synced = 0

    async with AsyncSessionLocal() as session:
        stmt = select(ScheduledContent).where(
            ScheduledContent.status == "published",
            ScheduledContent.platform == "instagram",
            ScheduledContent.published_ref_id.is_not(None),
        )
        rows = (await session.execute(stmt)).scalars().all()
        if not rows:
            return 0

        insights_tool = await _find_tool("get_instagram_media_insights")
        if insights_tool is None:
            return 0

        for row in rows:
            if row.published_at and row.published_at.timestamp() < cutoff:
                continue  # only track the recent window — older posts stop being actionable

            try:
                insights = await insights_tool.ainvoke({"brand_id": row.brand_id, "media_id": row.published_ref_id})
            except Exception:
                logger.warning("Failed to fetch insights for scheduled_content=%s", row.id, exc_info=True)
                continue

            if not isinstance(insights, dict) or insights.get("error"):
                continue

            await crud.record_content_performance(
                session, row.brand_id, row.id, "instagram",
                engagement=int(insights.get("engagement", 0) or 0),
            )
            synced += 1

        await session.commit()

    return synced
