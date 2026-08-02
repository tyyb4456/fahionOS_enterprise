"""
Backward-compatible re-export — the actual implementation is fully generic
(binds/strips `brand_id` for any StructuredTool list) and now lives in
agents/common/tool_scoping.py so the Sales Agent (and any future agent) can
reuse it instead of duplicating this file. Nothing here is
inventory-specific; this module exists only so `from agents.inventory
.tool_scoping import scope_tools_to_brand` in graph.py keeps working
unchanged.
"""
from agents.common.tool_scoping import scope_tools_to_brand

__all__ = ["scope_tools_to_brand"]