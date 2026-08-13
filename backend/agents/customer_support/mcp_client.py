"""
Loads a read-only-plus-write subset of shopify-mcp (order lookup + real
refund/cancel writes), the Instagram-DM subset of meta-mcp, and the full
customer-support-mcp tool set (simulated courier tracking) for the
Customer Support Agent's ReAct loop. Same client pattern as every other
agent's mcp_client.py.
"""
import logging
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "http://localhost:8001/mcp")
META_MCP_URL = os.getenv("META_MCP_URL", "http://localhost:8002/mcp")
CUSTOMER_SUPPORT_MCP_URL = os.getenv("CUSTOMER_SUPPORT_MCP_URL", "http://localhost:8005/mcp")

_ALLOWED_TOOL_NAMES = {
    # shopify-mcp — order lookup + the two real writes this agent owns
    "get_order_by_id",
    "get_recent_orders",
    "get_returns",
    "create_refund",
    "cancel_order",
    # meta-mcp — Instagram DM reply (this agent's Instagram execution surface)
    "send_instagram_dm",
    # customer-support-mcp — simulated courier delivery-status tracking
    "check_delivery_status",
}

_client: MultiServerMCPClient | None = None


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient({
            "shopify":          {"url": SHOPIFY_MCP_URL, "transport": "streamable_http"},
            "meta":              {"url": META_MCP_URL, "transport": "streamable_http"},
            "customer_support":  {"url": CUSTOMER_SUPPORT_MCP_URL, "transport": "streamable_http"},
        })
    return _client


async def get_customer_support_tools() -> list:
    """Fetch the combined shopify-mcp (order + refund/cancel) + meta-mcp
    (Instagram DM) + customer-support-mcp (courier tracking) tools this
    agent is allowed to call."""
    tools = await _get_client().get_tools()
    return [t for t in tools if t.name in _ALLOWED_TOOL_NAMES]