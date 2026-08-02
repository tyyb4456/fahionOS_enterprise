"""
Loads the shared shopify-mcp server's tools (list_products, get_recent_orders,
calculate_sales_velocity, update_product_price, ...) as LangChain tools, so
the Inventory Agent's ReAct loop can call live Shopify data alongside its
internal tools (forecasting, supplier/warehouse lookups, RAG).
"""
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")

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
    """Fetch the current tool set exposed by shopify-mcp."""
    return await _get_client().get_tools()
