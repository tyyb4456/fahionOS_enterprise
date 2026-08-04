"""
Marketing Agent — scheduled runs + the operational publish loop.

Three jobs live here:
  - run_marketing_agent_for_all_brands — daily planning run (like
    Inventory/Sales), fans out one task per active brand.
  - publish_due_content_for_all_brands — frequent (every ~15 min) sweep of
    ScheduledContent rows whose scheduled_for has arrived; this is what
    actually turns a schedule_content() tool call into a live Instagram
    post. Runs independently of the agent's own reasoning loop — no LLM
    call needed to publish something that was already decided and queued.
  - sync_content_performance_for_all_brands — pulls Instagram insights for
    recently-published posts so find_best_posting_time / content_performance
    have real data to learn from on the next run.
"""
import asyncio

from sqlalchemy import select

from db.models import Brand
from db.session import AsyncSessionLocal
from pipeline import run_marketing_agent_sync
from tasks.celery_app import celery_app


@celery_app.task(name="tasks.marketing_tasks.run_marketing_agent_for_brand")
def run_marketing_agent_for_brand(brand_id: str, task_type: str = "daily_content") -> dict:
    task = {"task_type": task_type, "priority": "normal", "trigger": "daily_scheduler"}
    return run_marketing_agent_sync(brand_id, task)


@celery_app.task(name="tasks.marketing_tasks.run_marketing_agent_for_all_brands")
def run_marketing_agent_for_all_brands() -> int:
    async def _active_brand_ids() -> list[str]:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(Brand.brand_id).where(Brand.is_active == True)  # noqa: E712
            )).scalars().all()
            return list(rows)

    brand_ids = asyncio.run(_active_brand_ids())
    for brand_id in brand_ids:
        run_marketing_agent_for_brand.delay(brand_id)
    return len(brand_ids)


@celery_app.task(name="tasks.marketing_tasks.publish_due_content_for_all_brands")
def publish_due_content_for_all_brands() -> int:
    """Beat job — publishes any ScheduledContent row whose scheduled_for
    has arrived. Deliberately outside the agent's own graph: this is
    mechanical execution of an already-made decision, not new reasoning."""
    from agents.marketing.scheduler import publish_due_content
    return asyncio.run(publish_due_content())


@celery_app.task(name="tasks.marketing_tasks.sync_content_performance_for_all_brands")
def sync_content_performance_for_all_brands() -> int:
    """Beat job — pulls Instagram insights for recently-published posts so
    future runs have real engagement data instead of the cold-start
    defaults in agents/marketing/analytics.py."""
    from agents.marketing.scheduler import sync_content_performance
    return asyncio.run(sync_content_performance())