"""
Loads research-mcp's tools (public web/market data — no per-brand
credentials, so these are NOT brand_id-scoped) plus a read-only shopify-mcp
subset (product catalog cross-reference — "do we already sell this?",
scoped to brand_id the same way every other agent's Shopify tools are).
Same client pattern as agents/inventory/mcp_client.py etc.
"""
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")
RESEARCH_MCP_URL = os.getenv("RESEARCH_MCP_URL", "http://localhost:8003/mcp")

_ALLOWED_SHOPIFY_TOOL_NAMES = {
    "list_products",
    "get_product_by_sku",
    "calculate_sales_velocity",
}

_ALLOWED_RESEARCH_TOOL_NAMES = {
    "web_search",
    "fetch_page_content",
    "google_trends_search",
    "news_search",
    "check_competitor_price",
}

_client: MultiServerMCPClient | None = None


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient({
            "shopify":  {"url": SHOPIFY_MCP_URL, "transport": "streamable_http"},
            "research": {"url": RESEARCH_MCP_URL, "transport": "streamable_http"},
        })
    return _client


async def get_shopify_tools_for_research() -> list:
    """The brand_id-scoped subset — bind/strip brand_id via
    scope_tools_to_brand in graph.py, same as every other agent."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_SHOPIFY_TOOL_NAMES]


async def get_research_web_tools() -> list:
    """research-mcp tools — public data, no brand_id parameter, never scoped."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_RESEARCH_TOOL_NAMES]