"""
Shared "request a research scan" tool factory — lets Sales/Inventory/
Marketing ask the Research Agent to look into something without calling it
directly (agents never call each other directly in this architecture — see
agents/sales/prompt.py: "you don't call other agents directly"). This
queues a real Research Agent run via Celery instead of just leaving a note
in next_actions, so the event-driven trigger described in the Research
Agent design doc ("Sales Agent detects a sudden drop... trigger deeper
research") actually fires instead of waiting for the Supervisor to notice
and re-delegate on the next chat turn.

Not wired into any agent's tool list by default — add
`make_trigger_research_tool(brand_id, agent_name="Sales Agent")` to that
agent's build_internal_tools() to enable it.
"""
from __future__ import annotations

import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class _TriggerResearchArgs(BaseModel):
    reason: str = Field(description="Why a deeper research scan is needed right now — e.g. 'hoodie category revenue dropped 30% with no obvious internal cause'.")
    task_type: str = Field(
        default="trend_monitoring",
        description="'market_research' | 'competitor_analysis' | 'trend_monitoring' | 'pricing_intelligence' | 'product_opportunity_scan'.",
    )
    category: str = Field(default="", description="Optional product category to focus the scan on.")


def make_trigger_research_tool(brand_id: str, agent_name: str) -> StructuredTool:
    async def _run(reason: str, task_type: str = "trend_monitoring", category: str = "") -> dict:
        from tasks.research_tasks import run_research_agent_for_brand
        logger.info("[TriggerResearch:%s] Queuing research run for brand_id=%s, task_type=%s, reason=%s", agent_name, brand_id, task_type, reason)
        try:
            run_research_agent_for_brand.delay(brand_id, task_type=task_type, category=category or None)
        except Exception as exc:
            logger.error("[TriggerResearch:%s] Failed to queue research run for brand_id=%s: %s", agent_name, brand_id, exc)
            return {"queued": False, "error": str(exc)}
        return {"queued": True, "task_type": task_type, "reason": reason}

    return StructuredTool.from_function(
        name="request_research_scan",
        description=(
            "Ask the Research Agent to run a deeper external-market scan in the background "
            "(e.g. a revenue drop with no clear internal cause, growing dead stock in a "
            "category, or a request for campaign-ready trend ideas). Fires a real background "
            "run — it does not return results immediately; the findings land in the Research "
            "Agent's own tables (market_trends, research_insights, ...) for the next "
            "conversation or dashboard view to pick up."
        ),
        args_schema=_TriggerResearchArgs,
        coroutine=_run,
    )