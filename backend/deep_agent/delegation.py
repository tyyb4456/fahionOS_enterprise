"""
Structured task delegation for the FashionOS supervisor
=========================================================
deepagents' built-in `task` tool only exposes a string `description` to the
model (`deepagents/middleware/subagents.py` → `TaskToolSchema`), so the
supervisor could never hand a subagent the typed task object that the
standalone pipelines already support, e.g.:

    {"task_type": "forecast_inventory", "forecast_days": 30,
     "priority": "high", "trigger": "manual", "sku": "..."}

This module ships a drop-in replacement for the deepagents `task` tool that:

* adds an optional `task` dict argument to the tool schema, and
* injects it into the subagent's `state["task"]` before invoking its graph,
  while still forwarding everything else (brand_id, parent state, config)
  exactly like deepagents does — so subgraph streaming, reasoning token
  streaming, and the office activity feed are all unchanged.

It is applied at runtime by swapping two module-level symbols in
`deepagents.middleware.subagents` (install()); nothing in the installed
package is edited, so the change survives pip reinstalls and is not scoped
to a frozen `.venv`. install() is idempotent and degrades gracefully: if the
deepagents internals we depend on change shape, we log a warning and the
original string-only behavior is preserved.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
from collections.abc import Generator, Sequence
from typing import Any, cast

from langchain.tools import BaseTool, ToolRuntime
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from langsmith.run_helpers import get_tracing_context, tracing_context
from pydantic import Field

import deepagents.middleware.subagents as _subagent_module
from deepagents.middleware.subagents import (
    TASK_TOOL_DESCRIPTION,
    TaskToolSchema,
    _EXCLUDED_STATE_KEYS,
    _get_subagent_response_format,
    create_sub_agent,
)

logger = logging.getLogger(__name__)


class StructuredTaskSchema(TaskToolSchema):
    """`task` tool input schema, widened with an optional structured payload."""

    task: dict[str, Any] | None = Field(
        default=None,
        description=(
            "OPTIONAL structured task payload (a JSON object). The FashionOS subagents run from "
            "typed task objects, e.g. inventory_agent: "
            '{"task_type": "forecast_inventory", "forecast_days": 30, "priority": "high", '
            '"trigger": "manual", "sku": "..."} (see each subagent\'s task types in its '
            "description). When you have the specifics, populate this with the matching object; "
            "it lands in the subagent's structured task state so its pipeline gets a typed task "
            "(task_type, numeric params, scoping) instead of only free text. ALWAYS also write a "
            "clear `description` summarizing the objective and expected output."
        ),
    )


@contextlib.contextmanager
def _subagent_tracing_context() -> Generator[None, None, None]:
    """Tag subagent runs with `ls_agent_type="subagent"` (mirrors deepagents)."""
    current = get_tracing_context()
    merged_metadata = {**(current.get("metadata") or {}), "ls_agent_type": "subagent"}
    kwargs: dict[str, Any] = {**current, "metadata": merged_metadata}
    with tracing_context(**kwargs):
        yield


def _build_structured_task_tool(  # noqa: C901, PLR0915
    subagents: Sequence[dict[str, Any]],
    task_description: str | None = None,
    *,
    private_state_keys: frozenset[str] = frozenset(),
    state_schema: type | None = None,
) -> BaseTool:
    """Create a `task` tool from subagent specs — same behavior as deepagents'
    `_build_task_tool`, plus an optional structured `task` payload that is
    injected into the subagent's `state["task"]`.
    """

    def _compile_spec(
        spec: dict[str, Any],
        *,
        response_format: Any = None,
    ) -> dict[str, Any]:
        """Compile one raw spec or configure one provided runnable."""
        if "runnable" in spec:
            if response_format is not None:
                msg = f'response_schema cannot be used with compiled subagent "{spec["name"]}"; dynamic schemas require a raw SubAgent spec.'
                raise ValueError(msg)
            compiled = cast("dict[str, Any]", spec)
            runnable = compiled["runnable"].with_config(
                {
                    "metadata": {"lc_agent_name": spec["name"]},
                    "run_name": spec["name"],
                }
            )
            return {
                "name": spec["name"],
                "description": spec["description"],
                "runnable": runnable,
            }
        return {
            "name": spec["name"],
            "description": spec["description"],
            "runnable": create_sub_agent(
                spec,
                state_schema=state_schema,
                response_format=response_format,
            ),
        }

    compiled_subagents = [_compile_spec(spec) for spec in subagents]
    subagents_by_name = {spec["name"]: spec for spec in subagents}

    subagent_graphs: dict[str, Runnable] = {spec["name"]: spec["runnable"] for spec in compiled_subagents}

    subagent_description_str = "\n".join(f"- {s['name']}: {s['description']}" for s in compiled_subagents)

    if task_description is None:
        description = TASK_TOOL_DESCRIPTION.format(available_agents=subagent_description_str)
    elif "{available_agents}" in task_description:
        description = task_description.format(available_agents=subagent_description_str)
    else:
        description = task_description

    def _return_command_with_state_update(result: dict, tool_call_id: str) -> Command:
        if "messages" not in result:
            error_msg = (
                "CompiledSubAgent must return a state containing a 'messages' key. "
                "Custom StateGraphs used with CompiledSubAgent should include 'messages' "
                "in their state schema to communicate results back to the main agent."
            )
            raise ValueError(error_msg)

        # `task` is deliberately excluded from the write-back so a structured
        # payload used by one delegation never leaks into the supervisor's
        # persisted state (and thus into later delegations).
        state_update = {
            k: v
            for k, v in result.items()
            if k not in _EXCLUDED_STATE_KEYS and k not in private_state_keys and k != "task"
        }

        structured = result.get("structured_response")
        if structured is not None:
            if hasattr(structured, "model_dump_json"):
                content: str = structured.model_dump_json()
            elif dataclasses.is_dataclass(structured) and not isinstance(structured, type):
                content = json.dumps(dataclasses.asdict(structured))
            else:
                content = json.dumps(structured)
        else:
            # Walk back to the last AIMessage with non-empty text.
            content = ""
            for msg in reversed(result["messages"]):
                if isinstance(msg, AIMessage):
                    text = msg.text.rstrip() if msg.text else ""
                    if text:
                        content = text
                        break

        return Command(
            update={
                **state_update,
                "messages": [ToolMessage(content, tool_call_id=tool_call_id)],
            }
        )

    def _select_subagent(subagent_type: str, runtime: ToolRuntime) -> Runnable:
        response_format = _get_subagent_response_format(runtime)
        if response_format is not None:
            new_spec = _compile_spec(
                subagents_by_name[subagent_type],
                response_format=response_format,
            )
            return new_spec["runnable"]
        return subagent_graphs[subagent_type]

    def _validate_and_prepare_state(
        subagent_type: str,
        description: str,
        runtime: ToolRuntime,
        task: dict[str, Any] | None,
    ) -> tuple[Runnable, dict]:
        """Prepare state for invocation."""
        subagent = _select_subagent(subagent_type, runtime)
        subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
        subagent_state = {k: v for k, v in subagent_state.items() if k not in private_state_keys}
        # Never let a stale task dict from a previous delegation bleed in.
        subagent_state.pop("task", None)
        subagent_state["messages"] = [HumanMessage(content=description)]
        if task is not None:
            subagent_state["task"] = task
        return subagent, subagent_state

    def task(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
        task: dict[str, Any] | None = None,
    ) -> str | Command:
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed_types}"
        if not runtime.tool_call_id:
            value_error_msg = "Tool call ID is required for subagent invocation"
            raise ValueError(value_error_msg)
        subagent, subagent_state = _validate_and_prepare_state(
            subagent_type,
            description,
            runtime,
            task,
        )
        subagent_config: RunnableConfig = {"configurable": {"ls_agent_type": "subagent"}}
        with _subagent_tracing_context():
            result = subagent.invoke(subagent_state, subagent_config)
        return _return_command_with_state_update(result, runtime.tool_call_id)

    async def atask(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
        task: dict[str, Any] | None = None,
    ) -> str | Command:
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed_types}"
        if not runtime.tool_call_id:
            value_error_msg = "Tool call ID is required for subagent invocation"
            raise ValueError(value_error_msg)
        subagent, subagent_state = _validate_and_prepare_state(
            subagent_type,
            description,
            runtime,
            task,
        )
        subagent_config: RunnableConfig = {"configurable": {"ls_agent_type": "subagent"}}
        with _subagent_tracing_context():
            result = await subagent.ainvoke(subagent_state, subagent_config)
        return _return_command_with_state_update(result, runtime.tool_call_id)

    return StructuredTool.from_function(
        name="task",
        func=task,
        coroutine=atask,
        description=description,
        infer_schema=False,
        args_schema=StructuredTaskSchema,
    )


_installed = False


def install() -> None:
    """Swap deepagents' `task` tool internals for the structured-dict version.

    Idempotent. Degrades gracefully (string-only task tool) if deepagents
    internals drift from what this module expects.
    """
    global _installed
    if _installed:
        return
    mod = _subagent_module
    if not (hasattr(mod, "_build_task_tool") and hasattr(mod, "TaskToolSchema")):
        logger.warning(
            "[Delegation] deepagents internals changed; structured `task` dict delegation unavailable "
            "— keeping default string-only task tool."
        )
        _installed = True
        return
    mod.TaskToolSchema = StructuredTaskSchema
    mod._build_task_tool = _build_structured_task_tool
    _installed = True
    logger.info("[Delegation] Structured task delegation installed — the `task` tool now accepts an optional `task` dict.")