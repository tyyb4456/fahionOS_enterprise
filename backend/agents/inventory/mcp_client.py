"""
Loads the shared shopify-mcp server's tools the Inventory Agent actually
needs (read tools for demand context + the two write tools that make this
agent operational — correcting a stock count and logging a restock
decision). Same client pattern as agents/sales/mcp_client.py.

update_product_price, get_returns, and get_abandoned_checkouts are left out
on purpose — those are Pricing's and Sales' domains respectively, not
Inventory's; scoping down here is the same reasoning as Sales' own
_ALLOWED_TOOL_NAMES filter, just with a couple of write tools included since
Inventory is now allowed to act, not only read.
"""
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")

_ALLOWED_TOOL_NAMES = {
    "list_products",
    "get_product_by_sku",
    "get_recent_orders",
    "calculate_sales_velocity",
    "list_locations",
    "set_inventory_level",
    "create_restock_recommendation",
}

_client: MultiServerMCPClient | None = None


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient({
            "shopify": {
                "url": SHOPIFY_MCP_URL,
                "transport": "streamable_http",
            }
        })
    return _client


async def get_shopify_tools() -> list:
    """Fetch shopify-mcp's tool set, filtered to what the Inventory Agent
    is allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_TOOL_NAMES]
