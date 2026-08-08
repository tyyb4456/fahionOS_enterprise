"""
Internal tools for the Supplier Agent's ReAct loop — everything that isn't
a live "external" call (marketplace search / shipment tracking, which come
from supplier-mcp — see mcp_client.py) or a live Shopify read (shopify-mcp,
also mcp_client.py). Each factory below binds `brand_id` in a closure so
the LLM never has to supply it — same reasoning as tool_scoping.py.

This agent is operational, not advisory: request_quotes, create_purchase_order,
send_supplier_message, update_shipment_status, record_negotiation, and
update_supplier_score all make real, immediate changes mid-ReAct-loop —
same pattern as Inventory's create_purchase_order / notify_supplier.

check_purchase_affordability is deliberately read-only: it reuses Finance's
own deterministic evaluate_purchase_order() function + crud_finance's cash
lookup directly (not a live call into the Finance Agent's LLM loop — agents
don't invoke each other, only the Supervisor delegates across domains; see
deep_agent/prompts.py) so Supplier can get a same-domain-math affordability
read before recommending a spend, the same way Marketing reads Sales/
Inventory's stored outputs instead of recomputing them.
"""
from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.common.notify_tools import make_notify_brand_owner_tool
from db import crud_supplier as crud
from db.session import AsyncSessionLocal
from notifications.dispatch import send_email, send_whatsapp

from . import memory as rag

logger = logging.getLogger(__name__)


def build_internal_tools(brand_id: str) -> list[StructuredTool]:
    return [
        _make_find_suppliers_tool(brand_id),
        _make_supplier_details_tool(brand_id),
        _make_request_quotes_tool(brand_id),
        _make_compare_quotes_tool(brand_id),
        _make_create_po_tool(brand_id),
        _make_affordability_tool(brand_id),
        _make_send_supplier_message_tool(brand_id),
        _make_update_shipment_tool(brand_id),
        _make_record_negotiation_tool(brand_id),
        _make_update_supplier_score_tool(brand_id),
        _make_policy_tool(brand_id),
        _make_memory_tool(brand_id),
        make_notify_brand_owner_tool(brand_id, agent_name="Supplier Agent"),
    ]


# ── find_suppliers ────────────────────────────────────────────────────────

class _FindSuppliersArgs(BaseModel):
    query: str = Field(default="", description="Fuzzy match against supplier name. Leave blank to list all on-file suppliers.")


def _make_find_suppliers_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str = "") -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.find_suppliers(session, brand_id, query=query)

    return StructuredTool.from_function(
        name="find_suppliers",
        description=(
            "Search this brand's own approved/on-file suppliers. Try this before "
            "search_marketplace_suppliers (an external, simulated marketplace search) — "
            "an existing relationship usually beats a cold one."
        ),
        args_schema=_FindSuppliersArgs,
        coroutine=_run,
    )


# ── get_supplier_details ─────────────────────────────────────────────────

class _SupplierIdArgs(BaseModel):
    supplier_id: str = Field(description="supplier_id from find_suppliers.")


def _make_supplier_details_tool(brand_id: str) -> StructuredTool:
    async def _run(supplier_id: str) -> dict:
        async with AsyncSessionLocal() as session:
            supplier = await crud.get_supplier_by_id(session, brand_id, supplier_id)
        return supplier or {"error": f"No supplier with id '{supplier_id}' on file."}

    return StructuredTool.from_function(
        name="get_supplier_details",
        description="Full detail on one supplier — lead time, MOQ, reliability/quality scores, contact info.",
        args_schema=_SupplierIdArgs,
        coroutine=_run,
    )


# ── request_quotes ────────────────────────────────────────────────────────

class _RequestQuoteArgs(BaseModel):
    supplier_id: str = Field(description="supplier_id to request a quote from.")
    sku: str = Field(description="SKU being sourced.")
    quantity: int = Field(description="Units needed.")
    reference_unit_price: Optional[float] = Field(
        default=None,
        description="A known reference unit price (e.g. the product's on-file cost_price) to anchor the estimate. Omit if unknown.",
    )


def _make_request_quotes_tool(brand_id: str) -> StructuredTool:
    async def _run(supplier_id: str, sku: str, quantity: int, reference_unit_price: Optional[float] = None) -> dict:
        async with AsyncSessionLocal() as session:
            if reference_unit_price is None:
                reference_unit_price = await crud.get_reference_cost_price(session, brand_id, sku)
            result = await crud.create_quote_estimate(session, brand_id, supplier_id, sku, quantity, reference_unit_price)
            if "error" not in result:
                await session.commit()
        return result

    return StructuredTool.from_function(
        name="request_quotes",
        description=(
            "Request pricing from an on-file supplier for a SKU/quantity and store the quote. "
            "NOTE: this environment has no live supplier-portal/RFQ-response integration, so the "
            "returned unit_price is a deterministic ESTIMATE from the supplier's on-file MOQ/lead-time "
            "and any reference cost you supply — say so if you report a number from this to the founder, "
            "and prefer real numbers (e.g. an on-file cost_price) over guessing a reference price."
        ),
        args_schema=_RequestQuoteArgs,
        coroutine=_run,
    )


# ── compare_quotes ────────────────────────────────────────────────────────

class _CompareQuotesArgs(BaseModel):
    sku: str = Field(description="SKU to compare quotes for.")


def _make_compare_quotes_tool(brand_id: str) -> StructuredTool:
    async def _run(sku: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await crud.compare_quotes_for_sku(session, brand_id, sku)

    return StructuredTool.from_function(
        name="compare_quotes",
        description=(
            "Rank all quotes on file for a SKU by a composite score (price, lead time, "
            "reliability, quality) — NOT just cheapest-wins. Call after request_quotes has "
            "collected at least one quote per candidate supplier."
        ),
        args_schema=_CompareQuotesArgs,
        coroutine=_run,
    )


# ── create_purchase_order (operational write) ────────────────────────────

class _CreatePOArgs(BaseModel):
    sku: str = Field(description="SKU to order.")
    supplier_id: str = Field(description="Chosen supplier's supplier_id.")
    quantity: int = Field(description="Units to order.")
    unit_cost: Optional[float] = Field(default=None, description="Agreed unit cost, e.g. from compare_quotes or a negotiation.")
    payment_terms: str = Field(default="", description="e.g. '30% advance, 70% on shipment' — stored on the PO.")


def _make_create_po_tool(brand_id: str) -> StructuredTool:
    async def _run(sku: str, supplier_id: str, quantity: int, unit_cost: Optional[float] = None, payment_terms: str = "") -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.create_purchase_order(session, brand_id, sku, supplier_id, quantity, unit_cost=unit_cost, payment_terms=payment_terms)
            if "error" not in result:
                await session.commit()
        return result

    return StructuredTool.from_function(
        name="create_purchase_order",
        description=(
            "Place a real purchase order — creates a purchase_orders row (expected delivery from the "
            "supplier's lead time) plus an initial shipment-tracking record. Only call this once you've "
            "confirmed the supplier, quantity, and price (via compare_quotes or a negotiation) and, for a "
            "large order, checked check_purchase_affordability."
        ),
        args_schema=_CreatePOArgs,
        coroutine=_run,
    )


# ── check_purchase_affordability (advisory — reuses Finance's own math) ──

class _AffordabilityArgs(BaseModel):
    total_cost: float = Field(description="Total cost of the order you're about to place (unit_cost x quantity).")


def _make_affordability_tool(brand_id: str) -> StructuredTool:
    async def _run(total_cost: float) -> dict:
        from agents.finance import analytics as finance_analytics
        from db import crud_finance

        async with AsyncSessionLocal() as session:
            current_cash, _series = await crud_finance.get_cash_position_and_series(session, brand_id, days=30)

        po_like = {"purchase_order_id": None, "sku": None, "total_cost": total_cost}
        return finance_analytics.evaluate_purchase_order(po_like, current_cash)

    return StructuredTool.from_function(
        name="check_purchase_affordability",
        description=(
            "Advisory affordability check for an order you're about to place, before create_purchase_order — "
            "compares the order's total cost against current cash position using the same math the Finance "
            "Agent uses. Not a live call to Finance's own reasoning; just its cash math, reused directly. "
            "Use for any order that isn't trivially small."
        ),
        args_schema=_AffordabilityArgs,
        coroutine=_run,
    )


# ── send_supplier_message (operational write — outbound message) ─────────

class _SendMessageArgs(BaseModel):
    supplier_id: str = Field(description="supplier_id to message.")
    message: str = Field(description="RFQ, order confirmation, or negotiation message to send.")
    channel: str = Field(default="both", description="'whatsapp', 'email', or 'both'.")
    subject: str = Field(default="Purchase order / procurement message", description="Email subject line, if channel includes email.")


def _make_send_supplier_message_tool(brand_id: str) -> StructuredTool:
    async def _run(supplier_id: str, message: str, channel: str = "both", subject: str = "Purchase order / procurement message") -> dict:
        async with AsyncSessionLocal() as session:
            supplier = await crud.get_supplier_by_id(session, brand_id, supplier_id)
        if not supplier:
            return {"error": f"No supplier with id '{supplier_id}' on file."}

        results = []
        if channel in ("whatsapp", "both") and supplier.get("contact_whatsapp"):
            results.append(await send_whatsapp(supplier["contact_whatsapp"], message))
        if channel in ("email", "both") and supplier.get("contact_email"):
            results.append(await send_email(supplier["contact_email"], subject, message))
        if not results:
            return {"error": f"No contact info on file for supplier '{supplier['name']}'."}
        return {"sent": any(r.get("sent") for r in results), "supplier": supplier["name"], "results": results}

    return StructuredTool.from_function(
        name="send_supplier_message",
        description=(
            "Send a supplier an RFQ, order confirmation, or negotiation message via WhatsApp and/or email. "
            "Use for RFQs before request_quotes, and for confirming a PO after create_purchase_order."
        ),
        args_schema=_SendMessageArgs,
        coroutine=_run,
    )


# ── update_shipment_status (operational write) ────────────────────────────

class _UpdateShipmentArgs(BaseModel):
    purchase_order_id: str = Field(description="The purchase_order_id this shipment update is for.")
    status: str = Field(description="'manufacturing' | 'shipped' | 'in_transit' | 'customs' | 'delivered' | 'delayed'.")
    current_location: Optional[str] = Field(default=None)
    estimated_arrival: Optional[str] = Field(default=None, description="ISO date, e.g. '2026-08-20'.")
    tracking_number: Optional[str] = Field(default=None)
    carrier: Optional[str] = Field(default=None)


def _make_update_shipment_tool(brand_id: str) -> StructuredTool:
    async def _run(
        purchase_order_id: str, status: str, current_location: Optional[str] = None,
        estimated_arrival: Optional[str] = None, tracking_number: Optional[str] = None,
        carrier: Optional[str] = None,
    ) -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.upsert_shipment_status(
                session, brand_id, purchase_order_id, status,
                current_location=current_location, estimated_arrival=estimated_arrival,
                tracking_number=tracking_number, carrier=carrier,
            )
            if "error" not in result:
                await session.commit()

        # A delivery just landed — feed it straight into the supplier's
        # reliability score rather than leaving that as a separate step
        # the agent has to remember to do.
        if "error" not in result and status == "delivered" and result.get("supplier_id") and result.get("delivered_on_time") is not None:
            async with AsyncSessionLocal() as session:
                await crud.update_supplier_score(
                    session, brand_id, result["supplier_id"],
                    delivered_on_time=result["delivered_on_time"],
                    note=f"PO {purchase_order_id} delivered {'on time' if result['delivered_on_time'] else 'late'}.",
                )
                await session.commit()

        return result

    return StructuredTool.from_function(
        name="update_shipment_status",
        description=(
            "Record a shipment status update for an open purchase order — call track_shipment (an external, "
            "simulated courier tracker) first to get the current status/ETA, then persist it here. Marking a "
            "shipment 'delivered' also closes out the purchase order and updates the supplier's reliability score."
        ),
        args_schema=_UpdateShipmentArgs,
        coroutine=_run,
    )


# ── record_negotiation (operational write) ────────────────────────────────

class _NegotiationArgs(BaseModel):
    supplier_id: str = Field(description="supplier_id being negotiated with.")
    sku: Optional[str] = Field(default=None, description="SKU this negotiation concerns, if specific to one.")
    initial_offer: Optional[float] = Field(default=None, description="Supplier's original unit price.")
    counter_offer: Optional[float] = Field(default=None, description="Your counter-offer.")
    final_price: Optional[float] = Field(default=None, description="Agreed price, if settled.")
    result: str = Field(default="ongoing", description="'ongoing' | 'accepted' | 'rejected'.")
    notes: str = Field(default="", description="Strategy and reasoning, for future negotiations with this supplier.")


def _make_record_negotiation_tool(brand_id: str) -> StructuredTool:
    async def _run(
        supplier_id: str, sku: Optional[str] = None, initial_offer: Optional[float] = None,
        counter_offer: Optional[float] = None, final_price: Optional[float] = None,
        result: str = "ongoing", notes: str = "",
    ) -> dict:
        async with AsyncSessionLocal() as session:
            record = await crud.record_negotiation(session, brand_id, supplier_id, sku, initial_offer, counter_offer, final_price, result, notes)
            await session.commit()
        return record

    return StructuredTool.from_function(
        name="record_negotiation",
        description=(
            "Log a negotiation round with a supplier — target/counter/final price and outcome. Builds "
            "procurement history (search_agent_memory) so future negotiations with the same supplier start "
            "from what actually worked last time."
        ),
        args_schema=_NegotiationArgs,
        coroutine=_run,
    )


# ── update_supplier_score (operational write) ─────────────────────────────

class _ScoreArgs(BaseModel):
    supplier_id: str = Field(description="supplier_id to update.")
    delivered_on_time: Optional[bool] = Field(default=None, description="Whether their most recent delivery was on time.")
    quality_issue: Optional[bool] = Field(default=None, description="Whether a quality problem was found in their most recent delivery.")
    note: str = Field(default="", description="What happened — stored as a supplier insight.")


def _make_update_supplier_score_tool(brand_id: str) -> StructuredTool:
    async def _run(supplier_id: str, delivered_on_time: Optional[bool] = None, quality_issue: Optional[bool] = None, note: str = "") -> dict:
        async with AsyncSessionLocal() as session:
            result = await crud.update_supplier_score(session, brand_id, supplier_id, delivered_on_time=delivered_on_time, quality_issue=quality_issue, note=note)
            if "error" not in result:
                await session.commit()
        return result

    return StructuredTool.from_function(
        name="update_supplier_score",
        description=(
            "Manually adjust a supplier's reliability/quality score from an observed outcome not already "
            "captured by update_shipment_status (e.g. a quality complaint, a late reply to an RFQ). Nudges "
            "the score gradually rather than overwriting it."
        ),
        args_schema=_ScoreArgs,
        coroutine=_run,
    )


# ── retrieve_policy / search_agent_memory (RAG) ────────────────────────────

class _QueryArgs(BaseModel):
    query: str = Field(description="What you need to know, e.g. 'Supplier A payment terms' or 'approved supplier list for outerwear'.")


def _make_policy_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_policies(brand_id, query)

    return StructuredTool.from_function(
        name="retrieve_policy",
        description=(
            "Search brand-specific procurement documents (supplier contracts, negotiation rules, approved "
            "supplier list, quality SOP, packaging standards) for guidance relevant to your query."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )


def _make_memory_tool(brand_id: str) -> StructuredTool:
    async def _run(query: str) -> list[str]:
        return await rag.retrieve_memory(brand_id, query)

    return StructuredTool.from_function(
        name="search_agent_memory",
        description=(
            "Search notes this agent kept from previous runs (e.g. 'Supplier A accepts 5% off after a second "
            "counter-offer', 'Supplier C delays during Eid') for anything relevant to the current task."
        ),
        args_schema=_QueryArgs,
        coroutine=_run,
    )