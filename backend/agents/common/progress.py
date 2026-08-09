"""
Shared streaming-progress helpers for subagent graphs.

Emits custom stream events (via langgraph's StreamWriter) so the chat UI can
track each subagent's progress live: which pipeline node it is on and which
tool it is calling. The events surface through the parent deep-agent astream
as {"type": "custom", "ns": [...], "data": {...}} and are forwarded by
deep_agent/streaming.py with a `source` label.

Event shapes emitted here:
    {"type": "progress", "stage": "<node>",  "status": "started"|"done"|"error", "message": "..."}
    {"type": "tool",     "name": "<tool>",   "status": "started"|"done"|"error", "message": "..."}
"""

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_stream_writer


def emit(event: dict) -> None:
    """Emit a custom event. No-op outside an active stream (null writer)."""
    writer = get_stream_writer()
    writer(event)


def progress(stage: str, status: str, message: str = "") -> None:
    """Announce a pipeline node stage transition."""
    emit({"type": "progress", "stage": stage, "status": status, "message": message})


def _tool_name(request) -> str:
    if hasattr(request, "tool_call"):
        tc = request.tool_call
        if isinstance(tc, dict):
            return tc.get("name") or "tool"
        return getattr(tc, "name", None) or "tool"
    return getattr(request, "name", "tool")


class AnnounceToolCalls(AgentMiddleware):
    """Emit a custom stream event before/after every tool call in a reason loop."""

    async def awrap_tool_call(self, request, handler):
        name = _tool_name(request)
        writer = get_stream_writer()
        writer({"type": "tool", "name": name, "status": "started", "message": f"Running {name}"})
        try:
            result = await handler(request)
            writer({"type": "tool", "name": name, "status": "done", "message": f"Finished {name}"})
            return result
        except Exception:
            writer({"type": "tool", "name": name, "status": "error", "message": f"{name} failed"})
            raise

    def wrap_tool_call(self, request, handler):
        name = _tool_name(request)
        writer = get_stream_writer()
        writer({"type": "tool", "name": name, "status": "started", "message": f"Running {name}"})
        try:
            result = handler(request)
            writer({"type": "tool", "name": name, "status": "done", "message": f"Finished {name}"})
            return result
        except Exception:
            writer({"type": "tool", "name": name, "status": "error", "message": f"{name} failed"})
            raise
