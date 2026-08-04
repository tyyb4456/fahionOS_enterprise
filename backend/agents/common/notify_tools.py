"""
Shared "notify a human" tool factory — used by every operational agent when
a decision needs to reach the brand owner outside the dashboard (e.g. "I
just paused campaign X because ROAS cratered" or "Revenue dropped 20%,
here's why"). Wraps notifications/dispatch.py the same way
agents/common/tool_scoping.py wraps brand_id binding for MCP tools — one
implementation, every agent reuses it instead of rolling its own.

Inventory's supplier-facing notify_supplier tool is *not* here — it needs a
Supplier lookup (agents/inventory/tools.py + db/crud_inventory.py), a
different data source than the Brand row this factory reads from — but
Inventory can still use make_notify_brand_owner_tool for founder-facing
alerts (e.g. a critical stockout on a bestseller) alongside its own
supplier tool.
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.models import Brand
from db.session import AsyncSessionLocal
from notifications.dispatch import send_email, send_whatsapp


class _NotifyArgs(BaseModel):
    subject: str = Field(description="Short subject/headline for the alert.")
    message: str = Field(description="The message body — be specific and actionable.")
    channel: str = Field(default="both", description="'whatsapp', 'email', or 'both'.")


def make_notify_brand_owner_tool(brand_id: str, agent_name: str) -> StructuredTool:
    async def _run(subject: str, message: str, channel: str = "both") -> dict:
        async with AsyncSessionLocal() as session:
            brand = (await session.execute(
                select(Brand).where(Brand.brand_id == brand_id)
            )).scalar_one_or_none()
        if not brand:
            return {"sent": False, "error": "Brand not found."}

        results = []
        if channel in ("whatsapp", "both") and brand.brand_owner_whatsapp:
            results.append(await send_whatsapp(brand.brand_owner_whatsapp, f"[{agent_name}] {subject}\n\n{message}"))
        if channel in ("email", "both") and brand.brand_owner_email:
            results.append(await send_email(brand.brand_owner_email, f"[FashionOS – {agent_name}] {subject}", message))

        if not results:
            return {"sent": False, "error": "No contact info on file for this brand (brand_owner_whatsapp / brand_owner_email)."}
        return {"sent": any(r.get("sent") for r in results), "results": results}

    return StructuredTool.from_function(
        name="notify_brand_owner",
        description=(
            "Send the brand owner a direct WhatsApp and/or email alert outside the dashboard. "
            "Use for time-sensitive findings (e.g. a stockout risk, a revenue anomaly, a "
            "campaign you just launched or paused) — not for routine, non-urgent updates."
        ),
        args_schema=_NotifyArgs,
        coroutine=_run,
    )
