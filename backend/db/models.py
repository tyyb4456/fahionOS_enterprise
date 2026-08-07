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
# chat_tool_results  — persists structured tool output per chat turn
# ══════════════════════════════════════════════════════════════════════════════

class ChatToolResult(Base):
    """
    One row per tool call (or persisted reasoning block) during a chat turn.

    Keyed by (brand_id, thread_id, turn_index, label).
    turn_index = 0-based index of the assistant message this belongs to,
    computed by counting existing AI messages in the checkpoint at stream start.

    data column stores the full structured JSON (InventoryAnalysis, etc.)
    so the frontend can render rich cards when loading conversation history.
    """
    __tablename__ = "chat_tool_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id:  Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Human-readable label for this row: a tool name (get_inventory_status),
    # a comma-joined list of pipeline agents that ran (inventory,trend,pricing),
    # or the reasoning sentinel (see deep_agents/streaming.py REASONING_SENTINEL).
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data:    Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
    # Featured product image — synced from Shopify's `image.src` on
    # products/update (see api/routers/shopify_webhook.py::_sync_product).
    # Added for the Marketing Agent, which needs real imagery to publish
    # Instagram content (see agents/marketing/tools.py::schedule_content /
    # meta-mcp's publish_instagram_post).
    image_url:          Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
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
    # Manually entered via dashboard/seed (Shopify's REST fields config here
    # doesn't sync unit cost) — needed for the Finance Agent's margin/
    # profitability math. Nullable: agents must flag SKUs where it's unset
    # rather than guessing a cost.
    cost_price:         Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    synced_at:          Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SalesOrder(Base):
    __tablename__ = "sales_orders"
    __table_args__ = (UniqueConstraint("brand_id", "shopify_order_id", name="uq_orders_brand_shopify_id"),)

    id:                  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:            Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    shopify_order_id:    Mapped[int]       = mapped_column(BigInteger, nullable=False)
    shopify_customer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    created_at:          Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    financial_status:    Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fulfillment_status:  Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # ── Sales Agent fields — revenue/discount analytics (Shopify order totals) ──
    subtotal_price:      Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    total_discounts:     Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    total_price:         Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    discount_codes:      Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # comma-joined codes


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
    refund_amount:     Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    restock:           Mapped[bool]      = mapped_column(Boolean, nullable=False, default=False)
    return_reason:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Customer(Base):
    """
    Synced Shopify customer data — denormalized straight off the `customer`
    object nested in Shopify's orders/paid webhook payload (see
    api/routers/shopify_webhook.py::_sync_customer). No separate
    customers/* webhook subscription needed for this to stay reasonably
    fresh, since every paid order carries the buyer's current customer
    record. Read by the Sales Agent for segmentation/LTV/cohort analysis.
    """
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("brand_id", "shopify_customer_id", name="uq_customers_brand_shopify_id"),)

    id:                  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:            Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    shopify_customer_id: Mapped[int]       = mapped_column(BigInteger, nullable=False)
    email:               Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name:          Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name:           Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country:             Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city:                Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    orders_count:        Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    total_spent:         Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    first_order_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_order_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at:           Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


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
    # Real purchase_order this recommendation resulted in, once the agent
    # actually executes it (see agents/inventory/tools.py::create_purchase_order).
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True)
    created_at:       Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InventoryAlert(Base):
    __tablename__ = "inventory_alerts"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    type:       Mapped[str]       = mapped_column(String(50), nullable=False)   # stockout_risk|overstock|velocity_spike|sales_agent_flag|...
    severity:   Mapped[str]       = mapped_column(String(20), nullable=False, default="low")  # low|medium|high|critical
    sku:        Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    resolved:   Mapped[bool]      = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgentExecutionLog(Base):
    __tablename__ = "agent_execution_log"

    id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:    Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    agent:       Mapped[str]       = mapped_column(String(100), nullable=False)   # "inventory_agent" | "sales_agent" | "marketing_agent"
    task:        Mapped[str]       = mapped_column(String(100), nullable=False)   # task_type
    status:      Mapped[str]       = mapped_column(String(20), nullable=False)    # running|completed|failed
    duration_ms: Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    tools_used:  Mapped[list]      = mapped_column(JSON, nullable=False, default=list)
    token_usage: Mapped[dict]      = mapped_column(JSON, nullable=False, default=dict)
    summary:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PolicyDocument(Base):
    """
    Bookkeeping for uploaded policy documents. The `agent` field routes a
    document to the right Chroma collection (inventory_policies_{brand_id}
    vs sales_policies_{brand_id} vs marketing_policies_{brand_id} — see
    agents/inventory/memory.py, agents/sales/memory.py,
    agents/marketing/memory.py) so list/delete know which one to touch.
    """
    __tablename__ = "policy_documents"

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:     Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    agent:        Mapped[str]       = mapped_column(String(50), nullable=False, default="inventory", server_default="inventory")
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


# ══════════════════════════════════════════════════════════════════════════════
# Sales Agent outputs — AI-generated business intelligence.
# ══════════════════════════════════════════════════════════════════════════════

class SalesReport(Base):
    __tablename__ = "sales_reports"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    period:     Mapped[str]       = mapped_column(String(50), nullable=False, default="last_7_days")
    summary:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    kpis:       Mapped[dict]      = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SalesInsight(Base):
    __tablename__ = "sales_insights"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    category:   Mapped[str]       = mapped_column(String(50), nullable=False, default="revenue")
    severity:   Mapped[str]       = mapped_column(String(20), nullable=False, default="low")
    message:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float]     = mapped_column(Float, nullable=False, default=0.5)
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SalesForecast(Base):
    __tablename__ = "sales_forecasts"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:          Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    forecast_date:     Mapped[date]      = mapped_column(Date, nullable=False)
    predicted_revenue: Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    predicted_orders:  Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    confidence:        Mapped[float]     = mapped_column(Float, nullable=False, default=0.5)
    created_at:        Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SalesAnomaly(Base):
    __tablename__ = "sales_anomalies"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    metric:     Mapped[str]       = mapped_column(String(100), nullable=False)
    expected:   Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    actual:     Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    severity:   Mapped[str]       = mapped_column(String(20), nullable=False, default="low")
    message:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CustomerSegment(Base):
    __tablename__ = "customer_segments"
    __table_args__ = (UniqueConstraint("brand_id", "segment", name="uq_segment_brand_name"),)

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:       Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    segment:        Mapped[str]       = mapped_column(String(50), nullable=False)   # VIP|Loyal|New|At Risk|Inactive
    customer_count: Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    definition:     Mapped[str]       = mapped_column(Text, nullable=False, default="")
    customer_ids:   Mapped[list]      = mapped_column(JSON, nullable=False, default=list)
    updated_at:     Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ══════════════════════════════════════════════════════════════════════════════
# Marketing Agent outputs — AI-generated campaigns, content, and insights.
# Product/Sales/Inventory tables above are READ, not owned, by this agent —
# see agents/marketing/tools.py / db/crud_marketing.py for the cross-agent
# reads (SalesInsight, SalesReport, CustomerSegment, InventoryAlert,
# InventoryForecast) that feed its context builder rather than recomputing
# the same analysis.
# ══════════════════════════════════════════════════════════════════════════════

class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id:               Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:         Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    name:             Mapped[str]       = mapped_column(String(255), nullable=False)
    goal:             Mapped[str]       = mapped_column(Text, nullable=False, default="")
    platform:         Mapped[str]       = mapped_column(String(100), nullable=False, default="multi-channel")
    target_audience:  Mapped[str]       = mapped_column(String(255), nullable=False, default="")
    budget:           Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    duration_days:    Mapped[int]       = mapped_column(Integer, nullable=False, default=7)
    status:           Mapped[str]       = mapped_column(String(30), nullable=False, default="draft")
    # draft|launched|scheduled|completed|paused
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # set once a real Meta Ads campaign exists
    created_at:       Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ContentPlan(Base):
    """
    Weekly content calendar overview — topics + platforms for the week, not
    individual posts (see ScheduledContent for the operational, per-post
    record that actually gets executed/published).
    """
    __tablename__ = "content_plans"

    id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:      Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    week_start:    Mapped[date]      = mapped_column(Date, nullable=False)
    topics:        Mapped[list]      = mapped_column(JSON, nullable=False, default=list)
    platforms:     Mapped[list]      = mapped_column(JSON, nullable=False, default=list)
    created_at:    Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScheduledContent(Base):
    """
    The operational record behind "Content Scheduler" — one row per post/
    email/SMS the agent has queued for publishing. Not in the original
    design doc's table list, but necessary to make scheduling a *real*
    action rather than a description of one: tasks/marketing_tasks.py's
    publish_due_content beat job polls this table and calls the matching
    meta-mcp tool (or, for email/sms, marks it awaiting_integration pending
    an ESP/SMS gateway — see agents/marketing/prompts.py) once
    scheduled_for arrives.
    """
    __tablename__ = "scheduled_content"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:          Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    campaign_id:       Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("marketing_campaigns.id"), nullable=True)
    platform:          Mapped[str]       = mapped_column(String(50), nullable=False)   # instagram|facebook|email|sms|tiktok|blog
    content_type:      Mapped[str]       = mapped_column(String(50), nullable=False)   # post|story|reel|email|sms|blog
    content:           Mapped[dict]      = mapped_column(JSON, nullable=False, default=dict)  # caption/hashtags/image_url/subject/body/cta/sms_text
    scheduled_for:     Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)
    status:            Mapped[str]       = mapped_column(String(20), nullable=False, default="scheduled")
    # scheduled|published|failed|awaiting_integration
    published_ref_id:  Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # e.g. Instagram media_id
    error:             Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:        Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketingInsight(Base):
    __tablename__ = "marketing_insights"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    insight:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float]     = mapped_column(Float, nullable=False, default=0.5)
    priority:   Mapped[str]       = mapped_column(String(20), nullable=False, default="low")  # low|medium|high
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AudienceSegment(Base):
    """
    Marketing's own audience/targeting notes — distinct from Sales'
    CustomerSegment (RFM buckets with concrete customer_ids). This is the
    agent's qualitative read on which segment to target for a given goal
    and how it's performed historically, e.g. "VIP customers respond best
    to early-access drops, not discounts."
    """
    __tablename__ = "audience_segments"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:          Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    segment:           Mapped[str]       = mapped_column(String(100), nullable=False)
    description:       Mapped[str]       = mapped_column(Text, nullable=False, default="")
    campaign_success:  Mapped[str]       = mapped_column(Text, nullable=False, default="")
    updated_at:        Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ContentPerformance(Base):
    __tablename__ = "content_performance"

    id:                   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:             Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    scheduled_content_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("scheduled_content.id"), nullable=True)
    platform:             Mapped[str]       = mapped_column(String(50), nullable=False)
    engagement:           Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    ctr:                  Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    conversion:           Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    roas:                 Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at:          Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# Finance Agent — operational + AI-generated financial intelligence.
# Expense is operational (dashboard/seed-populated, read-only from the
# agent's perspective — same role as Inventory's Supplier/Warehouse), plus
# record_expense lets the agent log a confirmed cost mid-run. FinancialReport
# /FinancialForecast/FinancialInsight/BudgetRecommendation/RiskAssessment
# are AI-output tables, written only by this agent.
# ══════════════════════════════════════════════════════════════════════════════

class Expense(Base):
    __tablename__ = "expenses"

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:     Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    category:     Mapped[str]       = mapped_column(String(50), nullable=False)  # marketing|shipping|software|salaries|warehouse|utilities|packaging|other
    description:  Mapped[str]       = mapped_column(String(500), nullable=False, default="")
    amount:       Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    recurring:    Mapped[bool]      = mapped_column(Boolean, nullable=False, default=False)
    incurred_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at:   Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinancialReport(Base):
    __tablename__ = "financial_reports"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    period:     Mapped[str]       = mapped_column(String(50), nullable=False, default="last_30_days")
    summary:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    revenue:    Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    expenses:   Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    profit:     Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    margin:     Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)  # percent
    kpis:       Mapped[dict]      = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinancialForecast(Base):
    __tablename__ = "financial_forecasts"

    id:                 Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:           Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    forecast_date:      Mapped[date]      = mapped_column(Date, nullable=False)
    forecast_days:      Mapped[int]       = mapped_column(Integer, nullable=False, default=30)
    cash_today:         Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    predicted_cash:     Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    predicted_revenue:  Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    predicted_expenses: Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    risk:               Mapped[str]       = mapped_column(String(20), nullable=False, default="low")  # low|medium|high|critical
    confidence:         Mapped[float]     = mapped_column(Float, nullable=False, default=0.5)
    created_at:         Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinancialInsight(Base):
    __tablename__ = "financial_insights"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:   Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    category:   Mapped[str]       = mapped_column(String(50), nullable=False, default="profitability")  # profitability|cashflow|expense|budget|risk
    severity:   Mapped[str]       = mapped_column(String(20), nullable=False, default="low")
    message:    Mapped[str]       = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float]     = mapped_column(Float, nullable=False, default=0.5)
    created_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BudgetRecommendation(Base):
    __tablename__ = "budget_recommendations"

    id:                 Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:           Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    department:         Mapped[str]       = mapped_column(String(100), nullable=False)  # marketing|inventory|operations|...
    current_budget:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_budget: Mapped[float]     = mapped_column(Float, nullable=False, default=0.0)
    reason:             Mapped[str]       = mapped_column(Text, nullable=False, default="")
    created_at:         Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id:       Mapped[str]       = mapped_column(String(100), ForeignKey("brands.brand_id"), nullable=False, index=True)
    risk:           Mapped[str]       = mapped_column(Text, nullable=False, default="")
    severity:       Mapped[str]       = mapped_column(String(20), nullable=False, default="low")  # low|medium|high|critical
    related_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str]       = mapped_column(Text, nullable=False, default="")
    resolved:       Mapped[bool]      = mapped_column(Boolean, nullable=False, default=False)
    created_at:     Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)