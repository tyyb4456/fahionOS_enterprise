"""
Loads the shared shopify-mcp server's tools for the Sales Agent's ReAct
loop. Same server, same client pattern as agents/inventory/mcp_client.py.

The Sales Agent reads broadly (orders, returns, velocity, price rules,
abandoned checkouts) but the only Shopify WRITE tool it's allowed is
create_discount_code — a scoped, reversible promo action ("recommends,
doesn't act" used to mean no write tools at all; now that this agent is
operational, discount creation is the one write action squarely in its own
domain — update_product_price/set_inventory_level stay with Pricing/
Inventory).
"""
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")

_ALLOWED_TOOL_NAMES = {
    "list_products",
    "get_product_by_sku",
    "get_recent_orders",
    "get_returns",
    "calculate_sales_velocity",
    "get_price_rules",
    "get_abandoned_checkouts",
    "create_discount_code",
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
    """Fetch shopify-mcp's tool set, filtered to what the Sales Agent is
    allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_TOOL_NAMES]
