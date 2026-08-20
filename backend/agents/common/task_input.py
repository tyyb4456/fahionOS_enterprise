"""Helpers for resolving an agent's incoming task."""

from typing import Any


def resolve_task_input(state: dict) -> Any:
    """Return the task this pipeline run should work from.

    A structured `task` dict (supervisor delegation, scheduler, webhook) wins —
    that is what lets subagents run off typed task objects like
    {"task_type": "forecast_inventory", "forecast_days": 30, "priority": "high"}.
    When none was provided, fall back to the free-text delegation message, then
    to an empty object.
    """
    task = state.get("task")
    if isinstance(task, dict) and task:
        return task
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        return getattr(last_msg, "content", str(last_msg))
    return task or {}