"""
Finance Agent — trigger + inspect runs.

POST /api/v1/agents/finance/run                   → run the agent now for the current brand
GET  /api/v1/agents/finance/reports                → list recent financial reports
GET  /api/v1/agents/finance/forecasts              → list recent cashflow forecasts
GET  /api/v1/agents/finance/insights               → list recent financial insights
GET  /api/v1/agents/finance/budget-recommendations → list recent budget recommendations
GET  /api/v1/agents/finance/risk-assessments       → list risk assessments (default: unresolved)
GET  /api/v1/agents/finance/expenses               → list recent expenses

Wire into your app with:
    from api.routers.agents import finance as finance_agent
    app.include_router(finance_agent.router)
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.finance import run_finance_agent
from api.auth import get_current_brand
from db import crud_finance as crud
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents/finance", tags=["finance-agent"])


class RunFinanceAgentRequest(BaseModel):
    task_type: Literal[
        "financial_analysis", "evaluate_purchase_order", "cashflow_forecast", "budget_review", "expense_analysis",
    ] = "financial_analysis"
    time_range: Literal["today", "yesterday", "last_7_days", "last_14_days", "last_30_days", "last_90_days"] = "last_30_days"
    forecast_days: int = 30
    purchase_order_id: Optional[str] = None


@router.post("/run")
async def trigger_finance_agent(
    req: RunFinanceAgentRequest,
    brand: Brand = Depends(get_current_brand),
):
    logger.info("API trigger finance agent for brand_id=%s, task_type=%s", brand.brand_id, req.task_type)
    task = req.model_dump(exclude_none=True)
    task["trigger"] = "manual"
    try:
        res = await run_finance_agent(brand.brand_id, task)
        logger.info("Completed API trigger finance agent for brand_id=%s", brand.brand_id)
        return res
    except Exception:
        logger.exception("Failed API trigger finance agent for brand_id=%s", brand.brand_id)
        raise


@router.get("/reports")
async def list_reports(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing financial reports for brand_id=%s", brand.brand_id)
    return await crud.list_financial_reports(session, brand.brand_id)


@router.get("/forecasts")
async def list_forecasts(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing financial forecasts for brand_id=%s", brand.brand_id)
    return await crud.list_financial_forecasts(session, brand.brand_id)


@router.get("/insights")
async def list_insights(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing financial insights for brand_id=%s", brand.brand_id)
    return await crud.list_financial_insights(session, brand.brand_id)


@router.get("/budget-recommendations")
async def list_budget_recommendations(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing budget recommendations for brand_id=%s", brand.brand_id)
    return await crud.list_budget_recommendations(session, brand.brand_id)


@router.get("/risk-assessments")
async def list_risk_assessments(
    resolved: bool = False,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing risk assessments for brand_id=%s, resolved=%s", brand.brand_id, resolved)
    return await crud.list_risk_assessments(session, brand.brand_id, resolved=resolved)


@router.get("/expenses")
async def list_expenses(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing expenses for brand_id=%s", brand.brand_id)
    return await crud.list_expenses(session, brand.brand_id)