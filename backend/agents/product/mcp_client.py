"""
Loads a Shopify-mcp subset for the Product Agent — read tools for catalog/
velocity context, plus the write tools that make this agent operational:
create_product, update_product_details, add_product_variant (added to
shopify-mcp alongside the existing Inventory/Sales/Marketing write tools —
same server, no new MCP service needed). Same client pattern as every other
agent's mcp_client.py.

Research-mcp is deliberately NOT wired in here — Product Agent reads
Research's own stored outputs (MarketTrend, ProductOpportunity,
CompetitorAnalysis, via db/crud_product.py) instead of re-querying the web
itself, the same "read another agent's facts, don't recompute them" pattern
Marketing/Finance already use against Sales/Inventory.
"""
import logging
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")

_ALLOWED_TOOL_NAMES = {
    "list_products",
    "get_product_by_sku",
    "calculate_sales_velocity",
    "create_product",
    "update_product_details",
    "add_product_variant",
}

_client: MultiServerMCPClient | None = None


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient({
            "shopify": {"url": SHOPIFY_MCP_URL, "transport": "streamable_http"},
        })
    return _client


async def get_product_tools() -> list:
    """Fetch shopify-mcp's tool set, filtered to what the Product Agent is
    allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_TOOL_NAMES]