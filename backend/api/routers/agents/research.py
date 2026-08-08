"""
Research Agent — trigger + inspect runs.

POST /api/v1/agents/research/run                    → run the agent now for the current brand
GET  /api/v1/agents/research/trends                  → list recent market trends
GET  /api/v1/agents/research/competitors             → list recent competitor analyses
GET  /api/v1/agents/research/opportunities            → list product opportunities (default: proposed)
GET  /api/v1/agents/research/pricing                  → list pricing intelligence
GET  /api/v1/agents/research/insights                 → list recent research insights

Wire into your app with:
    from api.routers.agents import research as research_agent
    app.include_router(research_agent.router)
"""
import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.research import run_research_agent
from api.auth import get_current_brand
from db import crud_research as crud
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents/research", tags=["research-agent"])


class RunResearchAgentRequest(BaseModel):
    task_type: Literal[
        "market_research", "competitor_analysis", "trend_monitoring", "pricing_intelligence", "product_opportunity_scan",
    ] = "trend_monitoring"
    category: Optional[str] = None
    region: Optional[str] = None
    competitors: Optional[List[str]] = None


@router.post("/run")
async def trigger_research_agent(
    req: RunResearchAgentRequest,
    brand: Brand = Depends(get_current_brand),
):
    logger.info("API trigger research agent for brand_id=%s, task_type=%s", brand.brand_id, req.task_type)
    task = req.model_dump(exclude_none=True)
    task["trigger"] = "manual"
    try:
        res = await run_research_agent(brand.brand_id, task)
        logger.info("Completed API trigger research agent for brand_id=%s", brand.brand_id)
        return res
    except Exception:
        logger.exception("Failed API trigger research agent for brand_id=%s", brand.brand_id)
        raise


@router.get("/trends")
async def list_trends(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing market trends for brand_id=%s", brand.brand_id)
    return await crud.list_trends(session, brand.brand_id)


@router.get("/competitors")
async def list_competitors(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing competitor analyses for brand_id=%s", brand.brand_id)
    return await crud.list_competitor_analysis(session, brand.brand_id)


@router.get("/opportunities")
async def list_opportunities(
    status: Optional[str] = "proposed",
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing product opportunities for brand_id=%s, status=%s", brand.brand_id, status)
    return await crud.list_product_opportunities(session, brand.brand_id, status=status)


@router.get("/pricing")
async def list_pricing(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing pricing intelligence for brand_id=%s", brand.brand_id)
    return await crud.list_pricing_intelligence(session, brand.brand_id)


@router.get("/insights")
async def list_insights(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing research insights for brand_id=%s", brand.brand_id)
    return await crud.list_research_insights(session, brand.brand_id)