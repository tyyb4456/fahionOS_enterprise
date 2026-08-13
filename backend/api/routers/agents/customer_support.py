"""
Customer Support Agent — trigger + inspect runs.

POST /api/v1/agents/customer-support/run              → run the agent now for an explicit issue
GET  /api/v1/agents/customer-support/tickets           → list support tickets
GET  /api/v1/agents/customer-support/conversations     → list conversations
GET  /api/v1/agents/customer-support/conversations/{id}/messages → one thread's messages
GET  /api/v1/agents/customer-support/refunds           → list refund records
GET  /api/v1/agents/customer-support/exchanges         → list exchange records
GET  /api/v1/agents/customer-support/insights          → list support insights
GET  /api/v1/agents/customer-support/feedback          → list customer feedback

Wire into your app with:
    from api.routers.agents import customer_support as customer_support_agent
    app.include_router(customer_support_agent.router)
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.customer_support import run_customer_support_agent
from api.auth import get_current_brand
from db import crud_customer_support as crud
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents/customer-support", tags=["customer-support-agent"])


class RunCustomerSupportAgentRequest(BaseModel):
    task_type: Literal[
        "handle_customer_message", "handle_customer_issue", "process_return",
        "check_order_status", "escalation_review",
    ] = "handle_customer_issue"
    channel: Optional[Literal["whatsapp", "instagram", "email", "webchat"]] = None
    external_thread_id: Optional[str] = None
    customer_id: Optional[str] = None
    order_id: Optional[str] = None
    message: Optional[str] = None
    issue: Optional[str] = None
    priority: Literal["low", "normal", "high", "critical"] = "normal"


@router.post("/run")
async def trigger_customer_support_agent(
    req: RunCustomerSupportAgentRequest,
    brand: Brand = Depends(get_current_brand),
):
    logger.info("API trigger customer support agent for brand_id=%s, task_type=%s", brand.brand_id, req.task_type)
    task = req.model_dump(exclude_none=True)
    task["trigger"] = "manual"
    try:
        res = await run_customer_support_agent(brand.brand_id, task)
        logger.info("Completed API trigger customer support agent for brand_id=%s", brand.brand_id)
        return res
    except Exception:
        logger.exception("Failed API trigger customer support agent for brand_id=%s", brand.brand_id)
        raise


@router.get("/tickets")
async def list_tickets(
    status: Optional[str] = None,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing support tickets for brand_id=%s, status=%s", brand.brand_id, status)
    return await crud.list_tickets(session, brand.brand_id, status=status)


@router.get("/conversations")
async def list_conversations(
    status: Optional[str] = None,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing support conversations for brand_id=%s, status=%s", brand.brand_id, status)
    return await crud.list_conversations(session, brand.brand_id, status=status)


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing messages for conversation_id=%s, brand_id=%s", conversation_id, brand.brand_id)
    return await crud.list_conversation_messages(session, brand.brand_id, conversation_id)


@router.get("/refunds")
async def list_refunds(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing refund records for brand_id=%s", brand.brand_id)
    return await crud.list_refunds(session, brand.brand_id)


@router.get("/exchanges")
async def list_exchanges(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing exchange records for brand_id=%s", brand.brand_id)
    return await crud.list_exchanges(session, brand.brand_id)


@router.get("/insights")
async def list_insights(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing support insights for brand_id=%s", brand.brand_id)
    return await crud.list_support_insights(session, brand.brand_id)


@router.get("/feedback")
async def list_feedback(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing customer feedback for brand_id=%s", brand.brand_id)
    return await crud.list_customer_feedback(session, brand.brand_id)