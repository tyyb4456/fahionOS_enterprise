"""
Inbound customer-message webhooks — WhatsApp, Instagram DM, and email all
land here; website chat does NOT (see api/routers/webchat.py — there's no
external "webchat provider" pushing to us, so it's a plain public
request/response API instead of a webhook receiver).

WhatsApp + Instagram DM both land on Meta's webhook infrastructure and
share the same verify-token handshake + payload shape. Email arrives via
Resend Inbound, configured once for the whole platform against a single
shared domain (INBOUND_EMAIL_DOMAIN) — brand routing is done by
plus-addressing (support+{brand_id}@{domain}), not per-brand DNS/Resend
config; see db/support_email.py.

Resend's inbound webhook carries METADATA ONLY — the actual body needs a
follow-up call to Resend's Receiving API (_fetch_resend_email_body below),
unlike the old SendGrid Inbound Parse setup, which posted the full parsed
email in one shot. In exchange, Resend never silently drops a message:
every inbound email is stored regardless of whether this webhook
succeeds, and stays fetchable/replayable from the dashboard or API later
— the reason this codebase moved off SendGrid, whose Inbound Parse
retries for 3 days then permanently drops an email with no notification
if the endpoint stays down.

GET  /api/v1/webhooks/customer-support/meta   → Meta's webhook verification handshake
POST /api/v1/webhooks/customer-support/meta   → inbound WhatsApp + Instagram DM events
POST /api/v1/webhooks/customer-support/email  → inbound email (Resend Inbound, email.received event)
"""
import logging
import os
import re

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from svix.webhooks import Webhook, WebhookVerificationError

from agents.customer_support import run_customer_support_agent
from db import crud_customer_support as crud
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks/customer-support", tags=["customer-support-webhooks"])

META_WEBHOOK_VERIFY_TOKEN = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "")
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
DEFAULT_SUPPORT_BRAND_ID = os.getenv("DEFAULT_SUPPORT_BRAND_ID", "")

_PLUS_TAG_RE = re.compile(r"support\+([^@\s]+)@")
_EMAIL_ADDRESS_RE = re.compile(r"[\w\.\+\-]+@[\w\-]+\.[\w\-\.]+")

async def _resolve_brand_by_whatsapp_phone_number_id(phone_number_id: str) -> str | None:
    if phone_number_id:
        async with AsyncSessionLocal() as session:
            brand_id = await crud.get_brand_id_by_whatsapp_phone_number_id(session, phone_number_id)
        if brand_id:
            return brand_id
        logger.warning("No brand registered for WhatsApp phone_number_id=%s", phone_number_id)

    if DEFAULT_SUPPORT_BRAND_ID:
        logger.warning("Falling back to DEFAULT_SUPPORT_BRAND_ID for WhatsApp phone_number_id=%s", phone_number_id)
        return DEFAULT_SUPPORT_BRAND_ID
    return None


async def _resolve_brand_by_instagram_page_id(ig_page_id: str) -> str | None:
    if ig_page_id:
        async with AsyncSessionLocal() as session:
            brand_id = await crud.get_brand_id_by_instagram_page_id(session, ig_page_id)
        if brand_id:
            return brand_id
        logger.warning("No brand registered for Instagram page id=%s", ig_page_id)

    if DEFAULT_SUPPORT_BRAND_ID:
        logger.warning("Falling back to DEFAULT_SUPPORT_BRAND_ID for Instagram page id=%s", ig_page_id)
        return DEFAULT_SUPPORT_BRAND_ID
    return None



_PLUS_TAG_RE = re.compile(r"support\+([^@\s]+)@")
_EMAIL_ADDRESS_RE = re.compile(r"[\w\.\+\-]+@[\w\-]+\.[\w\-\.]+")


# ── Meta (WhatsApp + Instagram) ─────────────────────────────────────────────

@router.get("/meta")
async def verify_meta_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Meta's one-time webhook subscription handshake — echoes the
    challenge back if the verify token matches what's configured in the
    Meta App dashboard."""
    if hub_mode == "subscribe" and hub_verify_token == META_WEBHOOK_VERIFY_TOKEN and META_WEBHOOK_VERIFY_TOKEN:
        logger.info("Meta webhook verification succeeded for customer-support endpoint")
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge
    logger.error("Meta webhook verification failed — token mismatch or not configured")
    return {"error": "verification failed"}


def _brand_id_for_page(recipient_id: str) -> str | None:
    """
    Placeholder brand resolution for WhatsApp/Instagram — Meta doesn't put
    brand_id in the webhook payload, only the receiving WhatsApp
    phone_number_id / Instagram page id. Deliberately left as a documented
    seam (item 3 of the follow-up list) rather than guessed at — see the
    email path below for how the same problem is actually solved via
    plus-addressing once there's no Meta-imposed payload shape to work
    around.
    """
    return os.getenv("DEFAULT_SUPPORT_BRAND_ID") or None


@router.post("/meta")
async def receive_meta_webhook(request: Request):
    payload = await request.json()
    object_type = payload.get("object")
    logger.info("Received Meta customer-support webhook, object=%s", object_type)

    handled = 0
    for entry in payload.get("entry", []):
        if object_type == "whatsapp_business_account":
            handled += await _handle_whatsapp_entry(entry)
        elif object_type == "instagram":
            handled += await _handle_instagram_entry(entry)

    return {"received": True, "handled": handled}


async def _handle_whatsapp_entry(entry: dict) -> int:
    handled = 0
    for change in entry.get("changes", []):
        value = change.get("value", {})
        metadata = value.get("metadata", {})
        brand_id = await _resolve_brand_by_whatsapp_phone_number_id(metadata.get("phone_number_id", ""))
        if not brand_id:
            continue

        for msg in value.get("messages", []):
            if msg.get("type") != "text":
                continue
            from_number = msg.get("from")
            text = (msg.get("text") or {}).get("body", "")
            if not from_number or not text:
                continue

            await run_customer_support_agent(brand_id, {
                "task_type": "handle_customer_message",
                "channel": "whatsapp",
                "external_thread_id": from_number,
                "message": text,
                "trigger": "webhook:whatsapp",
            })
            handled += 1
    return handled


async def _handle_instagram_entry(entry: dict) -> int:
    handled = 0
    for change in entry.get("messaging", []) or entry.get("changes", []):
        sender = (change.get("sender") or {}).get("id")
        message_text = (change.get("message") or {}).get("text")
        if not sender or not message_text:
            continue
        brand_id = await _resolve_brand_by_instagram_page_id(entry.get("id", ""))
        if not brand_id:
            continue

        await run_customer_support_agent(brand_id, {
            "task_type": "handle_customer_message",
            "channel": "instagram",
            "external_thread_id": sender,
            "message": message_text,
            "trigger": "webhook:instagram",
        })
        handled += 1
    return handled


# ── Email — Resend Inbound ──────────────────────────────────────────────

def _brand_id_from_inbound_addresses(to_addresses: list[str]) -> str | None:
    """
    Extract brand_id from whichever recipient address carries the
    plus-addressed alias, e.g. 'support+brand_xxx@support.fashionos.app'
    -> 'brand_xxx'. Resend's `to` field is a list — check each entry.
    """
    for addr in to_addresses or []:
        match = _PLUS_TAG_RE.search(addr or "")
        if match:
            return match.group(1)
    return None


def _extract_email_address(raw: str) -> str | None:
    """'Jane Doe <jane@example.com>' -> 'jane@example.com'; bare addresses pass through unchanged."""
    match = _EMAIL_ADDRESS_RE.search(raw or "")
    return match.group(0) if match else None


async def _fetch_resend_email_body(email_id: str) -> str:
    """
    Resend's email.received webhook carries metadata only — no body (see
    the module docstring) — so this fetches the actual text content via
    Resend's Receiving API before the agent can do anything with the
    message.

    NOTE: GET /emails/receiving/{id} is inferred from Resend's documented
    SDK method (resend.emails.receiving.get(id)) and its general REST
    conventions (mirrors GET /emails/{id} for sent mail, which *is*
    directly confirmed in their docs) rather than a literally-quoted
    path — verify against resend.com/docs/api-reference before relying
    on this in production. If the path differs, this is the only place
    that needs to change.
    """
    if not RESEND_API_KEY:
        logger.error("Cannot fetch inbound email body — RESEND_API_KEY not configured")
        return ""

    url = f"https://api.resend.com/emails/receiving/{email_id}"
    headers = {"Authorization": f"Bearer {RESEND_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch inbound email body for email_id=%s: %s", email_id, e)
        return ""

    data = r.json()
    text = data.get("text") or ""
    if not text and data.get("html"):
        # Naive fallback if only an HTML part came back — strips tags
        # rather than pulling in a full HTML parser for what should be
        # the uncommon path (plain-text support emails are the norm).
        text = re.sub(r"<[^>]+>", " ", data["html"])
    return text.strip()


@router.post("/email")
async def receive_inbound_email(request: Request):
    """
    Resend Inbound webhook — fires whenever an email arrives at
    *@{INBOUND_EMAIL_DOMAIN} (MX record configured once, platform-wide;
    see db/support_email.py). Verified with Resend's Svix-signed webhook
    (svix-id/svix-timestamp/svix-signature headers + RESEND_WEBHOOK_SECRET)
    — the same verification library this codebase already uses for
    Clerk's webhook (see api/routers/clerk_webhook.py): Svix is a shared
    open signing standard both providers build on, not a Resend-specific
    one, so there's nothing new to learn here.
    """
    if not RESEND_WEBHOOK_SECRET:
        logger.error("Inbound email webhook rejected — RESEND_WEBHOOK_SECRET not configured")
        raise HTTPException(500, "RESEND_WEBHOOK_SECRET not configured.")

    body = await request.body()
    try:
        event = Webhook(RESEND_WEBHOOK_SECRET).verify(body, dict(request.headers))
    except WebhookVerificationError:
        logger.error("Inbound email webhook verification failed — invalid Svix signature")
        raise HTTPException(401, "Invalid webhook signature.")

    if event.get("type") != "email.received":
        # Resend can send other event types to the same endpoint if more
        # get subscribed later (delivery/bounce events, etc.) — ignore
        # anything that isn't a new inbound message.
        return {"received": True, "handled": False, "reason": f"ignored event type '{event.get('type')}'"}

    data = event.get("data", {})
    email_id = data.get("email_id")
    to_addresses = data.get("to", [])
    from_field = data.get("from", "")
    subject = data.get("subject", "")

    brand_id = _brand_id_from_inbound_addresses(to_addresses)
    if not brand_id:
        logger.warning("Inbound email couldn't resolve a brand from to=%s — dropping", to_addresses)
        return {"received": True, "handled": False, "reason": "unresolvable brand"}

    sender_email = _extract_email_address(from_field)
    if not sender_email or not email_id:
        logger.info("Inbound email missing sender or email_id for brand_id=%s — dropping", brand_id)
        return {"received": True, "handled": False, "reason": "missing sender or email_id"}

    text_body = await _fetch_resend_email_body(email_id)
    if not text_body:
        logger.warning("Inbound email_id=%s for brand_id=%s had no retrievable body — dropping", email_id, brand_id)
        return {"received": True, "handled": False, "reason": "empty body"}

    logger.info("Received inbound email for brand_id=%s from=%s", brand_id, sender_email)
    await run_customer_support_agent(brand_id, {
        "task_type": "handle_customer_message",
        "channel": "email",
        "external_thread_id": sender_email,
        "message": f"Subject: {subject}\n\n{text_body}" if subject else text_body,
        "trigger": "webhook:email",
    })

    return {"received": True, "handled": True}