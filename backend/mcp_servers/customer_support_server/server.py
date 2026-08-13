"""
customer-support-mcp — FashionOS MCP Server
Exposes real courier delivery-status tracking as an MCP tool for the
Customer Support Agent — the "why is my order late" investigation step
(check courier -> check latest location -> determine reason for delay).

Each brand connects their own courier account (API key issued from the
provider's own merchant dashboard — see api/routers/courier.py) and the
credentials get pushed into the same Redis credential cache shopify-mcp/
meta-mcp already share (fashionos:creds:{brand_id} — see
db/credentials.py::BrandCredentials, api/routers/brands.py::
build_brand_credentials). Two providers are wired up so far — PostEx and
Leopards Courier, both widely used in Pakistani e-commerce, matching this
brand's market (see deep_agent/memory.py's seeded AGENTS.md: "market:
Pakistani fashion e-commerce"). Adding a third provider means adding one
`_track_<provider>` function + one status map entry — the tool's return
shape (the contract agents/customer_support/tools.py depends on) never
changes.

Note: exact endpoint paths and response field names for both providers
are reconstructed from their publicly documented merchant APIs and may
have moved since — same caveat meta_server.py already carries for the
Graph API ("worth checking the exact list against current docs if a read
tool starts erroring"). Verify against each provider's current API docs
before relying on this in production; the normalization layer
(_normalize_postex / _normalize_leopards) is isolated specifically so
that's a contained fix, not a rewrite.

Order-level Shopify data (fulfillment status, the tracking_number itself)
lives on shopify-mcp (get_order_by_id), not here.
"""

import logging
import os

import httpx
from fastmcp import FastMCP
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

mcp = FastMCP(
    name="customer-support-mcp",
    instructions=(
        "You have access to real courier delivery-status tracking for whichever "
        "provider this brand has connected (PostEx or Leopards Courier). If the "
        "brand hasn't connected a courier yet, the tool returns a clear "
        "'not connected' error — say so plainly rather than guessing a status."
    ),
)

# ── Multi-tenant credential fetching — same Redis key shopify-mcp/meta-mcp use ─

import redis.asyncio as _aioredis

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


async def _get_brand_creds(brand_id: str) -> dict:
    r = _aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        raw = await r.get(f"fashionos:creds:{brand_id}")
        if not raw:
            logger.error("No credentials found for brand_id=%s", brand_id)
            raise ValueError(f"No credentials found for brand_id='{brand_id}'. Ensure the brand exists.")
        import json as _json
        return _json.loads(raw)
    finally:
        await r.aclose()


# ── Status normalization — provider-specific status strings map onto one
# shared vocabulary the agent's tool contract already expects ─────────────

_POSTEX_STATUS_MAP = {
    "picked": "dispatched",
    "in transit": "in_transit",
    "en-route": "in_transit",
    "out for delivery": "out_for_delivery",
    "delivered": "delivered",
    "returned": "delayed",
    "attempted": "delayed",
}

_LEOPARDS_STATUS_MAP = {
    "booked": "dispatched",
    "in transit": "in_transit",
    "out for delivery": "out_for_delivery",
    "delivered": "delivered",
    "returned to shipper": "delayed",
    "delivery attempted": "delayed",
}


def _normalize_status(raw_status: str, status_map: dict) -> str:
    return status_map.get((raw_status or "").strip().lower(), "unknown")


# ── PostEx ──────────────────────────────────────────────────────────────

async def _track_postex(tracking_number: str, api_key: str) -> dict:
    url = "https://api.postex.pk/services/integration/api/order/v3/get-order-tracking-detail"
    headers = {"token": api_key}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers, params={"trackingNumber": tracking_number})
        r.raise_for_status()
        return r.json()


def _normalize_postex(raw: dict, tracking_number: str, order_id: str) -> dict:
    dist = raw.get("dist") or {}
    raw_status = dist.get("transactionStatusMessage", "")
    history = dist.get("transactionStatusHistory") or []
    latest = history[-1] if history else {}
    status = _normalize_status(raw_status, _POSTEX_STATUS_MAP)

    return {
        "tracking_number": tracking_number,
        "order_id": order_id,
        "status": status,
        "raw_status": raw_status,
        "current_location": latest.get("statusLocation") or dist.get("destinationCity"),
        "delay_reason": raw_status if status == "delayed" else None,
        "estimated_arrival": None,  # PostEx's tracking-detail endpoint doesn't return an ETA field
        "source": "postex",
    }


# ── Leopards Courier ────────────────────────────────────────────────────

async def _track_leopards(tracking_number: str, api_key: str, api_password: str) -> dict:
    url = "https://merchantapi.leopardscourier.com/api/trackBookedPacket/format/json/"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, data={
            "api_key": api_key, "api_password": api_password, "track_numbers": tracking_number,
        })
        r.raise_for_status()
        return r.json()


def _normalize_leopards(raw: dict, tracking_number: str, order_id: str) -> dict:
    packets = raw.get("packet_list") or []
    packet = packets[0] if packets else {}
    raw_status = packet.get("booked_packet_status", "")
    status = _normalize_status(raw_status, _LEOPARDS_STATUS_MAP)

    return {
        "tracking_number": tracking_number,
        "order_id": order_id,
        "status": status,
        "raw_status": raw_status,
        "current_location": packet.get("origin_city") or packet.get("destination_city"),
        "delay_reason": raw_status if status == "delayed" else None,
        "estimated_arrival": None,  # Leopards' tracking response doesn't return an ETA field
        "source": "leopards",
    }


# ── The tool ────────────────────────────────────────────────────────────

@mcp.tool()
async def check_delivery_status(brand_id: str, tracking_number: str, order_id: str) -> dict:
    """
    Check a courier's current delivery status for an order that's already
    left the warehouse — for "where is my order" / "why is my order late"
    investigations. Dispatches to whichever real courier (PostEx or
    Leopards Courier) this brand has connected via
    PUT /api/v1/brands/me/courier — returns a clear "not connected" error
    if none is. Order-level fulfillment_status and the tracking_number
    itself come from get_order_by_id (shopify-mcp) — call that first.

    Args:
        brand_id: The ID of the brand the order belongs to.
        tracking_number: Carrier tracking number (from get_order_by_id).
        order_id: Shopify order_id — passed through into the response for
                  convenience, not sent to the courier's API.

    Used by: Customer Support Agent (delivery-issue investigation).
    """
    try:
        creds = await _get_brand_creds(brand_id)
    except ValueError as e:
        logger.error("Courier credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    provider = creds.get("courier_provider")
    api_key = creds.get("courier_api_key")
    if not provider or not api_key:
        return {
            "error": "No courier connected for this brand. Connect one via "
                     "PUT /api/v1/brands/me/courier before checking delivery status."
        }

    if not tracking_number:
        return {"error": "No tracking_number on file for this order yet — it may not have shipped."}

    try:
        if provider == "postex":
            raw = await _track_postex(tracking_number, api_key)
            return _normalize_postex(raw, tracking_number, order_id)
        elif provider == "leopards":
            # Leopards' API needs api_key + api_password together — the
            # account_id credential slot holds api_password for this
            # provider (see api/routers/courier.py::CourierConnectRequest).
            raw = await _track_leopards(tracking_number, api_key, creds.get("courier_account_id", ""))
            return _normalize_leopards(raw, tracking_number, order_id)
        else:
            return {"error": f"Unsupported courier provider '{provider}' on file for this brand."}
    except httpx.HTTPStatusError as e:
        logger.error("Courier API HTTP error for brand=%s provider=%s: %s", brand_id, provider, e.response.text)
        return {"error": f"{provider} tracking request failed: {e.response.text}"}
    except httpx.HTTPError as e:
        logger.error("Courier API request failed for brand=%s provider=%s: %s", brand_id, provider, e)
        return {"error": f"{provider} tracking request failed: {e}"}


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8005)