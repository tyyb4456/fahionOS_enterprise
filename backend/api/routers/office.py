"""
FashionOS — Virtual Office API Router
======================================
GET /api/v1/office/state   — current snapshot (supervisor + agents + activity)
GET /api/v1/office/stream  — live SSE activity feed for the brand

Event shape (same dicts stream_chat publishes to the office bus):
  {"type":"snapshot", "data": {...}}               — sent once on connect
  {"type":"run.start"|"run.end", "ts"}
  {"type":"supervisor.status", "status", "action", "ts"}
  {"type":"agent.status", "agent", "status", "node", "action", "ts"}
  {"type":"agent.tool", "agent", "tool", "status", "ts"}
  {"type":"agent.message", "from", "to", "kind", "text", "ts"}
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.auth import get_current_brand
from db.models import Brand
from deep_agent.office_bus import office_bus

router = APIRouter(prefix="/api/v1/office", tags=["office"])

logger = logging.getLogger(__name__)


@router.get("/state")
async def office_state(
    brand: Brand = Depends(get_current_brand),
) -> dict:
    """Snapshot of the brand's last-known office state for instant first paint."""
    return office_bus.snapshot(brand.brand_id)


@router.get("/stream", response_class=StreamingResponse)
async def office_stream(
    brand: Brand = Depends(get_current_brand),
) -> StreamingResponse:
    queue = office_bus.subscribe(brand.brand_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # First paint: replay the live snapshot, then stream new events.
            yield f"data: {json.dumps({'type': 'snapshot', 'data': office_bus.snapshot(brand.brand_id)})}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            office_bus.unsubscribe(brand.brand_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
