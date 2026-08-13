"""
Brand management — Clerk authenticated.
GET /api/v1/brands/me       → own brand info
PUT /api/v1/brands/me       → update brand name + notification contacts only
                               (credentials come via OAuth now)

Admin:
POST /api/v1/brands/provision  → manual brand creation (X-Admin-Secret)
GET  /api/v1/brands/all        → list all brands (X-Admin-Secret)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.support_email import generate_support_inbound_email

from api.auth import get_current_brand, require_admin
from api.routers.oauth import revoke_meta_token, unregister_shopify_webhooks
from db.credentials import BrandCredentials, cache_brand_credentials, decrypt_value, encrypt_value
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/brands", tags=["brands"])


class BrandProvisionRequest(BaseModel):
    brand_id:             str
    brand_name:           str
    owner_email:          EmailStr
    clerk_user_id:        Optional[str] = None
    plan:                 str = "starter"


class BrandUpdateRequest(BaseModel):
    """Only non-OAuth fields — credentials come through OAuth/courier flows."""
    brand_name:           Optional[str] = None
    brand_owner_whatsapp: Optional[str] = None
    brand_owner_email:    Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = Field(
        default=None,
        description=(
            "This brand's own WhatsApp Business phone_number_id, once connected "
            "under FashionOS's WhatsApp tech-provider setup in Meta Business "
            "Manager (no in-app OAuth flow for this yet). Not a secret — routes "
            "inbound customer WhatsApp messages to this brand and is used as the "
            "FROM number for the Customer Support Agent's replies. Send an empty "
            "string to disconnect."
        ),
    )


class BrandResponse(BaseModel):
    brand_id:             str
    brand_name:           str
    owner_email:          str
    plan:                 str
    is_active:            bool
    meta_ad_account_id:   Optional[str]
    instagram_page_id:    Optional[str]
    whatsapp_phone_number_id: Optional[str]
    brand_owner_whatsapp: Optional[str]
    brand_owner_email:    Optional[str]
    support_inbound_email: Optional[str]
    shopify_connected:    bool
    meta_connected:       bool
    instagram_connected:  bool
    whatsapp_connected:   bool
    courier_connected:    bool
    created_at:           datetime


def _to_response(b: Brand) -> BrandResponse:
    return BrandResponse(
        brand_id             = b.brand_id,
        brand_name           = b.brand_name,
        owner_email          = b.owner_email,
        plan                 = b.plan,
        is_active            = b.is_active,
        meta_ad_account_id   = b.meta_ad_account_id,
        instagram_page_id    = b.instagram_page_id,
        whatsapp_phone_number_id = b.whatsapp_phone_number_id,
        brand_owner_whatsapp = b.brand_owner_whatsapp,
        brand_owner_email    = b.brand_owner_email,
        support_inbound_email = b.support_inbound_email,
        shopify_connected    = bool(b.shopify_access_token_enc),
        meta_connected        = bool(b.meta_access_token_enc),
        instagram_connected  = bool(b.instagram_page_id and b.instagram_access_token_enc),
        whatsapp_connected   = bool(b.whatsapp_phone_number_id),
        courier_connected    = bool(b.courier_provider and b.courier_api_key_enc),
        created_at           = b.created_at,
    )


def build_brand_credentials(b: Brand) -> BrandCredentials:
    """Reconstructs the FULL credentials blob for a brand from its DB row
    — every credential type (Shopify/Meta/courier/notification contacts),
    not just whichever ones the calling code path happens to touch. This
    is the single source of truth for what goes into Redis
    (fashionos:creds:{brand_id}); cache_brand_credentials always
    overwrites the whole key, so a partial reconstruction anywhere would
    silently wipe every OTHER credential type already cached there.
    Reused by api/routers/oauth.py (after a Shopify/Meta OAuth callback)
    and api/routers/courier.py (after connecting a courier) for exactly
    that reason — one builder, every caller, no drift.
    """
    return BrandCredentials(
        shopify_shop_name      = b.shopify_shop_name or "",
        shopify_access_token   = decrypt_value(b.shopify_access_token_enc   or ""),
        shopify_webhook_secret = decrypt_value(b.shopify_webhook_secret_enc or ""),
        meta_access_token      = decrypt_value(b.meta_access_token_enc      or ""),
        meta_ad_account_id     = b.meta_ad_account_id or "",
        instagram_access_token = decrypt_value(b.instagram_access_token_enc or ""),
        instagram_page_id      = b.instagram_page_id or "",
        courier_provider       = b.courier_provider or "",
        courier_api_key        = decrypt_value(b.courier_api_key_enc or ""),
        courier_account_id     = b.courier_account_id or "",
        brand_owner_whatsapp   = b.brand_owner_whatsapp or "",
        brand_owner_email      = b.brand_owner_email or "",
    )


# ── Admin ──────────────────────────────────────────────────────────────────────

@router.post("/provision", status_code=201)
async def provision_brand(
    req:     BrandProvisionRequest,
    _:       None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Provisioning brand brand_id=%s, name=%s", req.brand_id, req.brand_name)
    if (await session.execute(
        select(Brand).where(Brand.brand_id == req.brand_id)
    )).scalar_one_or_none():
        logger.error("Provision brand failed: brand_id=%s already exists", req.brand_id)
        raise HTTPException(400, f"brand_id='{req.brand_id}' already exists.")

    brand = Brand(
        id            = uuid.uuid4(),
        brand_id      = req.brand_id,
        brand_name    = req.brand_name,
        owner_email   = req.owner_email,
        clerk_user_id = req.clerk_user_id,
        plan          = req.plan,
        is_active     = True,
        support_inbound_email = generate_support_inbound_email(req.brand_id),
    )
    session.add(brand)
    await session.flush()
    logger.info("Successfully provisioned brand brand_id=%s", req.brand_id)
    return {"brand_id": req.brand_id, "message": "Brand provisioned. Connect Shopify and Meta via OAuth."}


@router.get("/all", response_model=list[BrandResponse])
async def list_all_brands(
    _:       None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Listing all brands (admin request)")
    brands = (await session.execute(select(Brand).order_by(Brand.created_at))).scalars().all()
    return [_to_response(b) for b in brands]


# ── Brand authenticated ────────────────────────────────────────────────────────

@router.get("/me", response_model=BrandResponse)
async def get_my_brand(brand: Brand = Depends(get_current_brand)):
    logger.info("Fetched brand info for brand_id=%s", brand.brand_id)
    return _to_response(brand)


@router.put("/me", response_model=BrandResponse)
async def update_my_brand(
    req:     BrandUpdateRequest,
    brand:   Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    """Update brand name, notification contacts, and WhatsApp routing number. Other credentials come via OAuth/courier flows."""
    logger.info("Updating brand info for brand_id=%s", brand.brand_id)
    if req.brand_name is not None:
        brand.brand_name = req.brand_name
    if req.brand_owner_whatsapp is not None:
        brand.brand_owner_whatsapp = req.brand_owner_whatsapp
    if req.brand_owner_email is not None:
        brand.brand_owner_email = req.brand_owner_email
    if req.whatsapp_phone_number_id is not None:
        brand.whatsapp_phone_number_id = req.whatsapp_phone_number_id or None

    brand.updated_at = datetime.now(timezone.utc)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.error("Update brand failed: whatsapp_phone_number_id=%s already claimed by another brand", req.whatsapp_phone_number_id)
        raise HTTPException(409, "That WhatsApp phone_number_id is already connected to another brand.")

    await cache_brand_credentials(brand.brand_id, build_brand_credentials(brand))
    logger.info("Successfully updated brand info for brand_id=%s", brand.brand_id)
    return _to_response(brand)


@router.delete("/me/shopify", status_code=204)
async def disconnect_shopify(
    brand:   Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    """Disconnect Shopify — unregisters our webhooks on Shopify's side first
    (so subscriptions don't pile up on reconnect), then clears the token
    from DB and Redis."""
    logger.info("Disconnecting Shopify for brand_id=%s", brand.brand_id)

    if brand.shopify_shop_name and brand.shopify_access_token_enc:
        try:
            await unregister_shopify_webhooks(
                brand.shopify_shop_name,
                decrypt_value(brand.shopify_access_token_enc),
                brand.brand_id,
            )
        except Exception:
            logger.exception(
                "Failed to unregister Shopify webhooks for brand_id=%s — continuing disconnect anyway",
                brand.brand_id,
            )

    brand.shopify_shop_name          = None
    brand.shopify_access_token_enc   = None
    brand.shopify_webhook_secret_enc = None
    brand.updated_at                 = datetime.now(timezone.utc)
    await session.flush()
    await cache_brand_credentials(brand.brand_id, build_brand_credentials(brand))
    logger.info("Shopify disconnected for brand_id=%s", brand.brand_id)


@router.delete("/me/meta", status_code=204)
async def disconnect_meta(
    brand:   Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    """Disconnect Meta — revokes the token on Meta's side first, then clears
    it from DB and Redis."""
    logger.info("Disconnecting Meta for brand_id=%s", brand.brand_id)

    if brand.meta_access_token_enc:
        try:
            await revoke_meta_token(decrypt_value(brand.meta_access_token_enc))
        except Exception:
            logger.exception(
                "Failed to revoke Meta token for brand_id=%s — continuing disconnect anyway",
                brand.brand_id,
            )

    brand.meta_access_token_enc      = None
    brand.meta_ad_account_id         = None
    brand.instagram_access_token_enc = None
    brand.instagram_page_id          = None
    brand.updated_at                 = datetime.now(timezone.utc)
    await session.flush()
    await cache_brand_credentials(brand.brand_id, build_brand_credentials(brand))
    logger.info("Meta disconnected for brand_id=%s", brand.brand_id)