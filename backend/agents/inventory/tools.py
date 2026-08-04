"""
Internal tools for the Inventory Agent's ReAct loop — everything that isn't
a live Shopify call (those come from shopify-mcp, see mcp_client.py). Each
factory below binds `brand_id` in a closure so the LLM never has to supply
it — same reasoning as tool_scoping.py.

create_purchase_order and notify_supplier are the two tools that make this
agent operational rather than advisory: they make real, immediate changes
(a purchase_orders row, an outbound WhatsApp/email) mid-ReAct-loop, the
same way shopify-mcp's set_inventory_level does — not deferred to
persist_node, which only ever wrote the AI's own audit-trail records.
"""
from __future__ import annotations

from datetime import date, timedelta

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.common.notify_tools import make_notify_brand_owner_tool
from db import crud_inventory as crud
from db.session import AsyncSessionLocal
from notifications.dispatch import send_email, send_whatsapp

from . import memory as rag
from .forecasting import forecast_sku_demand as _forecast


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_forecast_tool(brand_id),
        _make_supplier_tool(brand_id),
        _make_warehouse_tool(brand_id),
        _make_create_po_tool(brand_id),
        _make_notify_supplier_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
        make_notify_brand_owner_tool(brand_id, agent_name="Inventory Agent"),
    ]


# ── forecast_sku_demand ──────────────────────────────────────────────────

class _ForecastArgs(BaseModel):
    sku: str = Field(description="SKU to forecast.")
    forecast_days: int = Field(default=30, description="Days to project forward.")


def _make_forecast_tool(brand_id: str) -> StructuredTool:
    async def _run(sku: str, forecast_days: int = 30) -> dict:
        async with AsyncSessionLocal() as session:
            current_stock, history = await crud.get_sku_sales_history(session, brand_id, sku)
        if current_stock is None:
            return {"error": f"SKU '{sku}' not found in synced product data."}
        result = _forecast(current_stock, history, forecast_days=forecast_days)
        result["sku"] = sku
        result["current_stock"] = current_stock
        return result

    return StructuredTool.from_function(
        name="forecast_sku_demand",
        description=(
            "Project demand and days-until-stockout for a SKU using its recent "
            "daily sales history from our database. Use this instead of eyeballing "
            "trends yourself."
        ),
        args_schema=_ForecastArgs,
        coroutine=_run,
    )


# ── get_supplier_details ─────────────────────────────────────────────────

class _SupplierArgs(BaseModel):
    supplier_name: str = Field(description="Supplier name (fuzzy match) or supplier_id.")


def _make_supplier_tool(brand_id: str) -> StructuredTool:
    async def _run(supplier_name: str) -> dict:
        async with AsyncSessionLocal() as session:
            supplier = await crud.find_supplier(session, brand_id, supplier_name)
        return supplier or {"error": f"No supplier matching '{supplier_name}'."}

    return StructuredTool.from_function(
        name="get_supplier_details",
        description="Look up lead time, minimum order quantity, price terms, and reliability score for a supplier.",
        args_schema=_SupplierArgs,
        coroutine=_run,
    )


# ── get_warehouse_capacity ───────────────────────────────────────────────

class _WarehouseArgs(BaseModel):
    warehouse_name: str = Field(default="", description="Warehouse name. Leave blank to list all warehouses.")


def _make_warehouse_tool(brand_id: str) -> StructuredTool:
    async def _run(warehouse_name: str = "") -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.get_warehouses(session, brand_id, name_filter=warehouse_name or None)

    return StructuredTool.from_function(
        name="get_warehouse_capacity",
        description="Check current capacity and utilization for one or all warehouses.",
        args_schema=_WarehouseArgs,
        coroutine=_run,
    )


# ── create_purchase_order (operational write) ────────────────────────────

class _CreatePOArgs(BaseModel):
    sku: str = Field(description="SKU to reorder.")
    supplier_id: str = Field(description="Supplier's supplier_id, from get_supplier_details.")
    quantity: int = Field(description="Units to order.")
    reason: str = Field(default="", description="Why this quantity/timing — stored on the PO.")


def _make_create_po_tool(brand_id: str) -> StructuredTool:
    async def _run(sku: str, supplier_id: str, quantity: int, reason: str = "") -> dict:
        async with AsyncSessionLocal() as session:
            supplier = await crud.get_supplier_by_id(session, brand_id, supplier_id)
            if not supplier:
                return {"error": f"No supplier with id '{supplier_id}' on file."}

            expected_delivery = date.today() + timedelta(days=supplier.get("lead_time_days", 14))
            po = await crud.create_purchase_order(
                session, brand_id, sku=sku, supplier_id=supplier_id,
                quantity=quantity, expected_delivery=expected_delivery,
            )
            await session.commit()
        po["reason"] = reason
        return po

    return StructuredTool.from_function(
        name="create_purchase_order",
        description=(
            "Actually place a reorder — creates a real purchase_orders record with an "
            "expected delivery date based on the supplier's lead time. This is a real "
            "action, not a suggestion: only call it once you've confirmed the SKU, "
            "quantity, and supplier with forecast_sku_demand / get_supplier_details."
        ),
        args_schema=_CreatePOArgs,
        coroutine=_run,
    )


# ── notify_supplier (operational write — outbound message) ───────────────

class _NotifySupplierArgs(BaseModel):
    supplier_name: str = Field(description="Supplier name (fuzzy match) or supplier_id.")
    message: str = Field(description="The order/reorder message to send — e.g. the supplier_message you drafted.")
    channel: str = Field(default="both", description="'whatsapp', 'email', or 'both'.")


def _make_notify_supplier_tool(brand_id: str) -> StructuredTool:
    async def _run(supplier_name: str, message: str, channel: str = "both") -> dict:
        async with AsyncSessionLocal() as session:
            supplier = await crud.find_supplier(session, brand_id, supplier_name)
        if not supplier:
            return {"error": f"No supplier matching '{supplier_name}'."}

        results = []
        if channel in ("whatsapp", "both") and supplier.get("contact_whatsapp"):
            results.append(await send_whatsapp(supplier["contact_whatsapp"], message))
        if channel in ("email", "both") and supplier.get("contact_email"):
            results.append(await send_email(supplier["contact_email"], f"Purchase order — {supplier['name']}", message))
        if not results:
            return {"error": f"No contact info on file for supplier '{supplier['name']}'."}
        return {"sent": any(r.get("sent") for r in results), "supplier": supplier["name"], "results": results}

    return StructuredTool.from_function(
        name="notify_supplier",
        description="Send the supplier your order/reorder message via WhatsApp and/or email. Call after create_purchase_order.",
        args_schema=_NotifySupplierArgs,
        coroutine=_run,
    )


# ── retrieve_policy (RAG) ────────────────────────────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'reorder threshold for outerwear'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description=(
            "Search brand-specific inventory policy documents (reorder rules, "
            "supplier contracts, warehouse SOPs) for guidance relevant to your query."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )


# ── search_agent_memory ──────────────────────────────────────────────────

def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description=(
            "Search notes this agent kept from previous runs (e.g. past forecast "
            "misses around Eid) for anything relevant to the current task."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )
