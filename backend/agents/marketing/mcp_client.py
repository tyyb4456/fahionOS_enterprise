"""
Loads shopify-mcp (a read-only product/inventory subset — Marketing checks
stock and pricing context but never touches Shopify inventory or price
writes itself) and meta-mcp (Instagram + Meta Ads — the Marketing Agent's
actual execution surface) for the ReAct loop. Same client pattern as
agents/inventory/mcp_client.py and agents/sales/mcp_client.py.
"""
import logging
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")
META_MCP_URL = os.getenv("META_MCP_URL", "http://localhost:8002/mcp")

_ALLOWED_TOOL_NAMES = {
    # shopify-mcp — read-only subset (product context for campaigns/content)
    "list_products",
    "get_product_by_sku",
    "calculate_sales_velocity",
    # meta-mcp — full set (this agent's actual execution surface)
    "get_instagram_account_insights",
    "list_recent_instagram_media",
    "get_instagram_media_insights",
    "publish_instagram_post",
    "get_ad_account_summary",
    "list_ad_campaigns",
    "create_ad_campaign",
    "update_campaign_budget",
    "pause_campaign",
    "resume_campaign",
}

_client: MultiServerMCPClient | None = None


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient({
            "shopify": {"url": SHOPIFY_MCP_URL, "transport": "streamable_http"},
            "meta":    {"url": META_MCP_URL, "transport": "streamable_http"},
        })
    return _client


async def get_marketing_tools() -> list:
    """Fetch the combined shopify-mcp (read-only subset) + meta-mcp (full
    set) tools this agent is allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_TOOL_NAMES]