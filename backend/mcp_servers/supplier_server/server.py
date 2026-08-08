"""
supplier-mcp — FashionOS MCP Server
Exposes the "external" side of procurement the Supplier Agent needs —
marketplace supplier discovery and courier shipment tracking — as MCP
tools, the same way shopify-mcp exposes Shopify and meta-mcp exposes Meta.

Unlike Shopify/Meta, there's no real OAuth-connected Alibaba/1688/ERP/
courier account anywhere in this codebase (no credentials in .env.example,
no token exchange flow) — building a fake integration against a real
vendor's API would be pure theater. So, same philosophy as
agents/inventory/forecasting.py and agents/supplier/analytics.py
("good enough to unblock the agent today, not a replacement for a real
model/integration"), both tools here are DETERMINISTIC SIMULATIONS,
seeded off inputs already on file (brand_id, sku/product, tracking
number/PO id) so results are stable across repeated calls instead of
being random noise. Swap the internals for a real marketplace/courier API
integration later — the tool signatures and return shapes are the
contract agents/supplier/tools.py depends on, not the data source itself.

Direct supplier outreach (RFQ emails/WhatsApp messages, negotiation
messages) does NOT live here — that goes through the same shared
notifications/dispatch.py every other agent's "notify" tools already use
(see agents/inventory/tools.py::notify_supplier), so it isn't duplicated
into a second messaging path.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastmcp import FastMCP
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

mcp = FastMCP(
    name="supplier-mcp",
    instructions=(
        "You have access to simulated external procurement data sources: a "
        "supplier/marketplace directory search and a courier shipment tracker. "
        "Both are deterministic placeholders (no live Alibaba/1688/courier "
        "account is connected in this environment) — treat their numbers as "
        "directional, not guaranteed, and say so if you report them to the "
        "founder."
    ),
)

_CATEGORIES = ["Textiles Co", "Garment Works", "Fabric House", "Apparel Partners", "Stitch & Supply"]
_REGIONS = ["Faisalabad, PK", "Karachi, PK", "Guangzhou, CN", "Dhaka, BD", "Lahore, PK"]


def _seed(*parts: str) -> int:
    """Stable integer seed from arbitrary strings, so repeated calls with
    the same inputs return the same simulated result instead of random
    noise on every call."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest[:8], 16)


@mcp.tool()
async def search_marketplace_suppliers(
    brand_id: str, product: str, target_price: Optional[float] = None, limit: int = 5,
) -> list[dict]:
    """
    Search external marketplace/manufacturer directories (Alibaba/1688/
    trade-show contacts, in a real integration) for suppliers who could
    make a given product — for when the brand's own approved-supplier list
    (find_suppliers / get_supplier_details, internal tools) doesn't have a
    good match. SIMULATED — no live marketplace account is connected in
    this environment; candidates are deterministically generated from the
    product description so the same query always returns the same
    candidates, but prices/lead times are illustrative, not real quotes.

    Args:
        brand_id: The ID of the brand searching (kept for future per-brand
                  marketplace account scoping).
        product: What's being sourced, e.g. "oversized cotton hoodie".
        target_price: Optional reference unit price to bias candidates around.
        limit: Max candidates to return (default 5).

    Used by: Supplier Agent (find_supplier / procure_inventory tasks, when
    no on-file supplier is a good fit).
    """
    base_seed = _seed(brand_id, product.lower().strip())
    candidates = []
    for i in range(min(limit, 8)):
        s = base_seed + i * 7919
        name = f"{_CATEGORIES[s % len(_CATEGORIES)]} #{s % 900 + 100}"
        region = _REGIONS[(s // 7) % len(_REGIONS)]
        price_jitter = 0.75 + ((s % 50) / 100.0)  # 0.75x - 1.24x
        unit_price = round((target_price or 10.0) * price_jitter, 2)
        lead_time = 7 + (s % 21)  # 7-27 days
        reliability = round(0.65 + (s % 30) / 100.0, 2)  # 0.65-0.94
        moq = [50, 100, 200, 300, 500][s % 5]
        candidates.append({
            "supplier_name": name,
            "region": region,
            "estimated_unit_price": unit_price,
            "lead_time_days": lead_time,
            "moq": moq,
            "estimated_reliability": reliability,
            "source": "simulated_marketplace_search",
        })

    candidates.sort(key=lambda c: c["estimated_unit_price"])
    return candidates


@mcp.tool()
async def track_shipment(brand_id: str, tracking_number: str, purchase_order_id: str) -> dict:
    """
    Check courier/customs status for an in-transit purchase order.
    SIMULATED — no live courier account is connected in this environment;
    status deterministically progresses through manufacturing -> shipped ->
    in_transit -> customs -> delivered based on a seeded "days elapsed"
    value derived from tracking_number/purchase_order_id, so repeated
    calls for the same shipment return consistent, forward-progressing
    results rather than random jitter.

    Args:
        brand_id: The ID of the brand the shipment belongs to.
        tracking_number: Carrier tracking number (from update_shipment_status
                          / a shipment_tracking record).
        purchase_order_id: The purchase_order_id this shipment is for —
                            used (with tracking_number) to seed a stable
                            elapsed-time simulation.

    Used by: Supplier Agent (track_purchase_order task, shipment_updates output).
    """
    seed = _seed(brand_id, tracking_number or "", purchase_order_id)
    days_elapsed = 1 + (seed % 30)

    if days_elapsed < 3:
        status, location = "manufacturing", "Origin factory"
    elif days_elapsed < 7:
        status, location = "shipped", "Origin port"
    elif days_elapsed < 18:
        status, location = "in_transit", "In transit (ocean/air freight)"
    elif days_elapsed < 23:
        status, location = "customs", "Destination customs clearance"
    else:
        status, location = "delivered", "Destination warehouse"

    delayed = (seed % 11) == 0 and status != "delivered"
    if delayed:
        status = "delayed"

    eta = (datetime.now(timezone.utc).date() + timedelta(days=max(0, 25 - days_elapsed)))

    return {
        "tracking_number": tracking_number,
        "purchase_order_id": purchase_order_id,
        "status": status,
        "current_location": location,
        "days_since_dispatch_estimate": days_elapsed,
        "estimated_arrival": eta.isoformat(),
        "source": "simulated_courier_tracking",
    }


if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8003)