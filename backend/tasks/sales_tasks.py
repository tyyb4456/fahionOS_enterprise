"""
Sales Agent — scheduled runs.

`run_sales_agent_for_all_brands` is what the beat schedule in
celery_app.py fires daily; fans out one task per active brand.
"""
import asyncio

from sqlalchemy import select

from db.models import Brand
from db.session import AsyncSessionLocal
from pipeline import run_sales_agent_sync
from tasks.celery_app import celery_app


@celery_app.task(name="tasks.sales_tasks.run_sales_agent_for_brand")
def run_sales_agent_for_brand(brand_id: str, task_type: str = "analyze_sales", time_range: str = "last_7_days") -> dict:
    task = {
        "task_type": task_type,
        "time_range": time_range,
        "priority": "normal",
        "trigger": "daily_scheduler",
    }
    return run_sales_agent_sync(brand_id, task)


@celery_app.task(name="tasks.sales_tasks.run_sales_agent_for_all_brands")
def run_sales_agent_for_all_brands() -> int:
    async def _active_brand_ids() -> list[str]:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(Brand.brand_id).where(Brand.is_active == True)  # noqa: E712
            )).scalars().all()
            return list(rows)

    brand_ids = asyncio.run(_active_brand_ids())
    for brand_id in brand_ids:
        run_sales_agent_for_brand.delay(brand_id)

    return len(brand_ids)