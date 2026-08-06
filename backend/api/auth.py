"""
FashionOS Authentication — Clerk JWT only.
API keys removed. All routes use get_current_brand (Clerk JWT).
Admin routes use require_admin (X-Admin-Secret header).
"""

import logging
import os
import uuid
from typing import Optional

from clerk_backend_api import Clerk, AuthenticateRequestOptions
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Brand
from db.session import get_session

logger = logging.getLogger(__name__)

ADMIN_SECRET  = os.getenv("FASHIONOS_ADMIN_SECRET", "")
CLERK_SECRET  = os.getenv("CLERK_SECRET_KEY", "")


FRONTEND_URL       = os.getenv("FRONTEND_URL", "http://localhost:5173")
FRONTEND_URL_PROD  = os.getenv("FRONTEND_URL_PROD", "")

authorized = [FRONTEND_URL]
if FRONTEND_URL_PROD:
    authorized.append(FRONTEND_URL_PROD)
_clerk: Optional[Clerk] = None


def _get_clerk() -> Clerk:
    global _clerk
    if _clerk is None:
        if not CLERK_SECRET:
            raise RuntimeError("CLERK_SECRET_KEY not set.")
        _clerk = Clerk(bearer_auth=CLERK_SECRET)
    return _clerk


async def get_current_brand(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Brand:
    """
    Validates Clerk JWT → returns Brand.
    Frontend sends: Authorization: Bearer <clerk_token>
    """
    try:
        state = _get_clerk().authenticate_request(
            request,
            AuthenticateRequestOptions(authorized_parties=authorized),
        )
    except Exception:
        logger.exception("Clerk token authentication failed")
        raise HTTPException(status_code=401, detail="Authentication failed.")

    if not state.is_signed_in:
        logger.error("Authentication attempt rejected: Request is not signed in")
        raise HTTPException(status_code=401, detail="Not authenticated.")

    clerk_user_id = state.payload.get("sub")
    if not clerk_user_id:
        logger.error("Authentication attempt rejected: sub claim missing in Clerk payload")
        raise HTTPException(status_code=401, detail="Invalid token.")

    brand = (await session.execute(
        select(Brand).where(Brand.clerk_user_id == clerk_user_id)
    )).scalar_one_or_none()

    if not brand:
        # Self-healing: lazily provision a Brand if the Clerk user.created
        # webhook was missed (misconfigured/undelivered). Idempotent and safe
        # under concurrent requests. Keeps the DB empty-until-first-login
        # instead of erroring every request with a 404.
        logger.info("No brand for clerk_user_id=%s — lazy-provisioning", clerk_user_id)
        brand = await _provision_brand(session, clerk_user_id, state.payload)

    if not brand.is_active:
        logger.error("Authentication failed: Brand brand_id=%s is inactive", brand.brand_id)
        raise HTTPException(status_code=403, detail="Brand account is inactive.")

    logger.info("Successfully authenticated brand_id=%s for clerk_user_id=%s", brand.brand_id, clerk_user_id)
    return brand


async def _provision_brand(
    session:       AsyncSession,
    clerk_user_id: str,
    payload:       dict,
) -> Brand:
    """Create a Brand for a Clerk user on first authenticated request.

    Identity (email/name) is sourced from the JWT claims if present,
    otherwise via the Clerk API. Falls back to safe placeholders so the
    user can still sign in and complete onboarding from Settings/OAuth.
    """
    email = payload.get("email") or ""
    name  = payload.get("name")  or ""
    if not email or not name:
        try:
            user = await _get_clerk().users.get_async(user_id=clerk_user_id)
            emails = user.email_addresses or []
            primary = user.primary_email_address_id
            for e in emails:
                if getattr(e, "id", None) == primary:
                    email = getattr(e, "email_address", "") or email
            if not email and emails:
                email = getattr(emails[0], "email_address", "") or ""
            first = getattr(user, "first_name", None) or ""
            last  = getattr(user, "last_name", None) or ""
            name  = name or f"{first} {last}".strip()
        except Exception:
            logger.exception("Clerk user fetch failed during lazy brand provisioning")

    if not email:
        email = f"{clerk_user_id}@clerk.local"
    if not name:
        name = email.split("@")[0] or "My Brand"

    brand_id = f"brand_{clerk_user_id[:12].lower()}"
    brand = Brand(
        id            = uuid.uuid4(),
        brand_id      = brand_id,
        brand_name    = name,
        owner_email   = email,
        clerk_user_id = clerk_user_id,
        plan          = "starter",
        is_active     = True,
    )
    session.add(brand)
    try:
        await session.flush()
    except IntegrityError:
        # Concurrent request provisioned it first — return the existing row.
        await session.rollback()
        existing = (await session.execute(
            select(Brand).where(Brand.clerk_user_id == clerk_user_id)
        )).scalar_one_or_none()
        if existing:
            return existing
        raise

    logger.info("Lazy-provisioned brand_id=%s for clerk_user_id=%s", brand_id, clerk_user_id)
    return brand


def require_admin(
    x_admin_secret: str = Header("", alias="X-Admin-Secret"),
) -> None:
    if not ADMIN_SECRET:
        logger.error("Admin request failed: FASHIONOS_ADMIN_SECRET is not configured on server")
        raise HTTPException(500, "FASHIONOS_ADMIN_SECRET not configured.")
    if x_admin_secret != ADMIN_SECRET:
        logger.error("Admin request failed: Invalid admin secret provided")
        raise HTTPException(403, "Invalid admin secret.")
    logger.info("Admin authentication successful")