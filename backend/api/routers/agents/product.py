"""
Product Agent — trigger + inspect runs.

POST /api/v1/agents/product/run           → run the agent now for the current brand
GET  /api/v1/agents/product/proposals      → list product proposals (optional status filter)
GET  /api/v1/agents/product/collections    → list planned/active collections
GET  /api/v1/agents/product/lifecycle      → list product lifecycle stages (optional stage filter)
GET  /api/v1/agents/product/insights       → list recent merchandising insights

Wire into your app with:
    from api.routers.agents import product as product_agent
    app.include_router(product_agent.router)
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.product import run_product_agent
from api.auth import get_current_brand
from db import crud_product as crud
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents/product", tags=["product-agent"])


class RunProductAgentRequest(BaseModel):
    task_type: Literal[
        "create_product_opportunity", "plan_next_collection", "evaluate_variant_performance",
        "product_lifecycle_review", "launch_product",
    ] = "create_product_opportunity"
    category: Optional[str] = None
    target: Optional[str] = None
    region: Optional[str] = None
    season: Optional[str] = None
    budget: Optional[float] = None
    product_ref: Optional[str] = None


@router.post("/run")
async def trigger_product_agent(
    req: RunProductAgentRequest,
    brand: Brand = Depends(get_current_brand),
):
    logger.info("API trigger product agent for brand_id=%s, task_type=%s", brand.brand_id, req.task_type)
    task = req.model_dump(exclude_none=True)
    task["trigger"] = "manual"
    try:
        res = await run_product_agent(brand.brand_id, task)
        logger.info("Completed API trigger product agent for brand_id=%s", brand.brand_id)
        return res
    except Exception:
        logger.exception("Failed API trigger product agent for brand_id=%s", brand.brand_id)
        raise


@router.get("/proposals")
async def list_proposals(
    status: Optional[str] = None,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing product proposals for brand_id=%s, status=%s", brand.brand_id, status)
    return await crud.list_proposals(session, brand.brand_id, status=status)


@router.get("/collections")
async def list_collections(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing collections for brand_id=%s", brand.brand_id)
    return await crud.list_collections(session, brand.brand_id)


@router.get("/lifecycle")
async def list_lifecycle(
    stage: Optional[str] = None,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing product lifecycle for brand_id=%s, stage=%s", brand.brand_id, stage)
    return await crud.list_lifecycle(session, brand.brand_id, stage=stage)


@router.get("/insights")
async def list_insights(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing merchandising insights for brand_id=%s", brand.brand_id)
    return await crud.list_merchandising_insights(session, brand.brand_id)