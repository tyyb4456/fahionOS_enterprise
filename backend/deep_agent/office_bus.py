"""
FashionOS — Virtual Office Activity Bus
========================================
An in-process, per-brand pub/sub hub that fans the deep-agent stream out to
the Virtual AI Office page (/api/v1/office/stream SSE).

Events published by deep_agent/streaming.py:
  {"type": "run.start"}                       — a run began
  {"type": "run.end"}                         — a run finished
  {"type": "supervisor.status", "status", "action"}
  {"type": "agent.status",     "agent", "status", "node", "action"}
  {"type": "agent.tool",       "agent", "tool", "status"}
  {"type": "agent.message",    "from", "to", "kind", "text"}

The bus keeps a rolling per-brand state snapshot (last known supervisor +
agent statuses plus a short activity log) so a freshly-opened office page can
render instantly via GET /api/v1/office/state without waiting for the next run.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


def _initial_state() -> dict:
    return {
        "supervisor": {"status": "idle", "action": "Standing by"},
        "agents": {},
        "activity": deque(maxlen=120),
    }


class OfficeBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._state: dict[str, dict] = defaultdict(_initial_state)

    # ── Subscriber lifecycle ───────────────────────────────────────────────────

    def subscribe(self, brand_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=500)
        self._subscribers[brand_id].append(queue)
        return queue

    def unsubscribe(self, brand_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(brand_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(brand_id, None)

    # ── Publish ────────────────────────────────────────────────────────────────

    def publish(self, brand_id: str, event: dict) -> None:
        event = {**event, "ts": time.time()}
        try:
            self._apply(brand_id, event)
        except Exception:
            logger.exception("office_bus._apply failed for brand=%s", brand_id)

        for queue in self._subscribers.get(brand_id, [])[:]:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest queued event rather than block the publisher.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass

    def _apply(self, brand_id: str, event: dict) -> None:
        st = self._state[brand_id]
        etype = event.get("type")

        if etype == "supervisor.status":
            st["supervisor"] = {
                "status": event.get("status", "idle"),
                "action": event.get("action", ""),
                "updated": event.get("ts"),
            }
        elif etype == "agent.status":
            agent = st["agents"].setdefault(event.get("agent", ""), {})
            agent["status"] = event.get("status", "idle")
            agent["action"] = event.get("action", "")
            if event.get("node"):
                agent["node"] = event["node"]
            agent["updated"] = event.get("ts")
        elif etype == "agent.tool":
            agent = st["agents"].setdefault(event.get("agent", ""), {})
            agent["last_tool"] = event.get("tool")
            agent["last_tool_status"] = event.get("status", "started")

        st["activity"].append(event)

    # ── Snapshot for fresh page loads ──────────────────────────────────────────

    def snapshot(self, brand_id: str) -> dict:
        st = self._state[brand_id]
        return {
            "connected": True,
            "supervisor": dict(st["supervisor"]),
            "agents": {k: dict(v) for k, v in st["agents"].items()},
            "activity": list(st["activity"]),
        }


office_bus = OfficeBus()
