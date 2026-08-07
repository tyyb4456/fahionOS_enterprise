"""
Loads a read-only subset of shopify-mcp (payment/order reconciliation +
product cost cross-check) and meta-mcp (ad spend, for ROI) for the Finance
Agent's ReAct loop. Finance never writes to Shopify or Meta directly — it
advises and records its own numbers — so only read tools are allowed here,
same filtering pattern as agents/inventory/mcp_client.py and
agents/sales/mcp_client.py.
"""
import logging
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")
META_MCP_URL = os.getenv("META_MCP_URL", "http://localhost:8002/mcp")

_ALLOWED_TOOL_NAMES = {
    # shopify-mcp — payment/order reconciliation + cost cross-check
    "get_payment_summary",
    "get_recent_orders",
    "get_returns",
    "list_products",
    # meta-mcp — ad spend, for ROI/budget review
    "get_ad_account_summary",
    "list_ad_campaigns",
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


async def get_finance_tools() -> list:
    """Fetch the combined shopify-mcp + meta-mcp read-only tools this
    agent is allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_TOOL_NAMES]