"""
shopify-mcp — FashionOS MCP Server
Exposes the Shopify Admin API as MCP tools for all FashionOS agents.

Read tools  : list_products, get_product_by_sku, get_price_rules, list_locations,
              get_recent_orders, get_returns, calculate_sales_velocity
Write tools : update_product_price, set_inventory_level,
              create_restock_recommendation, create_discount_code
"""

import logging
import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastmcp import FastMCP
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# ── Multi-tenant credential fetching ─────────────────────────────────────────
# MCP servers are shared across all brands.
# Each tool receives brand_id and fetches credentials from Redis.

import redis.asyncio as _aioredis

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


async def _get_brand_creds(brand_id: str) -> dict:
    """
    Fetch decrypted brand credentials from Redis.
    The main API writes these when a brand is created or credentials are updated.
    Raises ValueError if brand_id is not found in cache — caller returns an error response.
    """
    r = _aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        raw = await r.get(f"fashionos:creds:{brand_id}")
        if not raw:
            logger.error("No credentials found for brand_id=%s", brand_id)
            raise ValueError(
                f"No credentials found for brand_id='{brand_id}'. "
                "Ensure the brand exists and POST /api/v1/brands was called first."
            )
        import json as _json
        return _json.loads(raw)
    finally:
        await r.aclose()


# ── FastMCP app ───────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="shopify-mcp",
    instructions=(
        "You have access to a Shopify fashion store. "
        "Use these tools to read product, order, inventory, and returns data, "
        "and to take actions like updating prices, flagging restock needs, or "
        "creating discount codes. All write actions are logged. "
        "Price values are in the store's native currency."
    ),
)

API_VERSION = "2026-04"

# Each tool now does this instead:
async def _shopify_get(brand_id: str, endpoint: str, params: dict | None = None) -> dict:
    creds    = await _get_brand_creds(brand_id)
    shop     = creds["shopify_shop_name"]
    token    = creds["shopify_access_token"]
    base_url = f"https://{shop}.myshopify.com/admin/api/{API_VERSION}"
    headers  = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{base_url}/{endpoint}", headers=headers, params=params or {})
        r.raise_for_status()
        return r.json()

async def _shopify_put(brand_id: str, endpoint: str, payload: dict) -> dict:
    creds    = await _get_brand_creds(brand_id)
    shop     = creds["shopify_shop_name"]
    token    = creds["shopify_access_token"]
    base_url = f"https://{shop}.myshopify.com/admin/api/{API_VERSION}"
    headers  = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.put(f"{base_url}/{endpoint}", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

async def _shopify_post(brand_id: str, endpoint: str, payload: dict) -> dict:
    creds    = await _get_brand_creds(brand_id)
    shop     = creds["shopify_shop_name"]
    token    = creds["shopify_access_token"]
    base_url = f"https://{shop}.myshopify.com/admin/api/{API_VERSION}"
    headers  = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{base_url}/{endpoint}", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def _find_variant_id_by_sku(brand_id: str, sku: str) -> Optional[int]:
    """Internal helper — same lookup as get_product_by_sku but returns just
    the variant_id. Kept separate (rather than calling the @mcp.tool()
    decorated get_product_by_sku directly) so this stays a plain coroutine
    other tools in this module can safely call."""
    try:
        data = await _shopify_get(brand_id, "products.json", {"fields": "id,variants", "limit": 250})
    except ValueError:
        return None
    for product in data.get("products", []):
        for v in product.get("variants", []):
            if v.get("sku") == sku:
                return v["id"]
    return None

# ── READ TOOLS ────────────────────────────────────────────────────────────────

@mcp.tool()
async def list_products(brand_id: str, limit: int = 50, status: str = "active") -> list[dict]:
    """
    List all products with their variants, prices, and live inventory levels.

    Args:
        limit:  Max products to return (default 50, max 250).
        status: "active" | "draft" | "archived" | "any"

    Returns a flat list — each entry is one product with its variants nested.
    Used by: Inventory Agent, Pricing Agent, Marketing Agent.
    """
    try:
        data = await _shopify_get(brand_id, "products.json", {"limit": limit, "status": status, "fields": "id,title,status,tags,image,variants"})
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return [{"error": str(e)}]
    results = []
    for p in data.get("products", []):
        image = p.get("image") or {}
        results.append({
            "product_id":    p["id"],
            "title":         p["title"],
            "status":        p["status"],
            "tags":          p.get("tags", ""),
            "image_url":     image.get("src"),
            "variants": [
                {
                    "variant_id":           v["id"],
                    "sku":                  v.get("sku", ""),
                    "title":                v["title"],         # e.g. "Small / Beige"
                    "price":                float(v["price"]),
                    "compare_at_price":     float(v["compare_at_price"] or 0),
                    "inventory_quantity":   v.get("inventory_quantity", 0),
                    "inventory_management": v.get("inventory_management"),  # "shopify" | null
                }
                for v in p.get("variants", [])
            ],
        })
    return results


@mcp.tool()
async def get_product_by_sku(brand_id: str, sku: str) -> Optional[dict]:
    """
    Fetch a specific product variant by its SKU.

    Args:
        brand_id: The ID of the brand to query. 
        sku: The exact SKU string (case-sensitive).

    Returns product + variant details (including image_url, useful for
    Marketing Agent content) or None if SKU not found.
    Used by: all agents when acting on a specific item.
    """
    try:
        data = await _shopify_get(brand_id, "products.json", {"fields": "id,title,variants,image", "limit": 250})
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    for product in data.get("products", []):
        for v in product.get("variants", []):
            if v.get("sku") == sku:
                image = product.get("image") or {}
                return {
                    "product_id":         product["id"],
                    "product_title":      product["title"],
                    "image_url":          image.get("src"),
                    "variant_id":         v["id"],
                    "sku":                v["sku"],
                    "variant_title":      v["title"],
                    "price":              float(v["price"]),
                    "inventory_quantity": v.get("inventory_quantity", 0),
                }
    return None

@mcp.tool()
async def get_price_rules(brand_id: str, active_only: bool = True) -> list[dict]:
    """
    Fetch all price rules (discounts) currently configured in Shopify.

    Args:
        brand_id: The ID of the brand to query.
        active_only: If True, only returns rules that are currently active
                     (started but not yet expired). Default True.

    Returns a list of price rules with title, value, and validity window.
    Used by: Sales Agent / Pricing Agent (double-discount prevention).
    """
    from datetime import timezone  # add this import

    try:
        data = await _shopify_get(brand_id, "price_rules.json", {
            "limit":  250,
            "fields": "id,title,value_type,value,starts_at,ends_at,created_at",
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return [{"error": str(e)}]

    now = datetime.now(timezone.utc)  # ← aware datetime, matches Shopify's format

    rules = []
    for r in data.get("price_rules", []):
        starts_at = r.get("starts_at")
        ends_at   = r.get("ends_at")

        if active_only:
            if starts_at:
                starts_dt = datetime.fromisoformat(starts_at)
                if starts_dt.tzinfo is None:
                    starts_dt = starts_dt.replace(tzinfo=timezone.utc)
                if starts_dt > now:
                    continue

            if ends_at:
                ends_dt = datetime.fromisoformat(ends_at)
                if ends_dt.tzinfo is None:
                    ends_dt = ends_dt.replace(tzinfo=timezone.utc)
                if ends_dt < now:
                    continue

        rules.append({
            "rule_id":    r["id"],
            "title":      r.get("title", ""),
            "value_type": r.get("value_type", ""),
            "value":      r.get("value", "0"),
            "starts_at":  starts_at,
            "ends_at":    ends_at,
            "created_at": r.get("created_at"),
        })

    return rules


@mcp.tool()
async def list_locations(brand_id: str) -> list[dict]:
    """
    List all fulfillment locations (warehouses) configured in Shopify.

    Args:
        brand_id: The ID of the brand to query.

    Returns location_id + name for each location. Call this before
    set_inventory_level, which requires a location_id and has no other way
    to discover one.
    Used by: Inventory Agent (restock corrections), Restock Agent.
    """
    try:
        data = await _shopify_get(brand_id, "locations.json")
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return [{"error": str(e)}]
    return [
        {
            "location_id": loc["id"],
            "name":        loc.get("name", ""),
            "active":      loc.get("active", True),
        }
        for loc in data.get("locations", [])
    ]


@mcp.tool()
async def get_recent_orders(brand_id: str, hours: int = 24, paid_only: bool = True) -> list[dict]:
    """
    Get all orders placed in the last N hours.

    Args:
        brand_id: The ID of the brand to query.
        hours:     Look-back window in hours (default 24).
        paid_only: If True, only returns paid/fulfilled orders (excludes abandoned carts).

    Returns orders with their line items (sku, quantity, price).
    Used by: Inventory Agent (velocity), Pricing Agent, Marketing Agent.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    params: dict = {
        "created_at_min": since,
        "limit":          250,
        "fields":         "id,created_at,financial_status,fulfillment_status,line_items",
    }
    if paid_only:
        params["financial_status"] = "paid"

    try:
        data = await _shopify_get(brand_id, "orders.json", params)
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return [{"error": str(e)}]

    orders = []
    for o in data.get("orders", []):
        orders.append({
            "order_id":           o["id"],
            "created_at":         o["created_at"],
            "financial_status":   o["financial_status"],
            "fulfillment_status": o.get("fulfillment_status"),
            "line_items": [
                {
                    "product_id": item.get("product_id"),
                    "variant_id": item.get("variant_id"),
                    "sku":        item.get("sku", ""),
                    "name":       item.get("name", ""),
                    "quantity":   item["quantity"],
                    "price":      float(item["price"]),
                }
                for item in o.get("line_items", [])
            ],
        })
    return orders

@mcp.tool()
async def get_payment_summary(brand_id: str, days: int = 30) -> dict:
    """
    Aggregate order payment status over the last N days — counts and
    amounts grouped by financial_status (paid, pending, refunded,
    partially_refunded, voided). Coarser than get_recent_orders (which
    returns full line items): built for "how much is actually collected
    vs outstanding" reconciliation questions.

    Args:
        brand_id: The ID of the brand to query.
        days: Look-back window in days (default 30).

    Used by: Finance Agent (cashflow/profit context, payment reconciliation).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await _shopify_get(brand_id, "orders.json", {
            "created_at_min": since,
            "limit": 250,
            "fields": "id,financial_status,total_price,created_at",
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    summary: dict[str, dict] = {}
    for o in data.get("orders", []):
        status = o.get("financial_status") or "unknown"
        bucket = summary.setdefault(status, {"count": 0, "total": 0.0})
        bucket["count"] += 1
        bucket["total"] += float(o.get("total_price") or 0)

    for bucket in summary.values():
        bucket["total"] = round(bucket["total"], 2)

    return {"period_days": days, "by_status": summary}


@mcp.tool()
async def get_returns(brand_id: str, days: int = 30) -> list[dict]:
    """
    Get all refunds and returns from the last N days.

    Args:
        brand_id: The ID of the brand to query.
        days: Look-back window in days (default 30).

    Returns each returned line item with its SKU and any note the customer left.
    Notes are free-text reason fields — cluster them to find patterns.
    Used by: Returns Agent.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await _shopify_get(brand_id, "orders.json", {
            "created_at_min": since,
            "limit":          250,
            "fields":         "id,refunds,line_items",
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return [{"error": str(e)}]

    returns = []
    for order in data.get("orders", []):
        line_item_map = {li["id"]: li for li in order.get("line_items", [])}

        for refund in order.get("refunds", []):
            for rli in refund.get("refund_line_items", []):
                original = line_item_map.get(rli.get("line_item_id"), {})
                returns.append({
                    "order_id":         order["id"],
                    "refund_id":        refund["id"],
                    "refunded_at":      refund.get("created_at"),
                    "sku":              original.get("sku", ""),
                    "product_name":     original.get("name", ""),
                    "quantity":         rli.get("quantity", 0),
                    "restock":          rli.get("restock", False),
                    "return_reason":    refund.get("note", ""),    # customer's reason
                })
    return returns


@mcp.tool()
async def calculate_sales_velocity(brand_id: str, days: int = 14) -> list[dict]:
    """
    Calculate daily units sold (velocity) per SKU over the last N days.

    Args:
        brand_id: The ID of the brand to query.
        days: Period to calculate over (default 14 days).

    Returns SKUs sorted by velocity descending.
    This is the primary signal for stockout prediction and pricing decisions.
    Used by: Inventory Agent, Pricing Agent, Restock Agent, Marketing Agent.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await _shopify_get(brand_id, "orders.json", {
            "created_at_min":   since,
            "financial_status": "paid",
            "limit":            250,
            "fields":           "line_items,created_at",
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return [{"error": str(e)}]

    sku_data: dict[str, dict] = {}
    for order in data.get("orders", []):
        for item in order.get("line_items", []):
            sku = item.get("sku") or "NO_SKU"
            if sku not in sku_data:
                sku_data[sku] = {
                    "sku":        sku,
                    "name":       item.get("name", ""),
                    "product_id": item.get("product_id"),
                    "variant_id": item.get("variant_id"),
                    "total_units": 0,
                    "total_revenue": 0.0,
                }
            sku_data[sku]["total_units"]   += item.get("quantity", 0)
            sku_data[sku]["total_revenue"] += float(item["price"]) * item.get("quantity", 0)

    result = []
    for sku, d in sku_data.items():
        result.append({
            **d,
            "units_per_day":     round(d["total_units"] / days, 2),
            "period_days":       days,
        })

    return sorted(result, key=lambda x: -x["units_per_day"])


# ── WRITE TOOLS ───────────────────────────────────────────────────────────────

@mcp.tool()
async def update_product_price(
    brand_id: str,
    variant_id: int,
    new_price: float,
    compare_at_price: Optional[float],
    reason: str,
) -> dict:
    """
    Update the selling price of a specific product variant.

    Args:
        brand_id:         The ID of the brand to query. 
        variant_id:       Shopify variant ID (integer).
        new_price:        New price in store currency (e.g. 2499.0 for PKR 2499).
        compare_at_price: Optional "was" price to show a strikethrough.
                          Pass None to clear it (full price, no strikethrough).
        reason:           Why this change is being made — stored in audit log.

    Returns confirmation with old and new price.
    Used by: Pricing Agent (markdowns, trend-based holds).
    """
    payload: dict = {"variant": {"id": variant_id, "price": str(new_price)}}
    if compare_at_price is not None:
        payload["variant"]["compare_at_price"] = str(compare_at_price)
    else:
        payload["variant"]["compare_at_price"] = ""

    try:
        result = await _shopify_put(brand_id, f"variants/{variant_id}.json", payload)
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    v = result.get("variant", {})
    return {
        "success":          True,
        "variant_id":       variant_id,
        "new_price":        new_price,
        "compare_at_price": compare_at_price,
        "reason":           reason,
        "updated_at":       v.get("updated_at"),
    }


@mcp.tool()
async def set_inventory_level(
    brand_id: str,
    inventory_item_id: int,
    location_id: int,
    available: int,
    reason: str,
) -> dict:
    """
    Set the available inventory quantity at a specific location.

    Args:
        brand_id:          The ID of the brand to query.
        inventory_item_id: Shopify inventory item ID (from variant).
        location_id:       Shopify location ID — call list_locations if you don't have this.
        available:         New available quantity (absolute, not delta).
        reason:            Why inventory is being adjusted — for audit log.

    Returns success confirmation.
    Used by: Inventory Agent (corrections), Restock Agent (after delivery).
    """
    try:
        result = await _shopify_post(brand_id, "inventory_levels/set.json", {
            "inventory_item_id": inventory_item_id,
            "location_id":       location_id,
            "available":         available,
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}
    return {
        "success":   True,
        "available": available,
        "reason":    reason,
        "result":    result.get("inventory_level", {}),
    }


@mcp.tool()
async def create_restock_recommendation(
    sku: str,
    recommended_quantity: int,
    urgency: str,
    days_of_stock_remaining: float,
    units_per_day: float,
    reason: str,
    supplier_message: str,
) -> dict:
    """
    Record a restock recommendation for human review. Does NOT auto-order.
    This creates a pending record that shows up in the dashboard for approval.

    Args:
        sku:                     SKU that needs restocking.
        recommended_quantity:    Units to order.
        urgency:                 "critical" (<7 days stock) | "high" (7-14) | "normal" (>14).
        days_of_stock_remaining: Calculated days until stockout at current velocity.
        units_per_day:           Current sales velocity for this SKU.
        reason:                  Human-readable explanation of why restock is needed.
        supplier_message:        Pre-written WhatsApp/email message to send to supplier.

    Used by: Inventory Agent — a lightweight, non-committal flag. For an
    actual real purchase order the agent now creates one directly via its
    own create_purchase_order internal tool (agents/inventory/tools.py) +
    notify_supplier; this tool remains useful when the agent wants to
    surface something without ordering yet.
    """
    return {
        "type":                    "restock_recommendation",
        "sku":                     sku,
        "recommended_quantity":    recommended_quantity,
        "urgency":                 urgency,
        "days_of_stock_remaining": days_of_stock_remaining,
        "units_per_day":           units_per_day,
        "reason":                  reason,
        "supplier_message":        supplier_message,
        "status":                  "pending_approval",
        "created_at":              datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
async def create_discount_code(
    brand_id: str,
    code: str,
    value_type: str,
    value: float,
    title: Optional[str] = None,
    starts_at: Optional[str] = None,
    ends_at: Optional[str] = None,
    usage_limit: Optional[int] = None,
    applies_to_skus: Optional[list[str]] = None,
    reason: str = "",
) -> dict:
    """
    Create a Shopify discount code (price rule + discount code) — e.g. a
    flash-sale or win-back promo.

    Args:
        brand_id: The ID of the brand to query.
        code: The code customers enter at checkout, e.g. "FLASH20".
        value_type: "percentage" | "fixed_amount".
        value: Positive number — percent off (0-100) or currency amount off.
        title: Internal price rule name. Defaults to `code`.
        starts_at: ISO8601. Defaults to now.
        ends_at: ISO8601. Omit for no expiry.
        usage_limit: Max total redemptions. Omit for unlimited.
        applies_to_skus: Limit the discount to specific SKUs. Omit to apply store-wide.
        reason: Why this discount is being created — stored in audit log.

    Returns confirmation with the price_rule_id and discount_code_id.
    Used by: Sales Agent (win-back/flash-sale promos), Marketing Agent
    (campaign offers, via Sales — Marketing itself has no Shopify write access).
    """
    from datetime import timezone

    if value_type not in ("percentage", "fixed_amount"):
        return {"error": "value_type must be 'percentage' or 'fixed_amount'."}

    price_rule: dict = {
        "title": title or code,
        "target_type": "line_item",
        "value_type": value_type,
        "value": f"-{abs(value)}",
        "customer_selection": "all",
        "starts_at": starts_at or datetime.now(timezone.utc).isoformat(),
    }
    if ends_at:
        price_rule["ends_at"] = ends_at
    if usage_limit:
        price_rule["usage_limit"] = usage_limit

    if applies_to_skus:
        variant_ids = []
        for sku in applies_to_skus:
            vid = await _find_variant_id_by_sku(brand_id, sku)
            if vid:
                variant_ids.append(vid)
        if variant_ids:
            price_rule["target_selection"] = "entitled"
            price_rule["entitled_variant_ids"] = variant_ids
        else:
            price_rule["target_selection"] = "all"
    else:
        price_rule["target_selection"] = "all"

    try:
        result = await _shopify_post(brand_id, "price_rules.json", {"price_rule": price_rule})
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}

    rule_id = result.get("price_rule", {}).get("id")
    if not rule_id:
        return {"error": f"Shopify did not return a price_rule id: {result}"}

    code_result = await _shopify_post(
        brand_id, f"price_rules/{rule_id}/discount_codes.json", {"discount_code": {"code": code}}
    )

    return {
        "success": True,
        "price_rule_id": rule_id,
        "discount_code_id": code_result.get("discount_code", {}).get("id"),
        "code": code,
        "value_type": value_type,
        "value": value,
        "applies_to_skus": applies_to_skus or "store-wide",
        "reason": reason,
    }


@mcp.tool()
async def get_abandoned_checkouts(brand_id: str, hours: int = 24) -> list[dict]:
    """
    Get checkouts started but not completed (abandoned carts) in the last N hours.

    Args:
        brand_id: The ID of the brand to query.
        hours: Look-back window in hours (default 24).

    Returns each abandoned checkout with its email (if captured), line
    items, and total value — useful for correlating a revenue dip with
    cart abandonment rather than a real demand drop.
    Used by: Sales Agent (root-cause analysis on revenue changes).
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        data = await _shopify_get(brand_id, "checkouts.json", {
            "created_at_min": since,
            "limit": 250,
            "status": "open",
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return [{"error": str(e)}]

    checkouts = []
    for c in data.get("checkouts", []):
        checkouts.append({
            "checkout_id":  c.get("id"),
            "created_at":   c.get("created_at"),
            "email":        c.get("email"),
            "total_price":  float(c.get("total_price") or 0),
            "line_items": [
                {"sku": item.get("sku", ""), "title": item.get("title", ""), "quantity": item.get("quantity", 0)}
                for item in c.get("line_items", [])
            ],
        })
    return checkouts

@mcp.tool()
async def get_order_by_id(brand_id: str, order_id: str) -> dict:
    """
    Fetch full detail for one order by its Shopify order_id — line items,
    fulfillment/tracking, shipping address, financial status.

    Args:
        brand_id: The ID of the brand to query.
        order_id: Shopify order_id (numeric, as a string is fine).

    Used by: Customer Support Agent — the primary "find this customer's
    order" lookup, richer than get_recent_orders (which is time-windowed
    and doesn't include shipping address / tracking).
    """
    try:
        data = await _shopify_get(brand_id, f"orders/{order_id}.json", {
            "fields": "id,created_at,financial_status,fulfillment_status,total_price,"
                      "line_items,shipping_address,customer,fulfillments"
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        logger.error("Shopify API HTTP error fetching order %s: %s", order_id, e.response.text)
        return {"error": f"Order lookup failed: {e.response.text}"}

    o = data.get("order")
    if not o:
        return {"error": f"No order '{order_id}' found for this brand."}

    fulfillments = o.get("fulfillments", [])
    tracking_number = fulfillments[0].get("tracking_number") if fulfillments else None
    tracking_company = fulfillments[0].get("tracking_company") if fulfillments else None

    return {
        "order_id": o["id"],
        "created_at": o.get("created_at"),
        "financial_status": o.get("financial_status"),
        "fulfillment_status": o.get("fulfillment_status"),
        "total_price": float(o.get("total_price") or 0),
        "shipping_address": o.get("shipping_address"),
        "tracking_number": tracking_number,
        "tracking_company": tracking_company,
        "line_items": [
            {
                "line_item_id": item.get("id"), "product_id": item.get("product_id"),
                "variant_id": item.get("variant_id"), "sku": item.get("sku", ""),
                "name": item.get("name", ""), "quantity": item["quantity"],
                "price": float(item["price"]),
            }
            for item in o.get("line_items", [])
        ],
    }


@mcp.tool()
async def create_refund(
    brand_id: str,
    order_id: str,
    line_item_id: int,
    quantity: int,
    amount: float,
    reason: str,
    restock: bool = True,
) -> dict:
    """
    Issue a real refund on a Shopify order — actual money returned to the
    customer's original payment method.

    Args:
        brand_id: The ID of the brand to query.
        order_id: Shopify order_id.
        line_item_id: The specific line item being refunded (from get_order_by_id).
        quantity: Units being refunded.
        amount: The exact refund amount (in the store's currency) — compute
                this with calculate_refund_amount first, don't guess it.
        reason: Why — stored in Shopify's own audit log.
        restock: Whether to return the units to sellable inventory (default True).

    Returns the Shopify refund id. This is real money — only call after
    confirming eligibility and the amount.
    Used by: Customer Support Agent (refund resolution — pair with the
    internal record_refund tool right after this succeeds).
    """
    payload = {
        "refund": {
            "notify": True,
            "note": reason,
            "refund_line_items": [
                {"line_item_id": line_item_id, "quantity": quantity, "restock_type": "return" if restock else "no_restock"}
            ],
            "transactions": [
                {"amount": str(amount), "kind": "refund", "gateway": "manual"}
            ],
        }
    }
    try:
        result = await _shopify_post(brand_id, f"orders/{order_id}/refunds.json", payload)
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        logger.error("Shopify API HTTP error creating refund for order %s: %s", order_id, e.response.text)
        return {"error": f"Refund failed: {e.response.text}"}

    refund = result.get("refund", {})
    return {
        "success": True,
        "shopify_refund_id": refund.get("id"),
        "order_id": order_id,
        "amount": amount,
        "reason": reason,
        "created_at": refund.get("created_at"),
    }


@mcp.tool()
async def cancel_order(brand_id: str, order_id: str, reason: str, notify_customer: bool = True) -> dict:
    """
    Cancel an order that hasn't shipped yet.

    Args:
        brand_id: The ID of the brand to query.
        order_id: Shopify order_id.
        reason: Shopify's expected values — "customer", "fraud", "inventory",
                "declined", or "other".
        notify_customer: Whether Shopify sends the customer a cancellation email.

    Only call this for unfulfilled orders — check fulfillment_status via
    get_order_by_id first. An already-shipped order needs a return, not a
    cancellation.
    Used by: Customer Support Agent (cancellation requests caught before dispatch).
    """
    valid_reasons = {"customer", "fraud", "inventory", "declined", "other"}
    if reason not in valid_reasons:
        reason = "customer"

    try:
        result = await _shopify_post(brand_id, f"orders/{order_id}/cancel.json", {
            "reason": reason, "email": notify_customer,
        })
    except ValueError as e:
        logger.error("Shopify credential error for brand=%s: %s", brand_id, e)
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        logger.error("Shopify API HTTP error cancelling order %s: %s", order_id, e.response.text)
        return {"error": f"Cancellation failed: {e.response.text}"}

    o = result.get("order", {})
    return {
        "success": True, "order_id": order_id,
        "cancelled_at": o.get("cancelled_at"), "reason": reason,
    }

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
