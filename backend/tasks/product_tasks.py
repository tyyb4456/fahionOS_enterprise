"""
Product Agent — scheduled runs.

`run_product_agent_for_all_brands` fans out one task per active brand,
scheduled after Research, Sales, Inventory, Marketing, and Finance (see
tasks/celery_app.py) so its daily merchandising review reads the freshest
opportunities/trends/margins/alerts from all five.
"""
import asyncio
import logging

from sqlalchemy import select

from db.models import Brand
from db.session import AsyncSessionLocal
from pipeline import run_product_agent_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.product_tasks.run_product_agent_for_brand")
def run_product_agent_for_brand(brand_id: str, task_type: str = "product_lifecycle_review") -> dict:
    logger.info("Celery task run_product_agent_for_brand started for brand_id=%s, task_type=%s", brand_id, task_type)
    task = {
        "task_type": task_type,
        "priority": "normal",
        "trigger": "daily_scheduler",
    }
    try:
        res = run_product_agent_sync(brand_id, task)
        logger.info("Celery task run_product_agent_for_brand completed for brand_id=%s", brand_id)
        return res
    except Exception:
        logger.exception("Celery task run_product_agent_for_brand failed for brand_id=%s", brand_id)
        raise


@celery_app.task(name="tasks.product_tasks.run_product_agent_for_all_brands")
def run_product_agent_for_all_brands() -> int:
    logger.info("Celery task run_product_agent_for_all_brands triggered")
    async def _active_brand_ids() -> list[str]:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(Brand.brand_id).where(Brand.is_active == True)  # noqa: E712
            )).scalars().all()
            return list(rows)

    brand_ids = asyncio.run(_active_brand_ids())
    logger.info("Fanning out product task for %d active brands", len(brand_ids))
    for brand_id in brand_ids:
        run_product_agent_for_brand.delay(brand_id)

    return len(brand_ids)