"""
Public Website Chat API — Customer Support Agent
===================================================
Unlike WhatsApp/Instagram (Meta pushes messages to us) or email (SendGrid
Inbound Parse pushes to us), there is no external "webchat provider" —
website chat is FashionOS's own product surface: a small chat widget a
brand embeds on their storefront, talking directly to this API. So this
router is a plain public (anonymous, no Clerk auth — website visitors
aren't logged-in FashionOS users) request/response API, not a webhook
receiver, and the customer's reply comes straight back in the HTTP
response rather than being actively sent out through a channel API.

POST /api/v1/support/webchat/{brand_id}/message  → send a message, get the reply
GET  /api/v1/support/webchat/{brand_id}/history  → replay a session's message history

No Clerk auth, so:
  - brand_id is validated against a real, active Brand before doing anything.
  - session_id is an opaque, widget-generated id (e.g. a UUID kept in
    localStorage) — not a real auth credential, just a way to keep one
    visitor's messages in one conversation thread.
  - a lightweight Redis rate limit guards against abuse, since every
    message triggers a real agent run (LLM calls, real tool-call cost).

Mounted as an ISOLATED sub-application (webchat_app below, mounted in
api/main.py at /api/v1/support/webchat) with its own, permissive CORS
policy. A brand's storefront domain is unknown ahead of time (unlike
FRONTEND_URL, which is FashionOS's own dashboard), so this is the one
surface in the API that intentionally accepts cross-origin browser
requests from anywhere, while every other route keeps the app-wide
CORS_ORIGINS policy untouched.

Minimal widget call, for reference:
    const sessionId = localStorage.getItem('fos_chat_sid') || crypto.randomUUID();
    localStorage.setItem('fos_chat_sid', sessionId);
    const res = await fetch(`https://api.example.com/api/v1/support/webchat/${brandId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: userText }),
    });
    const { reply } = await res.json();
"""
import logging
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.customer_support import run_customer_support_agent
from db import crud_customer_support as crud
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webchat"])

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RATE_LIMIT_MAX_MESSAGES = 20
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes
MAX_MESSAGE_LENGTH = 4000


class WebchatMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=200, description="Opaque widget-generated session id — keep it stable across a visitor's page loads (e.g. localStorage).")
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)


class WebchatMessageResponse(BaseModel):
    conversation_id: str
    reply: str
    ticket_status: str = ""
    escalation_required: bool = False


async def _get_active_brand(session: AsyncSession, brand_id: str) -> Brand:
    brand = (await session.execute(select(Brand).where(Brand.brand_id == brand_id))).scalar_one_or_none()
    if not brand or not brand.is_active:
        logger.warning("Webchat request for unknown/inactive brand_id=%s", brand_id)
        raise HTTPException(404, "Unknown brand.")
    return brand


async def _check_rate_limit(brand_id: str, session_id: str) -> None:
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        key = f"webchat:rl:{brand_id}:{session_id}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        if count > RATE_LIMIT_MAX_MESSAGES:
            logger.warning("Webchat rate limit exceeded for brand_id=%s session_id=%s", brand_id, session_id)
            raise HTTPException(429, "Too many messages — please wait a few minutes and try again.")
    finally:
        await r.aclose()


@router.post("/{brand_id}/message", response_model=WebchatMessageResponse)
async def send_webchat_message(
    brand_id: str,
    req: WebchatMessageRequest,
    session: AsyncSession = Depends(get_session),
):
    await _get_active_brand(session, brand_id)
    await _check_rate_limit(brand_id, req.session_id)

    logger.info("Webchat message received for brand_id=%s session_id=%s", brand_id, req.session_id)
    result = await run_customer_support_agent(brand_id, {
        "task_type": "handle_customer_message",
        "channel": "webchat",
        "external_thread_id": req.session_id,
        "message": req.message,
        "trigger": "webchat",
    })

    ticket = result.get("ticket", {})
    return WebchatMessageResponse(
        conversation_id=result.get("conversation_id") or "",
        reply=result.get("customer_reply") or "Sorry, I couldn't process that — please try again in a moment.",
        ticket_status=ticket.get("status", ""),
        escalation_required=result.get("escalation_required", False),
    )


@router.get("/{brand_id}/history")
async def get_webchat_history(
    brand_id: str,
    session_id: str = Query(..., min_length=1, max_length=200),
    session: AsyncSession = Depends(get_session),
):
    await _get_active_brand(session, brand_id)
    logger.info("Webchat history requested for brand_id=%s session_id=%s", brand_id, session_id)
    return await crud.get_conversation_history(session, brand_id, "webchat", session_id, limit=100)


# ── Isolated sub-app — see module docstring for why this needs its own
# permissive CORS policy instead of the app-wide one in api/main.py. ───────

webchat_app = FastAPI(title="FashionOS Webchat")
webchat_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
webchat_app.include_router(router)