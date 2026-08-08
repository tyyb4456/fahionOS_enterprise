"""
Supplier Agent — trigger + inspect runs.

POST /api/v1/agents/supplier/run              → run the agent now for the current brand
GET  /api/v1/agents/supplier/purchase-orders   → list open purchase orders + shipment status
GET  /api/v1/agents/supplier/quotes            → list recent quotes
GET  /api/v1/agents/supplier/negotiations      → list recent negotiations
GET  /api/v1/agents/supplier/insights          → list recent supplier insights
GET  /api/v1/agents/supplier/suppliers         → list suppliers with current scores

Wire into your app with:
    from api.routers.agents import supplier as supplier_agent
    app.include_router(supplier_agent.router)
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.supplier import run_supplier_agent
from api.auth import get_current_brand
from db import crud_supplier as crud
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents/supplier", tags=["supplier-agent"])


class RunSupplierAgentRequest(BaseModel):
    task_type: Literal[
        "procure_inventory", "find_supplier", "track_purchase_order", "negotiate", "evaluate_suppliers",
    ] = "evaluate_suppliers"
    sku: Optional[str] = None
    quantity: Optional[int] = None
    product: Optional[str] = None
    purchase_order_id: Optional[str] = None
    deadline: Optional[str] = None


@router.post("/run")
async def trigger_supplier_agent(
    req: RunSupplierAgentRequest,
    brand: Brand = Depends(get_current_brand),
):
    logger.info("API trigger supplier agent for brand_id=%s, task_type=%s", brand.brand_id, req.task_type)
    task = req.model_dump(exclude_none=True)
    task["trigger"] = "manual"
    try:
        res = await run_supplier_agent(brand.brand_id, task)
        logger.info("Completed API trigger supplier agent for brand_id=%s", brand.brand_id)
        return res
    except Exception:
        logger.exception("Failed API trigger supplier agent for brand_id=%s", brand.brand_id)
        raise


@router.get("/purchase-orders")
async def list_purchase_orders(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing supplier purchase orders for brand_id=%s", brand.brand_id)
    return await crud.list_purchase_orders(session, brand.brand_id)


@router.get("/quotes")
async def list_quotes(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing supplier quotes for brand_id=%s", brand.brand_id)
    return await crud.list_quotes(session, brand.brand_id)


@router.get("/negotiations")
async def list_negotiations(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing supplier negotiations for brand_id=%s", brand.brand_id)
    return await crud.list_negotiations(session, brand.brand_id)


@router.get("/insights")
async def list_insights(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing supplier insights for brand_id=%s", brand.brand_id)
    return await crud.list_supplier_insights(session, brand.brand_id)


@router.get("/suppliers")
async def list_suppliers(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing scored suppliers for brand_id=%s", brand.brand_id)
    return await crud.list_suppliers_scored(session, brand.brand_id)