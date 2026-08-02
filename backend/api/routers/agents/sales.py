"""
Sales Agent — trigger + inspect runs.

POST /api/v1/agents/sales/run                → run the agent now for the current brand
GET  /api/v1/agents/sales/insights            → list recent insights
GET  /api/v1/agents/sales/reports             → list recent KPI reports
GET  /api/v1/agents/sales/forecasts           → list recent revenue forecasts
GET  /api/v1/agents/sales/anomalies           → list recent anomalies
GET  /api/v1/agents/sales/customer-segments   → list current customer segments

Wire into your app with:
    from api.routers.agents import sales as sales_agent
    app.include_router(sales_agent.router)
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.sales import run_sales_agent
from api.auth import get_current_brand
from db import crud_sales as crud
from db.models import Brand
from db.session import get_session

router = APIRouter(prefix="/api/v1/agents/sales", tags=["sales-agent"])


class RunSalesAgentRequest(BaseModel):
    task_type: Literal[
        "analyze_sales", "answer_question", "revenue_report", "customer_segmentation", "forecast_revenue",
    ] = "analyze_sales"
    time_range: Literal["today", "yesterday", "last_7_days", "last_14_days", "last_30_days", "last_90_days"] = "last_7_days"
    question: Optional[str] = None


@router.post("/run")
async def trigger_sales_agent(
    req: RunSalesAgentRequest, 
    brand: Brand = Depends(get_current_brand)
):
    task = req.model_dump(exclude_none=True)
    task["trigger"] = "manual"
    return await run_sales_agent(brand.brand_id, task)


@router.get("/insights")
async def list_insights(
    brand: Brand = Depends(get_current_brand), 
    session: AsyncSession = Depends(get_session)
):
    return await crud.list_insights(session, brand.brand_id)


@router.get("/reports")
async def list_reports(
    brand: Brand = Depends(get_current_brand), 
    session: AsyncSession = Depends(get_session)
):
    return await crud.list_reports(session, brand.brand_id)


@router.get("/forecasts")
async def list_forecasts(
    brand: Brand = Depends(get_current_brand), 
    session: AsyncSession = Depends(get_session)
):
    return await crud.list_forecasts(session, brand.brand_id)


@router.get("/anomalies")
async def list_anomalies(
    brand: Brand = Depends(get_current_brand), 
    session: AsyncSession = Depends(get_session)
):
    return await crud.list_anomalies(session, brand.brand_id)


@router.get("/customer-segments")
async def list_customer_segments(
    brand: Brand = Depends(get_current_brand), 
    session: AsyncSession = Depends(get_session)
):
    return await crud.list_customer_segments(session, brand.brand_id)