"""
Shopify Webhook Receiver
==========================
Keeps our Postgres mirror of Shopify data in sync so the Inventory Agent's
Context Builder can read from the DB instead of hitting the Shopify API on
every run. api/routers/oauth.py already registers these webhooks against
this exact path when a brand connects Shopify — this file is what was
missing to make that registration do anything.

POST /api/v1/webhooks/shopify/{brand_id}/{topic}

Handles: products/update, orders/paid, orders/cancelled, refunds/create,
inventory_levels/update (the same topics oauth.py registers).

Verified per-brand with the webhook secret generated at OAuth time
(X-Shopify-Hmac-Sha256 header, base64 HMAC-SHA256 of the raw body).

Note: payload shapes below follow Shopify's REST Admin webhook format as of
API version 2026-04 (same version used elsewhere in this codebase) — worth
double-checking against current Shopify docs if fields stop matching.
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.credentials import decrypt_value
from db.models import Brand, OrderLineItem, Product, ProductVariant, Return, SalesOrder
from db.session import AsyncSessionLocal

router = APIRouter(prefix="/api/v1/webhooks/shopify", tags=["shopify-webhooks"])


async def _verify_and_load(request: Request, brand_id: str, session: AsyncSession) -> tuple[Brand, dict]:
    brand = (await session.execute(select(Brand).where(Brand.brand_id == brand_id))).scalar_one_or_none()
    if not brand or not brand.shopify_webhook_secret_enc:
        raise HTTPException(404, "Unknown brand or Shopify not connected.")

    secret = decrypt_value(brand.shopify_webhook_secret_enc)
    body = await request.body()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    received = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(401, "Invalid webhook signature.")

    return brand, json.loads(body)


@router.post("/{brand_id}/{topic:path}")
async def shopify_webhook(brand_id: str, topic: str, request: Request):
    async with AsyncSessionLocal() as session:
        _brand, payload = await _verify_and_load(request, brand_id, session)

        handled = True
        if topic == "products/update":
            await _sync_product(session, brand_id, payload)
        elif topic in ("orders/paid", "orders/cancelled"):
            await _sync_order(session, brand_id, payload)
        elif topic == "refunds/create":
            await _sync_refund(session, brand_id, payload)
        elif topic == "inventory_levels/update":
            await _sync_inventory_level(session, brand_id, payload)
        else:
            handled = False

        await session.commit()

    return {"received": True, "topic": topic, "handled": handled}


async def _sync_product(session: AsyncSession, brand_id: str, payload: dict) -> None:
    shopify_id = payload["id"]
    product = (await session.execute(
        select(Product).where(Product.brand_id == brand_id, Product.shopify_product_id == shopify_id)
    )).scalar_one_or_none()

    if product is None:
        product = Product(brand_id=brand_id, shopify_product_id=shopify_id, title=payload.get("title", ""))
        session.add(product)
        await session.flush()
    else:
        product.title = payload.get("title", product.title)

    product.status = payload.get("status", product.status)
    product.tags = payload.get("tags", product.tags)
    product.synced_at = datetime.now(timezone.utc)

    for v in payload.get("variants", []):
        variant = (await session.execute(
            select(ProductVariant).where(
                ProductVariant.brand_id == brand_id, ProductVariant.shopify_variant_id == v["id"]
            )
        )).scalar_one_or_none()
        if variant is None:
            variant = ProductVariant(
                brand_id=brand_id, product_id=product.id, shopify_variant_id=v["id"],
                sku=v.get("sku") or f"NOSKU-{v['id']}",
            )
            session.add(variant)

        variant.sku = v.get("sku") or variant.sku
        variant.title = v.get("title", variant.title)
        variant.price = float(v.get("price") or 0)
        variant.compare_at_price = float(v["compare_at_price"]) if v.get("compare_at_price") else None
        variant.inventory_item_id = v.get("inventory_item_id")
        variant.inventory_quantity = v.get("inventory_quantity", variant.inventory_quantity)
        variant.synced_at = datetime.now(timezone.utc)

    await session.flush()


async def _sync_order(session: AsyncSession, brand_id: str, payload: dict) -> None:
    shopify_id = payload["id"]
    order = (await session.execute(
        select(SalesOrder).where(SalesOrder.brand_id == brand_id, SalesOrder.shopify_order_id == shopify_id)
    )).scalar_one_or_none()

    if order is None:
        order = SalesOrder(
            brand_id=brand_id,
            shopify_order_id=shopify_id,
            created_at=datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00")),
        )
        session.add(order)
        await session.flush()

    order.financial_status = payload.get("financial_status", order.financial_status)
    order.fulfillment_status = payload.get("fulfillment_status", order.fulfillment_status)

    existing = (await session.execute(
        select(OrderLineItem).where(OrderLineItem.order_id == order.id)
    )).scalars().all()
    existing_by_id = {li.shopify_line_item_id: li for li in existing}

    for item in payload.get("line_items", []):
        li = existing_by_id.get(item.get("id"))
        if li is None:
            li = OrderLineItem(brand_id=brand_id, order_id=order.id, shopify_line_item_id=item.get("id"))
            session.add(li)
        li.product_id = item.get("product_id")
        li.variant_id = item.get("variant_id")
        li.sku = item.get("sku", "")
        li.name = item.get("name", "")
        li.quantity = item.get("quantity", 0)
        li.price = float(item.get("price") or 0)

    await session.flush()


async def _sync_refund(session: AsyncSession, brand_id: str, payload: dict) -> None:
    order_shopify_id = payload.get("order_id")
    line_item_lookup: dict = {}

    if order_shopify_id:
        order = (await session.execute(
            select(SalesOrder).where(SalesOrder.brand_id == brand_id, SalesOrder.shopify_order_id == order_shopify_id)
        )).scalar_one_or_none()
        if order:
            items = (await session.execute(
                select(OrderLineItem).where(OrderLineItem.order_id == order.id)
            )).scalars().all()
            line_item_lookup = {li.shopify_line_item_id: li for li in items}

    for rli in payload.get("refund_line_items", []):
        original = line_item_lookup.get(rli.get("line_item_id"))
        session.add(Return(
            brand_id=brand_id,
            shopify_order_id=order_shopify_id or 0,
            shopify_refund_id=payload.get("id", 0),
            refunded_at=(
                datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
                if payload.get("created_at") else None
            ),
            sku=original.sku if original else "",
            product_name=original.name if original else "",
            quantity=rli.get("quantity", 0),
            restock=rli.get("restock", False),
            return_reason=payload.get("note", ""),
        ))

    await session.flush()


async def _sync_inventory_level(session: AsyncSession, brand_id: str, payload: dict) -> None:
    inventory_item_id = payload.get("inventory_item_id")
    available = payload.get("available")
    if inventory_item_id is None or available is None:
        return

    variant = (await session.execute(
        select(ProductVariant).where(
            ProductVariant.brand_id == brand_id, ProductVariant.inventory_item_id == inventory_item_id
        )
    )).scalar_one_or_none()

    if variant:
        variant.inventory_quantity = available
        variant.synced_at = datetime.now(timezone.utc)
        await session.flush()
