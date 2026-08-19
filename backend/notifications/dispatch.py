"""
Outbound notification dispatch — WhatsApp + email.
================================================================
Shared by every agent's action layer whenever a decision needs to reach a
human (brand owner, supplier) outside the dashboard — e.g. Inventory's
notify_supplier, or Sales/Marketing/Customer Support's notify_brand_owner
(see agents/common/notify_tools.py).

This is platform-level infra (FashionOS's own sending account), not a
per-brand OAuth credential — unlike Meta/Shopify, brand_owner_whatsapp and
brand_owner_email (db/models.py::Brand) are just contact info to send TO,
not credentials to send FROM.

Real deliverability depends on WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN
and RESEND_API_KEY being configured. If they aren't, we log instead of
raising — an agent's run should never fail just because notifications
aren't wired up yet in this environment (same "optional infra, degrade
gracefully" philosophy as agents/*/memory.py's Chroma fallback).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN    = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_API_VERSION     = os.getenv("WHATSAPP_API_VERSION", "v21.0")

RESEND_API_KEY    = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "alerts@fashionos.app")


async def notify_approval_required(brand_id: str, kind: str, title: str, detail: str = "") -> dict:
    """Prompt the brand owner that an item just entered the approval queue.

    Called at creation time by the crud functions that write pending
    reorder/refund/exchange records — so the owner hears about it in
    WhatsApp/email even if they're not staring at the dashboard. Degrades
    to a log when notification channels aren't configured.
    """
    return await notify_brand_owner(
        brand_id, "Approvals",
        f"Approval needed — {kind}: {title}",
        f"{title}\n\n{detail}\n\nOpen the Approval Center in your dashboard to review or reject it."
        if detail else
        f"{title}\n\nOpen the Approval Center in your dashboard to review or reject it.",
    )


async def notify_brand_owner(brand_id: str, agent_name: str, subject: str, message: str) -> dict:
    """Look up a brand's owner contacts and send the alert on both channels.

    Same purpose as agents/common/notify_tools.py::make_notify_brand_owner_tool
    but callable directly from non-agent code (routers, tasks) without a tool
    object. Local imports avoid a load-time cycle with db/session.
    """
    from sqlalchemy import select
    from db.models import Brand
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        brand = (await session.execute(
            select(Brand).where(Brand.brand_id == brand_id)
        )).scalar_one_or_none()
    if not brand:
        logger.error("[notify:owner] brand_id=%s not found", brand_id)
        return {"sent": False, "error": "Brand not found."}

    results = []
    if brand.brand_owner_whatsapp:
        results.append(await send_whatsapp(
            brand.brand_owner_whatsapp, f"[{agent_name}] {subject}\n\n{message}"
        ))
    if brand.brand_owner_email:
        results.append(await send_email(
            brand.brand_owner_email, f"[FashionOS – {agent_name}] {subject}", message
        ))
    if not results:
        return {"sent": False, "error": "No brand owner contact on file."}
    return {"sent": any(r.get("sent") for r in results), "results": results}


async def send_whatsapp(to: str, message: str, from_phone_number_id: Optional[str] = None) -> dict:
    """Send a WhatsApp text message via the Meta WhatsApp Business Cloud API.

    `from_phone_number_id`, when given, sends from that specific brand's
    own connected WhatsApp Business number (see
    db/models.py::Brand.whatsapp_phone_number_id) instead of FashionOS's
    platform-level number — so a customer's reply conversation stays on
    the same number they originally messaged. Falls back to
    WHATSAPP_PHONE_NUMBER_ID (this function's original behavior) when
    omitted — agents/common/notify_tools.py's founder alerts still want
    that: notifying the brand owner isn't a customer-facing conversation
    thread, so there's no "same number" continuity to preserve there.
    """
    if not to:
        return {"sent": False, "channel": "whatsapp", "error": "No recipient number on file."}

    phone_number_id = from_phone_number_id or WHATSAPP_PHONE_NUMBER_ID
    if not (phone_number_id and WHATSAPP_ACCESS_TOKEN):
        logger.info("[notify:whatsapp] (not configured, logging only) -> %s: %s", to, message)
        return {
            "sent": False, "channel": "whatsapp", "to": to,
            "error": "WhatsApp isn't configured in this environment (WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN), and no brand-specific number was given.",
        }

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        logger.error("[notify:whatsapp] Failed HTTP request to %s: %s", to, e)
        return {"sent": False, "channel": "whatsapp", "to": to, "error": str(e)}

    if r.is_success:
        logger.info("[notify:whatsapp] Sent message successfully to %s (from phone_number_id=%s)", to, phone_number_id)
        return {"sent": True, "channel": "whatsapp", "to": to}
    logger.error("[notify:whatsapp] API returned error for %s: %s", to, r.text)
    return {"sent": False, "channel": "whatsapp", "to": to, "error": r.text}


async def send_email(to: str, subject: str, body: str, reply_to: Optional[str] = None) -> dict:
    """Send a plain-text email via Resend. `reply_to`, when given, lets a
    customer's email-client "Reply" route back into our own inbound
    pipeline (see api/routers/customer_support_webhook.py::receive_inbound_email)
    instead of to RESEND_FROM_EMAIL, which isn't monitored."""
    if not to:
        return {"sent": False, "channel": "email", "error": "No recipient email on file."}

    if not RESEND_API_KEY:
        logger.info("[notify:email] (not configured, logging only) -> %s | %s: %s", to, subject, body)
        return {
            "sent": False, "channel": "email", "to": to,
            "error": "Email isn't configured in this environment (RESEND_API_KEY).",
        }

    url = "https://api.resend.com/emails"
    headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "from": RESEND_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        logger.error("[notify:email] Failed HTTP request to %s: %s", to, e)
        return {"sent": False, "channel": "email", "to": to, "error": str(e)}

    if r.is_success:
        logger.info("[notify:email] Sent email successfully to %s", to)
        return {"sent": True, "channel": "email", "to": to}
    logger.error("[notify:email] API returned error for %s: %s", to, r.text)
    return {"sent": False, "channel": "email", "to": to, "error": r.text}