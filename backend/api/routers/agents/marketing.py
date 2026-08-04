"""
Marketing Agent — trigger + inspect runs.

POST /api/v1/agents/marketing/run                 → run the agent now for the current brand
GET  /api/v1/agents/marketing/campaigns            → list recent campaigns
GET  /api/v1/agents/marketing/content-plans        → list recent weekly content plans
GET  /api/v1/agents/marketing/scheduled-content     → list scheduled/published content
GET  /api/v1/agents/marketing/insights             → list recent insights
GET  /api/v1/agents/marketing/audience-segments     → list audience notes
GET  /api/v1/agents/marketing/content-performance   → list tracked engagement/performance

Wire into your app with:
    from api.routers.agents import marketing as marketing_agent
    app.include_router(marketing_agent.router)
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.marketing import run_marketing_agent
from api.auth import get_current_brand
from db import crud_marketing as crud
from db.models import Brand
from db.session import get_session

router = APIRouter(prefix="/api/v1/agents/marketing", tags=["marketing-agent"])


class RunMarketingAgentRequest(BaseModel):
    task_type: Literal[
        "plan_marketing", "daily_content", "campaign_analysis", "launch_campaign", "audience_analysis",
    ] = "plan_marketing"
    objective: Optional[str] = None
    budget: Literal["low", "medium", "high"] = "medium"
    timeline: str = "7_days"


@router.post("/run")
async def trigger_marketing_agent(
    req: RunMarketingAgentRequest,
    brand: Brand = Depends(get_current_brand),
):
    task = req.model_dump(exclude_none=True)
    task["trigger"] = "manual"
    return await run_marketing_agent(brand.brand_id, task)


@router.get("/campaigns")
async def list_campaigns(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_campaigns(session, brand.brand_id)


@router.get("/content-plans")
async def list_content_plans(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_content_plans(session, brand.brand_id)


@router.get("/scheduled-content")
async def list_scheduled_content(
    status: Optional[str] = None,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_scheduled_content(session, brand.brand_id, status=status)


@router.get("/insights")
async def list_insights(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_marketing_insights(session, brand.brand_id)


@router.get("/audience-segments")
async def list_audience_segments(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_audience_segments(session, brand.brand_id)


@router.get("/content-performance")
async def list_content_performance(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_content_performance(session, brand.brand_id)