"""
Loads the shared shopify-mcp server's tools for the Sales Agent's ReAct
loop. Same server, same client pattern as agents/inventory/mcp_client.py.

Unlike Inventory, the Sales Agent gets a filtered, READ-ONLY subset — it
"recommends, doesn't act" (see system prompt), so it has no business
calling update_product_price / set_inventory_level / create_restock_
recommendation even though those tools exist on the shared server.
"""
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")

_READ_TOOL_NAMES = {
    "list_products",
    "get_product_by_sku",
    "get_recent_orders",
    "get_returns",
    "calculate_sales_velocity",
    "get_price_rules",
    "get_abandoned_checkouts",
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


async def get_shopify_read_tools() -> list:
    """Fetch shopify-mcp's tool set, filtered to the read-only subset the
    Sales Agent is allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _READ_TOOL_NAMES]