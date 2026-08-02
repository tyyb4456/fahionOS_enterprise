import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON,
    String, Text, UniqueConstraint, func,
)
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


# ══════════════════════════════════════════════════════════════════════════════
# Synced Shopify data — written by api/routers/shopify_webhooks.py (kicked off
# by the webhooks OAuth already registers in api/routers/oauth.py). Read-only
# from every agent's perspective: Shopify is the source of truth, this is a
# fast local mirror so the Context Builder doesn't hit the Shopify API on
# every run. Live tools (via shopify-mcp) exist for anything that needs to be
# second-fresh.
# ══════════════════════════════════════════════════════════════════════════════

class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("brand_id", "shopify_product_id", name="uq_products_brand_shopify_id"),)

    id:                 Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:           Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    shopify_product_id: Mapped[int]       = mapped_column(BigInteger, nullable=False)
    title:              Mapped[str]       = mapped_column(String(500), nullable=False)
    status:             Mapped[str]       = mapped_column(String(50), nullable=False, default="active")
    category:           Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags:               Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synced_at:          Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("brand_id", "sku", name="uq_variants_brand_sku"),)

    id:                 Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:           Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    product_id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    shopify_variant_id: Mapped[int]       = mapped_column(BigInteger, nullable=False)
    inventory_item_id:  Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sku:                Mapped[str]       = mapped_column(String(255), nullable=False, index=True)
    title:              Mapped[str]       = mapped_column(String(255), nullable=False, default="")
    price:              Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    compare_at_price:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inventory_quantity: Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    synced_at:          Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SalesOrder(Base):
    __tablename__ = "sales_orders"
    __table_args__ = (UniqueConstraint("brand_id", "shopify_order_id", name="uq_orders_brand_shopify_id"),)

    id:                 Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:           Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    shopify_order_id:   Mapped[int]       = mapped_column(BigInteger, nullable=False)
    created_at:         Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    financial_status:   Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fulfillment_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class OrderLineItem(Base):
    __tablename__ = "order_line_items"

    id:                   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:             Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    order_id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sales_orders.id"), nullable=False, index=True)
    shopify_line_item_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    product_id:           Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    variant_id:           Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sku:                  Mapped[str]       = mapped_column(String(255), nullable=False, default="", index=True)
    name:                 Mapped[str]       = mapped_column(String(500), nullable=False, default="")
    quantity:             Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    price:                Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)


class Return(Base):
    __tablename__ = "returns"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:          Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    shopify_order_id:  Mapped[int]       = mapped_column(BigInteger, nullable=False)
    shopify_refund_id: Mapped[int]       = mapped_column(BigInteger, nullable=False)
    refunded_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sku:               Mapped[str]       = mapped_column(String(255), nullable=False, default="")
    product_name:      Mapped[str]       = mapped_column(String(500), nullable=False, default="")
    quantity:          Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    restock:           Mapped[bool]      = mapped_column(Boolean, nullable=False, default=False)
    return_reason:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ══════════════════════════════════════════════════════════════════════════════
# Operational tables — NOT synced from Shopify. Populated via the dashboard /
# seed scripts. Read by the Inventory Agent's context builder + tools.
# ══════════════════════════════════════════════════════════════════════════════

class Supplier(Base):
    __tablename__ = "suppliers"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:          Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    name:              Mapped[str]       = mapped_column(String(255), nullable=False)
    contact_email:     Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_whatsapp:  Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lead_time_days:    Mapped[int]       = mapped_column(Integer, nullable=False, default=14)
    minimum_order_qty: Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    reliability_score: Mapped[float]     = mapped_column(Float, nullable=False, default=0.8)  # 0-1
    notes:             Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:        Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id:                  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:            Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    name:                Mapped[str]       = mapped_column(String(255), nullable=False)
    capacity:            Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    current_utilization: Mapped[int]       = mapped_column(Integer, nullable=False, default=0)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:          Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    supplier_id:       Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    sku:               Mapped[str]       = mapped_column(String(255), nullable=False)
    ordered_quantity:  Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    expected_delivery: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status:            Mapped[str]       = mapped_column(String(50), nullable=False, default="pending")  # pending|shipped|received|cancelled
    created_at:        Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SeasonalEvent(Base):
    __tablename__ = "seasonal_events"

    id:                         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:                   Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("brands.brand_id"), nullable=True
    )  # null = applies to all brands (e.g. Ramadan, Black Friday)
    name:                       Mapped[str]       = mapped_column(String(255), nullable=False)
    start_date:                 Mapped[date]      = mapped_column(Date, nullable=False)
    end_date:                   Mapped[date]      = mapped_column(Date, nullable=False)
    expected_demand_multiplier: Mapped[float]     = mapped_column(Float, nullable=False, default=1.0)
    notes:                      Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ══════════════════════════════════════════════════════════════════════════════
# Inventory Agent outputs — AI-generated intelligence. The agent's OWN data.
# Never duplicates Shopify inventory; this is forecasts/decisions/logs only.
# ══════════════════════════════════════════════════════════════════════════════

class InventoryForecast(Base):
    __tablename__ = "inventory_forecasts"

    id:                        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:                  Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    sku:                       Mapped[str]       = mapped_column(String(255), nullable=False, index=True)
    forecast_date:             Mapped[date]      = mapped_column(Date, nullable=False)
    forecast_days:             Mapped[int]       = mapped_column(Integer, nullable=False, default=30)
    predicted_units_sold:      Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    predicted_stock_remaining: Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    days_until_stockout:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence:                Mapped[float]     = mapped_column(Float, nullable=False, default=0.5)
    created_at:                Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReorderRecommendation(Base):
    __tablename__ = "reorder_recommendations"

    id:               Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:         Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    sku:              Mapped[str]       = mapped_column(String(255), nullable=False, index=True)
    supplier_id:      Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    quantity:         Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    urgency:          Mapped[str]       = mapped_column(String(20), nullable=False, default="normal")  # critical|high|normal
    reason:           Mapped[str]       = mapped_column(Text, nullable=False, default="")
    supplier_message: Mapped[str]       = mapped_column(Text, nullable=False, default="")
    status:           Mapped[str]       = mapped_column(String(30), nullable=False, default="pending_approval")
    # pending_approval|approved|rejected|ordered
    created_at:       Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InventoryAlert(Base):
    __tablename__ = "inventory_alerts"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    type:       Mapped[str]       = mapped_column(String(50), nullable=False)   # stockout_risk|overstock|velocity_spike|...
    severity:   Mapped[str]       = mapped_column(String(20), nullable=False, default="low")  # low|medium|high|critical
    sku:        Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    resolved:   Mapped[bool]      = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgentExecutionLog(Base):
    __tablename__ = "agent_execution_log"

    id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:    Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    agent:       Mapped[str]       = mapped_column(String(100), nullable=False)   # "inventory_agent"
    task:        Mapped[str]       = mapped_column(String(100), nullable=False)   # task_type
    status:      Mapped[str]       = mapped_column(String(20), nullable=False)    # running|completed|failed
    duration_ms: Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    tools_used:  Mapped[list]      = mapped_column(JSON, nullable=False, default=list)
    token_usage: Mapped[dict]      = mapped_column(JSON, nullable=False, default=dict)
    summary:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PolicyDocument(Base):
    """
    Bookkeeping for uploaded policy documents (Inventory Policy.pdf, Supplier
    Contracts.pdf, ...). The actual chunk text + embeddings live in Chroma
    (see agents/inventory/memory.py) — this table exists so the dashboard
    can list/delete what's been indexed without querying Chroma directly,
    which has no clean "list distinct sources" operation of its own.
    """
    __tablename__ = "policy_documents"

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:     Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    filename:     Mapped[str]       = mapped_column(String(500), nullable=False)
    chunk_count:  Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    created_at:   Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    agent:      Mapped[str]       = mapped_column(String(100), nullable=False)
    kind:       Mapped[str]       = mapped_column(String(50), nullable=False, default="run_summary")
    content:    Mapped[str]       = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
