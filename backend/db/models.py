import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass

# ══════════════════════════════════════════════════════════════════════════════
# brands  — tenant registry
# ══════════════════════════════════════════════════════════════════════════════

class Brand(Base):
    __tablename__ = "brands"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), unique=True, nullable=False, index=True)
    brand_name: Mapped[str]       = mapped_column(String(255), nullable=False)
    owner_email:Mapped[str]       = mapped_column(String(255), unique=True, nullable=False, index=True)
    clerk_user_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    plan:       Mapped[str]       = mapped_column(String(50),  nullable=False, default="starter")
    is_active:  Mapped[bool]      = mapped_column(Boolean,     nullable=False, default=True)

    # Shopify
    shopify_shop_name:          Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shopify_access_token_enc:   Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    shopify_webhook_secret_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Meta Ads
    meta_access_token_enc: Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    meta_ad_account_id:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Instagram DMs
    instagram_access_token_enc: Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    instagram_page_id:          Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Notification recipients (WHERE to send — brand owner's contacts)
    brand_owner_whatsapp: Mapped[Optional[str]] = mapped_column(String(50),  nullable=True)
    brand_owner_email:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

