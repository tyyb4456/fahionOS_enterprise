"""
Internal tools for the Inventory Agent's ReAct loop — everything that isn't
a live Shopify call (those come from shopify-mcp, see mcp_client.py). Each
factory below binds `brand_id` in a closure so the LLM never has to supply
it — same reasoning as tool_scoping.py.
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from db import crud_inventory as crud
from db.session import AsyncSessionLocal

from . import memory as rag
from .forecasting import forecast_sku_demand as _forecast


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_forecast_tool(brand_id),
        _make_supplier_tool(brand_id),
        _make_warehouse_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
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
