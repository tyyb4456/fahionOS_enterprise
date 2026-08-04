"""
Cross-agent persistence helpers — execution logging + agent memory audit
trail. Both AgentExecutionLog and AgentMemory (db/models.py) are already
generic, agent-tagged tables; this is the shared read/write layer so
Inventory, Sales, and any future agent write to them the same way instead
of each re-implementing the same two functions under its own crud module.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AgentExecutionLog, AgentMemory

logger = logging.getLogger(__name__)


async def log_execution(
    session: AsyncSession,
    brand_id: str,
    agent: str,
    task_type: str,
    status: str,
    duration_ms: float,
    tools_used: list[str],
    token_usage: dict,
    summary: str,
) -> None:
    logger.info("Logging execution for brand=%s agent=%s task=%s status=%s duration_ms=%.0f",
                brand_id, agent, task_type, status, duration_ms)
    session.add(AgentExecutionLog(
        brand_id=brand_id, agent=agent, task=task_type, status=status,
        duration_ms=duration_ms, tools_used=tools_used, token_usage=token_usage,
        summary=summary,
    ))
    await session.flush()


async def save_agent_memory_record(
    session: AsyncSession, brand_id: str, agent: str, content: str, kind: str = "run_summary"
) -> None:
    """Postgres-only write (the audit trail). Callers that also want a
    semantic copy in Chroma call their own agent's memory.store_memory()
    afterward — kept out of this function so it stays agent-agnostic."""
    logger.info("Saving agent memory record for brand=%s agent=%s kind=%s", brand_id, agent, kind)
    session.add(AgentMemory(brand_id=brand_id, agent=agent, content=content, kind=kind))
    await session.flush()