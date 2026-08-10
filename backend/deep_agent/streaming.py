import asyncio
import logging
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

from deep_agent.office_bus import office_bus
from deep_agent.runtime import get_cached_agent

# ── Persistence constants ───────────────────────────────────────────────────────
# Reused by deep_agent/supervisor.py and api/routers/chat.py.
# Reasoning/tool-result persistence to ChatToolResult lives here so the frontend
# can re-render reasoning + subagent output cards when history is reloaded.
REASONING_SENTINEL = "__reasoning__"
SUBAGENT_SENTINEL = "__subagent__"
PERSISTABLE_TOOLS: set[str] = set()


def strip_id(segment: str) -> str:
    return segment.split(":", 1)[0]


def make_labeler():
    """Fresh state per request — never share these across requests."""
    pending_by_parent = {}
    resolved = {}

    def track_dispatches(ns, node_name, node_data):
        if node_name != "model":
            return
        for msg in node_data.get("messages", []):
            for tc in getattr(msg, "tool_calls", []):
                if tc["name"] == "task":
                    pending_by_parent.setdefault(ns, []).append(
                        tc["args"].get("subagent_type", "subagent")
                    )

    def label_path(ns) -> str:
        if not ns:
            return "main agent"
        path = []
        for i, segment in enumerate(ns):
            prefix, key = ns[:i], ns[: i + 1]
            if segment.startswith("tools:"):
                if key not in resolved:
                    queue = pending_by_parent.get(prefix, [])
                    resolved[key] = queue.pop(0) if queue else "subagent"
                path.append(resolved[key])
            else:
                path.append(strip_id(segment))
        return " > ".join(path)

    return track_dispatches, label_path


def _reasoning_text(value) -> str:
    """Normalize a reasoning payload (string, list of {text}, or None) to text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            s.get("text", "") if isinstance(s, dict) else str(s)
            for s in value
        )
    return str(value) if value else ""


def _extract_reasoning_parts(value: dict) -> list[str]:
    """Pull reasoning out of a provider-specific block (Mistral `thinking`, etc.)."""
    parts = []
    if reasoning := value.get("reasoning"):
        parts.append(_reasoning_text(reasoning))
    thinking = value.get("thinking")
    if thinking:
        items = thinking if isinstance(thinking, list) else [thinking]
        for sub in items:
            if isinstance(sub, dict):
                if sub.get("text"):
                    parts.append(str(sub["text"]))
                elif sub.get("reasoning"):
                    parts.append(_reasoning_text(sub["reasoning"]))
            else:
                parts.append(str(sub))
    return [p for p in parts if p]


def _subagent_key(source: str) -> str:
    """Group a labeled path (e.g. `inventory_agent > subagent`) under its agent."""
    return source.split(" > ", 1)[0]


# ── Office activity feed ───────────────────────────────────────────────────────
# Human-readable labels for graph node names so the Virtual Office page can
# show "Running analysis" instead of a raw graph node id. The actual rich text
# comes from each subagent's emit_progress(...) custom events when available.

NODE_ACTION = {
    "model": "Thinking",
    "build_context": "Reading brand context",
    "reason": "Running analysis",
    "extract_decision": "Structuring output",
    "persist": "Saving results",
    "tool": "Calling tools",
}


def _agent_label(key: str) -> str:
    """inventory_agent -> Inventory"""
    if not key or key == "supervisor":
        return "Supervisor"
    return key.replace("_agent", "").replace("_", " ").strip().title()


def _publish_office(brand_id: str, event: dict) -> None:
    office_bus.publish(brand_id, event)


# ── Persistence (fire-and-forget) ───────────────────────────────────────────────

async def _save_reasoning(
    brand_id: str,
    thread_id: str,
    turn_index: int,
    reasoning_text: str,
) -> None:
    """
    Persist the main agent's reasoning for this turn so the ReasoningBlock
    survives a page reload / switching conversations.
    """
    from db.session import AsyncSessionLocal
    from db.models  import ChatToolResult

    try:
        async with AsyncSessionLocal() as session:
            session.add(ChatToolResult(
                brand_id=brand_id, thread_id=thread_id, turn_index=turn_index,
                label=REASONING_SENTINEL, summary=reasoning_text, data=None,
            ))
            await session.commit()
    except Exception as exc:
        logger.error("Failed to persist reasoning for thread=%s: %s", thread_id, exc)


async def _save_subagent_result(
    brand_id: str,
    thread_id: str,
    turn_index: int,
    source: str,
    content: str,
    reasoning: str,
    seq: int = 0,
) -> None:
    """
    Persist one subagent's streamed output (final answer + its own thinking) so
    the subagent card survives a page reload, not just the live SSE stream.
    """
    from db.session import AsyncSessionLocal
    from db.models  import ChatToolResult

    label = f"{SUBAGENT_SENTINEL}:{source}"
    if seq > 0:
        label = f"{label}#{seq + 1}"

    preview = " ".join(content.split())[:300] or "output"

    try:
        async with AsyncSessionLocal() as session:
            session.add(ChatToolResult(
                brand_id=brand_id, thread_id=thread_id, turn_index=turn_index,
                label=label, summary=preview,
                data={"content": content, "reasoning": reasoning},
            ))
            await session.commit()
    except Exception as exc:
        logger.error("Failed to persist subagent result (%s seq=%d) for thread=%s: %s", source, seq, thread_id, exc)


# ── Non-streaming chat ──────────────────────────────────────────────────────────

async def chat(brand_id: str, brand_name: str, message: str, thread_id: str = "default") -> str:
    logger.info("Non-streaming chat for brand=%s thread=%s", brand_id, thread_id)
    agent         = await get_cached_agent(brand_id, brand_name)
    scoped_thread = f"{brand_id}:{thread_id}"
    config        = {"configurable": {"thread_id": scoped_thread}}

    _publish_office(brand_id, {"type": "run.start", "thread_id": thread_id})
    _publish_office(brand_id, {"type": "supervisor.status", "status": "working", "action": "Received task"})
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": message}], "brand_id": brand_id},
            config=config,
        )
    finally:
        _publish_office(brand_id, {"type": "supervisor.status", "status": "idle", "action": "Standing by"})
        _publish_office(brand_id, {"type": "run.end", "thread_id": thread_id})

    msgs = result.get("messages", [])
    if msgs:
        last = msgs[-1]
        content = getattr(last, "content", None)
        if isinstance(content, list):
            text = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in content
            )
            return text or str(content)
        return str(content) if content is not None else str(last)
    return "No response generated."


# ── Streaming chat ──────────────────────────────────────────────────────────────

async def stream_chat(
    brand_id: str,
    brand_name: str,
    message: str,
    thread_id: str = "default",
) -> AsyncGenerator[dict, None]:
    """
    Yields SSE-ready event dicts:
      {"type": "step",       "source": "...", "node": "..."}
      {"type": "custom",     "source": "...", "data": ...}
      {"type": "reasoning",  "source": "...", "content": "..."}
      {"type": "token",      "source": "...", "content": "..."}
      {"type": "done"}
      {"type": "error", "content": "..."}
    """
    logger.info("Streaming chat for brand=%s thread=%s", brand_id, thread_id)
    agent         = await get_cached_agent(brand_id, brand_name)
    scoped_thread = f"{brand_id}:{thread_id}"
    config        = {"configurable": {"thread_id": scoped_thread}}

    track_dispatches, label_path = make_labeler()

    reasoning_accum  = ""   # main agent thinking for this turn
    subagent_accum: dict[str, dict] = {}   # source -> {"content":..., "reasoning":...}
    subagent_seq:    dict[str, int] = {}

    # turn_index = the assistant-message index this run will land on. A user turn
    # produces exactly one final assistant message (conversations.py collapses
    # intermediate AI tool-call messages), so it equals the number of prior turns,
    # i.e. the number of human messages already in the checkpoint.
    try:
        state         = await agent.aget_state(config)
        existing_msgs = (state.values or {}).get("messages", []) or []
        turn_index    = sum(1 for m in existing_msgs if getattr(m, "type", "") == "human")
    except Exception:
        turn_index = 0

    _publish_office(brand_id, {"type": "run.start", "thread_id": thread_id})
    _publish_office(brand_id, {"type": "supervisor.status", "status": "working", "action": "Received task"})
    main_token_sent = False

    try:
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": message}], "brand_id": brand_id},
            config=config,
            stream_mode=["updates", "messages", "custom"],
            subgraphs=True,
            version="v2",
        ):
            ns = chunk["ns"]
            source = label_path(ns)

            if chunk["type"] == "updates":
                for node_name, node_data in chunk["data"].items():
                    track_dispatches(ns, node_name, node_data)
                    yield {"type": "step", "source": source, "node": node_name}

                    if source == "main agent":
                        _publish_office(brand_id, {
                            "type": "supervisor.status", "status": "working",
                            "node": node_name,
                            "action": NODE_ACTION.get(node_name, node_name.replace("_", " ").title()),
                        })
                        # A `task` tool call means the supervisor is delegating
                        # to a subagent — surface it as a real inter-agent message.
                        if node_name == "model":
                            for msg in node_data.get("messages", []):
                                for tc in getattr(msg, "tool_calls", []):
                                    if tc["name"] == "task":
                                        target = tc["args"].get("subagent_type", "subagent")
                                        _publish_office(brand_id, {
                                            "type": "agent.message", "from": "supervisor",
                                            "to": target, "kind": "task",
                                            "text": f"Task dispatched to {_agent_label(target)}",
                                        })
                                        _publish_office(brand_id, {
                                            "type": "supervisor.status", "status": "working",
                                            "action": f"Delegating to {_agent_label(target)}",
                                        })
                    else:
                        _publish_office(brand_id, {
                            "type": "agent.status", "agent": _subagent_key(source),
                            "status": "working", "node": node_name,
                            "action": NODE_ACTION.get(node_name, node_name.replace("_", " ").title()),
                        })

            elif chunk["type"] == "custom":
                yield {"type": "custom", "source": source, "data": chunk["data"]}

                data = chunk["data"]
                if source == "main agent" or not isinstance(data, dict):
                    continue
                agent = _subagent_key(source)
                if data.get("type") == "progress":
                    stage  = data.get("stage")
                    status = data.get("status")
                    if status == "started":
                        _publish_office(brand_id, {
                            "type": "agent.status", "agent": agent,
                            "status": "working", "node": stage,
                            "action": data.get("message") or NODE_ACTION.get(stage),
                        })
                    elif status == "done" and stage == "persist":
                        _publish_office(brand_id, {
                            "type": "agent.status", "agent": agent,
                            "status": "done", "node": stage,
                            "action": "Finished",
                        })
                        _publish_office(brand_id, {
                            "type": "agent.message", "from": agent, "to": "supervisor",
                            "kind": "reply", "text": f"{_agent_label(agent)} analysis complete",
                        })
                        _publish_office(brand_id, {
                            "type": "supervisor.status", "status": "working",
                            "action": f"Reviewing {_agent_label(agent)}",
                        })
                    elif status == "error":
                        _publish_office(brand_id, {
                            "type": "agent.status", "agent": agent,
                            "status": "error", "node": stage,
                            "action": data.get("message") or "Failed",
                        })
                elif data.get("type") == "tool":
                    _publish_office(brand_id, {
                        "type": "agent.tool", "agent": agent,
                        "tool": data.get("name"), "status": data.get("status", "started"),
                    })

            elif chunk["type"] == "messages":
                token, _metadata = chunk["data"]
                is_main = source == "main agent"

                # Reasoning arrives in several shapes depending on provider:
                #   - standard content_blocks {"type": "reasoning", "reasoning": ...}
                #   - Mistral "thinking" blocks, which content_blocks wraps as
                #     {"type": "non_standard", "value": {"type": "thinking", ...}}
                #   - Ollama-style reasoning_content in additional_kwargs
                # Normalize all of them so reasoning still streams.
                for block in getattr(token, "content_blocks", []):
                    btype = block.get("type") if isinstance(block, dict) else None
                    if btype == "reasoning":
                        text = _reasoning_text(block.get("reasoning"))
                        if text:
                            reasoning_accum += text if is_main else ""
                            if not is_main:
                                acc = subagent_accum.setdefault(_subagent_key(source), {"content": "", "reasoning": ""})
                                acc["reasoning"] += text
                            yield {"type": "reasoning", "source": source, "content": text}
                    elif btype in ("thinking", "non_standard"):
                        value = block.get("value", block) if isinstance(block, dict) else block
                        if isinstance(value, dict):
                            for part in _extract_reasoning_parts(value):
                                reasoning_accum += part if is_main else ""
                                if not is_main:
                                    acc = subagent_accum.setdefault(_subagent_key(source), {"content": "", "reasoning": ""})
                                    acc["reasoning"] += part
                                yield {"type": "reasoning", "source": source, "content": part}
                    elif btype == "text" and block.get("text"):
                        if is_main and not main_token_sent:
                            main_token_sent = True
                            _publish_office(brand_id, {
                                "type": "supervisor.status", "status": "working",
                                "action": "Writing response",
                            })
                        if not is_main:
                            acc = subagent_accum.setdefault(_subagent_key(source), {"content": "", "reasoning": ""})
                            acc["content"] += block["text"]
                        yield {"type": "token", "source": source, "content": block["text"]}

                kw = (getattr(token, "additional_kwargs", {}) or {}).get("reasoning_content")
                if kw:
                    reasoning_accum += str(kw) if is_main else ""
                    if not is_main:
                        acc = subagent_accum.setdefault(_subagent_key(source), {"content": "", "reasoning": ""})
                        acc["reasoning"] += str(kw)
                    yield {"type": "reasoning", "source": source, "content": str(kw)}

    except Exception as exc:
        logger.error("stream_chat failed for thread=%s: %s", thread_id, exc)
        _publish_office(brand_id, {"type": "supervisor.status", "status": "error", "action": "Run failed"})
        yield {"type": "error", "content": str(exc)}

    if reasoning_accum or subagent_accum:
        if reasoning_accum:
            asyncio.ensure_future(_save_reasoning(
                brand_id=brand_id, thread_id=thread_id, turn_index=turn_index,
                reasoning_text=reasoning_accum,
            ))
        for src_key, data in subagent_accum.items():
            seq = subagent_seq.get(src_key, 0)
            subagent_seq[src_key] = seq + 1
            asyncio.ensure_future(_save_subagent_result(
                brand_id=brand_id, thread_id=thread_id, turn_index=turn_index,
                source=src_key, content=data["content"], reasoning=data["reasoning"], seq=seq,
            ))

    _publish_office(brand_id, {"type": "supervisor.status", "status": "idle", "action": "Standing by"})
    _publish_office(brand_id, {"type": "run.end", "thread_id": thread_id})
    yield {"type": "done"}
