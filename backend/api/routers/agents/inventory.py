"""
Inventory Agent — trigger + inspect runs.

POST /api/v1/agents/inventory/run              → run the agent now for the current brand
GET  /api/v1/agents/inventory/alerts            → list alerts (default: unresolved)
GET  /api/v1/agents/inventory/recommendations   → list recommendations (default: pending)

Wire into your app with:
    from api.routers import inventory_agent
    app.include_router(inventory_agent.router)
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.inventory import run_inventory_agent
from api.auth import get_current_brand
from db import crud_inventory as crud
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents/inventory", tags=["inventory-agent"])


class RunInventoryAgentRequest(BaseModel):
    task_type: Literal[
        "forecast_inventory",
        "check_stockouts",
        "reorder_analysis",
        "overstock_analysis",
        "full_inventory_review",
    ] = "forecast_inventory"
    forecast_days: int = 30
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    sku: Optional[str] = None


@router.post("/run")
async def trigger_inventory_agent(
    req: RunInventoryAgentRequest,
    brand: Brand = Depends(get_current_brand),
):
    logger.info("API trigger inventory agent for brand_id=%s, task_type=%s", brand.brand_id, req.task_type)
    task = req.model_dump()
    task["trigger"] = "manual"
    try:
        res = await run_inventory_agent(brand.brand_id, task)
        logger.info("Completed API trigger inventory agent for brand_id=%s", brand.brand_id)
        return res
    except Exception:
        logger.exception("Failed API trigger inventory agent for brand_id=%s", brand.brand_id)
        raise


@router.get("/alerts")
async def list_alerts(
    resolved: bool = False,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing inventory alerts for brand_id=%s, resolved=%s", brand.brand_id, resolved)
    return await crud.list_alerts(session, brand.brand_id, resolved=resolved)


@router.get("/recommendations")
async def list_recommendations(
    status: str = "pending_approval",
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing inventory recommendations for brand_id=%s, status=%s", brand.brand_id, status)
    return await crud.list_recommendations(session, brand.brand_id, status=status)

