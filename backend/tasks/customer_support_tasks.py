"""
Customer Support Agent — scheduled sweep.

Unlike Inventory/Sales/Marketing/Finance, this agent is primarily
event-driven (see api/routers/customer_support_webhook.py) — there's no
daily "review everything" run that makes sense for live customer
conversations. The one scheduled job here is a periodic sweep for tickets
that have sat open too long without resolution, so nothing silently rots
in the queue.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models import Brand, SupportTicket
from db.session import AsyncSessionLocal
from pipeline import run_customer_support_agent_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

STALE_TICKET_HOURS = 24


@celery_app.task(name="tasks.customer_support_tasks.run_escalation_review_for_all_brands")
def run_escalation_review_for_all_brands() -> int:
    """Beat job — finds tickets that have been open/in_progress for more
    than STALE_TICKET_HOURS with no resolution and re-runs the agent
    against each one with task_type='escalation_review', so a case that
    got stuck doesn't just sit silently."""
    logger.info("Celery task run_escalation_review_for_all_brands triggered")

    async def _stale_tickets() -> list[tuple[str, str]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_TICKET_HOURS)
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(SupportTicket.brand_id, SupportTicket.id).where(
                    SupportTicket.status.in_(["open", "in_progress"]),
                    SupportTicket.updated_at < cutoff,
                )
            )).all()
            return [(r.brand_id, str(r.id)) for r in rows]

    stale = asyncio.run(_stale_tickets())
    logger.info("Found %d stale support tickets for escalation review", len(stale))
    for brand_id, ticket_id in stale:
        run_escalation_review_for_ticket.delay(brand_id, ticket_id)

    return len(stale)


@celery_app.task(name="tasks.customer_support_tasks.run_escalation_review_for_ticket")
def run_escalation_review_for_ticket(brand_id: str, ticket_id: str) -> dict:
    logger.info("Celery task run_escalation_review_for_ticket started for brand_id=%s ticket_id=%s", brand_id, ticket_id)
    task = {
        "task_type": "escalation_review", "priority": "high",
        "issue": f"Ticket {ticket_id} has been open too long without resolution — review and either resolve or escalate.",
        "trigger": "escalation_sweep",
    }
    try:
        res = run_customer_support_agent_sync(brand_id, task)
        logger.info("Celery task run_escalation_review_for_ticket completed for brand_id=%s", brand_id)
        return res
    except Exception:
        logger.exception("Celery task run_escalation_review_for_ticket failed for brand_id=%s", brand_id)
        raise