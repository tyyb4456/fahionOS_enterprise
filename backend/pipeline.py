"""
FashionOS Pipeline Runner
==========================
Sync-safe entry points for running agent graphs.

Two consumers (see db/session.py docstring):
  1. Celery tasks (sync context) — call run_inventory_agent_sync() /
     run_sales_agent_sync() / run_marketing_agent_sync()
  2. FastAPI routes (async)      — call the agent's run_*_agent() directly
                                    (agents/{inventory,sales,marketing}/graph.py)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from agents.inventory.graph import run_inventory_agent
from agents.marketing.graph import run_marketing_agent
from agents.sales.graph import run_sales_agent
from agents.finance.graph import run_finance_agent

logger = logging.getLogger(__name__)


def _run_async(coro: "asyncio.coroutines.Coroutine") -> Any:
    """Run an async coroutine from sync (Celery worker) context."""
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No loop running — the normal case inside a Celery worker.
            return asyncio.run(coro)

        # A loop is already running (e.g. tests, notebooks). Shouldn't happen in
        # a real Celery worker, but don't blow up if it does.
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.get_event_loop().run_until_complete(coro)
    except Exception:
        logger.exception("Error executing coroutine in _run_async")
        raise


def run_inventory_agent_sync(brand_id: str, task: dict) -> dict[str, Any]:
    """Celery-safe wrapper around the async Inventory Agent graph."""
    logger.info("Executing run_inventory_agent_sync for brand_id=%s, task=%s", brand_id, task)
    res = _run_async(run_inventory_agent(brand_id, task))
    logger.info("Finished run_inventory_agent_sync for brand_id=%s", brand_id)
    return res


def run_sales_agent_sync(brand_id: str, task: dict) -> dict[str, Any]:
    """Celery-safe wrapper around the async Sales Agent graph."""
    logger.info("Executing run_sales_agent_sync for brand_id=%s, task=%s", brand_id, task)
    res = _run_async(run_sales_agent(brand_id, task))
    logger.info("Finished run_sales_agent_sync for brand_id=%s", brand_id)
    return res


def run_marketing_agent_sync(brand_id: str, task: dict) -> dict[str, Any]:
    """Celery-safe wrapper around the async Marketing Agent graph."""
    logger.info("Executing run_marketing_agent_sync for brand_id=%s, task=%s", brand_id, task)
    res = _run_async(run_marketing_agent(brand_id, task))
    logger.info("Finished run_marketing_agent_sync for brand_id=%s", brand_id)
    return res


def run_finance_agent_sync(brand_id: str, task: dict) -> dict[str, Any]:
    """Celery-safe wrapper around the async Finance Agent graph."""
    logger.info("Executing run_finance_agent_sync for brand_id=%s, task=%s", brand_id, task)
    res = _run_async(run_finance_agent(brand_id, task))
    logger.info("Finished run_finance_agent_sync for brand_id=%s", brand_id)
    return res
