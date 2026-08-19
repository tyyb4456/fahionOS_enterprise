"""
Celery app for FashionOS background/scheduled work.

Run a worker:  celery -A tasks.celery_app worker --loglevel=info
Run the beat:  celery -A tasks.celery_app beat --loglevel=info
"""
import logging
import os

from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("fashionos", broker=REDIS_URL, backend=REDIS_URL)
celery_app.autodiscover_tasks(["tasks"])
logger.info("Celery app initialized with broker=%s", REDIS_URL)

celery_app.conf.beat_schedule = {
    "daily-research-trend-monitoring": {
        "task": "tasks.research_tasks.run_research_agent_for_all_brands",
        "schedule": crontab(hour=5, minute=30),  # 05:30 UTC — before the other four, so their runs can read fresh trends
    },
    "research-competitor-pulse": {
        "task": "tasks.research_tasks.run_research_pulse_for_all_brands",
        "schedule": crontab(hour="*/6", minute=0),  # every 6 hours — the "always-on analyst" behavior
    },
    "daily-inventory-review": {
        "task": "tasks.inventory_tasks.run_inventory_agent_for_all_brands",
        "schedule": crontab(hour=6, minute=0),  # 06:00 UTC daily
    },
    "daily-supplier-procurement-review": {
        "task": "tasks.supplier_tasks.run_supplier_agent_for_all_brands",
        "schedule": crontab(hour=6, minute=10),  # 06:10 UTC — after inventory, so it can read fresh pending_approval reorder recommendations
    },
    "daily-sales-review": {
        "task": "tasks.sales_tasks.run_sales_agent_for_all_brands",
        "schedule": crontab(hour=6, minute=15),  # 06:15 UTC — right after inventory
    },
    "daily-marketing-planning": {
        "task": "tasks.marketing_tasks.run_marketing_agent_for_all_brands",
        "schedule": crontab(hour=6, minute=30),  # 06:30 UTC — after sales, so it can read fresh insights
    },
    "publish-due-marketing-content": {
        "task": "tasks.marketing_tasks.publish_due_content_for_all_brands",
        "schedule": crontab(minute="*/15"),  # every 15 min — turns schedule_content() into a real post
    },
    "sync-marketing-content-performance": {
        "task": "tasks.marketing_tasks.sync_content_performance_for_all_brands",
        "schedule": crontab(hour="*/6", minute=45),  # every 6 hours
    },
    "daily-finance-review": {
        "task": "tasks.finance_tasks.run_finance_agent_for_all_brands",
        "schedule": crontab(hour=6, minute=45),  # 06:45 UTC — after sales & marketing, so it reads fresh insights/spend
    },
    "customer-support-escalation-sweep": {
        "task": "tasks.customer_support_tasks.run_escalation_review_for_all_brands",
        "schedule": crontab(minute="*/30"),  # every 30 min — stale open tickets shouldn't silently rot
    },
    "approval-execution-sweep": {
        "task": "tasks.approval_tasks.sweep_unexecuted_approvals",
        "schedule": crontab(minute="*/15"),  # every 15 min — re-enqueue approved items whose background execution was never claimed (broker was down, worker died, etc.)
    },
    "daily-product-merchandising-review": {
        "task": "tasks.product_tasks.run_product_agent_for_all_brands",
        "schedule": crontab(hour=7, minute=0),  # 07:00 UTC — last in the chain, so it reads the freshest
                                                  # opportunities (Research), variant sales (Sales), stock
                                                  # signals (Inventory), campaign response (Marketing), and
                                                  # margins (Finance) from everyone that ran before it today.
    },
}