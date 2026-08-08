"""
Research Agent — scheduled runs.

Two beat jobs (see tasks/celery_app.py):
  - run_research_agent_for_all_brands — daily trend_monitoring pass, fans
    out one task per active brand, same pattern as inventory/sales/
    marketing/finance's daily jobs. Scheduled BEFORE those four so their
    same-day runs can read fresh market_trends/research_insights.
  - run_research_pulse_for_all_brands — a lighter, more frequent
    competitor_analysis pass (every few hours), per the design note that
    Research should behave like an always-on analyst rather than only
    running once a day.

Event-driven triggering (Sales spots a sudden drop, Inventory reports
growing dead stock, Marketing wants campaign-ready trend ideas) is
supported via run_research_agent_for_brand.delay(brand_id, task_type=...)
— see agents/common/research_trigger.py for a ready-to-wire tool that lets
another agent request a scan directly from its own ReAct loop.
"""
import asyncio
import logging

from sqlalchemy import select

from db.models import Brand
from db.session import AsyncSessionLocal
from pipeline import run_research_agent_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.research_tasks.run_research_agent_for_brand")
def run_research_agent_for_brand(
    brand_id: str, task_type: str = "trend_monitoring", category: str | None = None, region: str | None = None,
) -> dict:
    logger.info("Celery task run_research_agent_for_brand started for brand_id=%s, task_type=%s", brand_id, task_type)
    task = {"task_type": task_type, "priority": "normal", "trigger": "daily_scheduler"}
    if category:
        task["category"] = category
    if region:
        task["region"] = region
    try:
        res = run_research_agent_sync(brand_id, task)
        logger.info("Celery task run_research_agent_for_brand completed for brand_id=%s", brand_id)
        return res
    except Exception:
        logger.exception("Celery task run_research_agent_for_brand failed for brand_id=%s", brand_id)
        raise


@celery_app.task(name="tasks.research_tasks.run_research_agent_for_all_brands")
def run_research_agent_for_all_brands(task_type: str = "trend_monitoring") -> int:
    logger.info("Celery task run_research_agent_for_all_brands triggered, task_type=%s", task_type)
    async def _active_brand_ids() -> list[str]:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(Brand.brand_id).where(Brand.is_active == True)  # noqa: E712
            )).scalars().all()
            return list(rows)

    brand_ids = asyncio.run(_active_brand_ids())
    logger.info("Fanning out research task for %d active brands", len(brand_ids))
    for brand_id in brand_ids:
        run_research_agent_for_brand.delay(brand_id, task_type=task_type)

    return len(brand_ids)


@celery_app.task(name="tasks.research_tasks.run_research_pulse_for_all_brands")
def run_research_pulse_for_all_brands() -> int:
    """Lighter, more frequent scan (competitor_analysis) — the 'always-on
    analyst' behavior called for in the Research Agent design doc, as
    opposed to only running once a day like the other four agents."""
    return run_research_agent_for_all_brands(task_type="competitor_analysis")