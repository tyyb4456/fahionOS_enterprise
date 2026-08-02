"""
Generic brand_id scoping for MCP-exposed StructuredTools.

The shopify-mcp server (and any future shared MCP server) is used by every
agent, so each of its tools takes `brand_id` as an explicit first parameter
(see mcp_servers/shopify_server/server.py). We don't want the LLM filling
that in itself — a prompt injection buried in a product description or
return note could otherwise steer a tool call at another tenant's store.
Instead we bind the current run's brand_id in a closure and strip the
parameter from the schema the model actually sees.

This has nothing agent-specific in it — every agent that consumes shared
MCP tools (Inventory, Sales, ...) should scope through this same function
rather than each rolling its own copy.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import create_model


def scope_tools_to_brand(tools: list[StructuredTool], brand_id: str) -> list[StructuredTool]:
    scoped: list[StructuredTool] = []
    for t in tools:
        fields = getattr(t.args_schema, "model_fields", {}) if t.args_schema else {}
        if "brand_id" not in fields:
            scoped.append(t)
            continue
        scoped.append(_bind_brand_id(t, brand_id, fields))
    return scoped


def _bind_brand_id(tool: StructuredTool, brand_id: str, fields: dict[str, Any]) -> StructuredTool:
    remaining = {name: (f.annotation, f) for name, f in fields.items() if name != "brand_id"}
    new_args_schema = create_model(f"{tool.name}_ScopedArgs", **remaining)  # type: ignore[call-overload]

    original_coroutine = tool.coroutine
    original_func = tool.func

    async def _scoped_coroutine(**kwargs: Any) -> Any:
        if original_coroutine is not None:
            return await original_coroutine(brand_id=brand_id, **kwargs)
        return original_func(brand_id=brand_id, **kwargs)  # type: ignore[misc]

    return StructuredTool.from_function(
        name=tool.name,
        description=tool.description,
        args_schema=new_args_schema,
        coroutine=_scoped_coroutine,
    )