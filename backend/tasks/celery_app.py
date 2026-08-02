"""
Celery app for FashionOS background/scheduled work.

Run a worker:  celery -A tasks.celery_app worker --loglevel=info
Run the beat:  celery -A tasks.celery_app beat --loglevel=info
"""
import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("fashionos", broker=REDIS_URL, backend=REDIS_URL)
celery_app.autodiscover_tasks(["tasks"])

celery_app.conf.beat_schedule = {
    "daily-inventory-review": {
        "task": "tasks.inventory_tasks.run_inventory_agent_for_all_brands",
        "schedule": crontab(hour=6, minute=0),  # 06:00 UTC daily
    },
}
