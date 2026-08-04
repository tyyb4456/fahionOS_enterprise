"""
Outbound notification dispatch — WhatsApp + email.
================================================================
Shared by every agent's action layer whenever a decision needs to reach a
human (brand owner, supplier) outside the dashboard — e.g. Inventory's
notify_supplier, or Sales/Marketing's notify_brand_owner (see
agents/common/notify_tools.py).

This is platform-level infra (FashionOS's own sending account), not a
per-brand OAuth credential — unlike Meta/Shopify, brand_owner_whatsapp and
brand_owner_email (db/models.py::Brand) are just contact info to send TO,
not credentials to send FROM.

Real deliverability depends on WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN
and SENDGRID_API_KEY being configured. If they aren't, we log instead of
raising — an agent's run should never fail just because notifications
aren't wired up yet in this environment (same "optional infra, degrade
gracefully" philosophy as agents/*/memory.py's Chroma fallback).
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN    = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_API_VERSION     = os.getenv("WHATSAPP_API_VERSION", "v21.0")

SENDGRID_API_KEY    = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "alerts@fashionos.app")


async def send_whatsapp(to: str, message: str) -> dict:
    """Send a WhatsApp text message via the Meta WhatsApp Business Cloud API."""
    if not to:
        return {"sent": False, "channel": "whatsapp", "error": "No recipient number on file."}

    if not (WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN):
        logger.info("[notify:whatsapp] (not configured, logging only) -> %s: %s", to, message)
        return {
            "sent": False, "channel": "whatsapp", "to": to,
            "error": "WhatsApp isn't configured in this environment (WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN).",
        }

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        logger.error("[notify:whatsapp] Failed HTTP request to %s: %s", to, e)
        return {"sent": False, "channel": "whatsapp", "to": to, "error": str(e)}

    if r.is_success:
        logger.info("[notify:whatsapp] Sent message successfully to %s", to)
        return {"sent": True, "channel": "whatsapp", "to": to}
    logger.error("[notify:whatsapp] API returned error for %s: %s", to, r.text)
    return {"sent": False, "channel": "whatsapp", "to": to, "error": r.text}


async def send_email(to: str, subject: str, body: str) -> dict:
    """Send a plain-text email via SendGrid."""
    if not to:
        return {"sent": False, "channel": "email", "error": "No recipient email on file."}

    if not SENDGRID_API_KEY:
        logger.info("[notify:email] (not configured, logging only) -> %s | %s: %s", to, subject, body)
        return {
            "sent": False, "channel": "email", "to": to,
            "error": "Email isn't configured in this environment (SENDGRID_API_KEY).",
        }

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": SENDGRID_FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

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