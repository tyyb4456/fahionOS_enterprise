"""
Loads a read-only subset of shopify-mcp (product context — what's being
sourced) plus the full supplier-mcp tool set (marketplace search + courier
tracking simulations) for the Supplier Agent's ReAct loop. Same client
pattern as agents/inventory/mcp_client.py, agents/sales/mcp_client.py,
agents/finance/mcp_client.py.

Direct supplier outreach (RFQ/negotiation messages) and the actual
purchase_orders / supplier_quotes / shipment_tracking writes are internal
tools (agents/supplier/tools.py), not MCP — see that module's docstring.
"""
import logging
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")
SUPPLIER_MCP_URL = os.getenv("SUPPLIER_MCP_URL", "http://localhost:8003/mcp")

_ALLOWED_TOOL_NAMES = {
    # shopify-mcp — read-only subset (know what's being sourced)
    "list_products",
    "get_product_by_sku",
    "calculate_sales_velocity",
    # supplier-mcp — full set (this agent's external-facing execution surface)
    "search_marketplace_suppliers",
    "track_shipment",
}

_client: MultiServerMCPClient | None = None


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient({
            "shopify":  {"url": SHOPIFY_MCP_URL, "transport": "streamable_http"},
            "supplier": {"url": SUPPLIER_MCP_URL, "transport": "streamable_http"},
        })
    return _client


async def get_supplier_mcp_tools() -> list:
    """Fetch the combined shopify-mcp (read-only subset) + supplier-mcp
    (full set) tools this agent is allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_TOOL_NAMES]