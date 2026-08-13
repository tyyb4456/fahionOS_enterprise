"""
Courier / delivery-tracking integration — Customer Support Agent.

Unlike Shopify/Meta (OAuth), courier providers in this codebase (PostEx,
Leopards Courier) authenticate with a plain API key issued from the
provider's own merchant dashboard — there's no OAuth flow to redirect
through, so this is simple encrypted credential entry, the same shape as
brands.py's own PUT /me for brand_owner_whatsapp/brand_owner_email, just
for a sensitive value that needs Fernet encryption like Shopify's access
token.

GET    /api/v1/brands/me/courier/providers → list supported couriers
GET    /api/v1/brands/me/courier           → current connection status
PUT    /api/v1/brands/me/courier           → connect/update courier credentials
DELETE /api/v1/brands/me/courier           → disconnect

See mcp_servers/customer_support_server/server.py for where these
credentials actually get used (check_delivery_status).
"""
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_brand
from api.routers.brands import build_brand_credentials
from db.credentials import cache_brand_credentials, encrypt_value
from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/brands/me/courier", tags=["courier"])

SUPPORTED_COURIERS = [
    {"id": "postex", "name": "PostEx", "region": "Pakistan"},
    {"id": "leopards", "name": "Leopards Courier", "region": "Pakistan"},
]


class CourierConnectRequest(BaseModel):
    provider: Literal["postex", "leopards"]
    api_key: str
    account_id: Optional[str] = Field(
        default=None,
        description=(
            "Provider-specific secondary credential, if the provider needs one. "
            "For Leopards Courier this is the account's api_password (Leopards' "
            "API requires api_key + api_password together). Unused for PostEx."
        ),
    )


class CourierStatusResponse(BaseModel):
    connected: bool
    provider: Optional[str] = None
    account_id: Optional[str] = None


@router.get("/providers")
async def list_courier_providers(_: Brand = Depends(get_current_brand)):
    return SUPPORTED_COURIERS


@router.get("", response_model=CourierStatusResponse)
async def get_courier_status(brand: Brand = Depends(get_current_brand)):
    return CourierStatusResponse(
        connected=bool(brand.courier_provider and brand.courier_api_key_enc),
        provider=brand.courier_provider,
        account_id=brand.courier_account_id,
    )


@router.put("", response_model=CourierStatusResponse)
async def connect_courier(
    req: CourierConnectRequest,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Connecting courier provider=%s for brand_id=%s", req.provider, brand.brand_id)
    brand.courier_provider = req.provider
    brand.courier_api_key_enc = encrypt_value(req.api_key)
    brand.courier_account_id = req.account_id
    brand.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await cache_brand_credentials(brand.brand_id, build_brand_credentials(brand))

    logger.info("Courier connected for brand_id=%s provider=%s", brand.brand_id, req.provider)
    return CourierStatusResponse(connected=True, provider=req.provider, account_id=req.account_id)


@router.delete("", status_code=204)
async def disconnect_courier(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Disconnecting courier for brand_id=%s", brand.brand_id)
    brand.courier_provider = None
    brand.courier_api_key_enc = None
    brand.courier_account_id = None
    brand.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await cache_brand_credentials(brand.brand_id, build_brand_credentials(brand))
    logger.info("Courier disconnected for brand_id=%s", brand.brand_id)