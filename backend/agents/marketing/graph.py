"""
Marketing Agent — LangGraph pipeline.

Same shape as agents/inventory/graph.py and agents/sales/graph.py:
    build_context   (Step 1 — read Postgres: products, Sales/Inventory
                      Agent outputs, customer segments, past campaigns,
                      marketing calendar)
        -> reason           (Steps 2-4 — ReAct loop; tools = live
                              Shopify/Meta data via shopify-mcp + meta-mcp,
                              plus internal analytics/creative/scheduling
                              tools, all called on demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured MarketingDecision)
        -> persist          (Step 7 — write campaigns/content plan/
                              insights/audience notes + execution log +
                              memory)

RAG note: same as Inventory/Sales — retrieval is NOT a forced pre-step/
node. It's the retrieve_policy / search_agent_memory tools in
agents/marketing/tools.py, backed by agents/marketing/memory.py's Chroma
collections, called only when the ReAct loop decides it needs brand-voice
or past-campaign context.

Operational note: unlike a pure analysis agent, this agent's tools include
real external actions (publish_instagram_post, create_ad_campaign, ...)
that execute live inside the reasoning loop — same pattern as Inventory's
set_inventory_level and Sales' create_discount_code. A human-approval /
execution-policy layer in front of the riskier of these is planned (see
the design doc's "Execution Policy Layer") but intentionally not built
yet — this agent runs fully autonomously for now.
"""
from __future__ import annotations
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

from langgraph.graph import END, StateGraph
from deepagents import CompiledSubAgent, create_deep_agent
from langchain_mistralai import ChatMistralAI
from langchain.chat_models import init_chat_model

from agents.common.tool_scoping import scope_tools_to_brand
from db import crud_marketing as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_marketing_tools
from .output_schema import MarketingDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .state import MarketingPipelineState
from .tools import build_internal_tools


# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

async def build_context_node(state: MarketingPipelineState) -> dict:
    logger.info("[MarketingAgent] Building business context for brand_id=%s", state["brand_id"])
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, state["brand_id"])
    return {"context": context}


async def reasoning_node(state: MarketingPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[MarketingAgent] Running reasoning node for brand_id=%s", brand_id)

    live_tools = scope_tools_to_brand(await get_marketing_tools(), brand_id)
    internal_tools = build_internal_tools(brand_id)
    tools = [*live_tools, *internal_tools]

    model = ChatMistralAI(
        model="mistral-medium-3-5",
        temperature=0,
        model_kwargs={"reasoning_effort": "high"},
    )

    agent = create_deep_agent(model, tools)

    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        task_input = getattr(last_msg, "content", str(last_msg))
    else:
        task_input = state.get("task", {})

    task_prompt = build_task_prompt(task_input, state.get("context", {}))
    result = await agent.ainvoke({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ]
    })

    tools_used = sorted({
        call["name"]
        for message in result["messages"]
        for call in (getattr(message, "tool_calls", None) or [])
    })

    logger.info("[MarketingAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: MarketingPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[MarketingAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(MarketingDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: MarketingDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "marketing decision. In actions_executed, list only things that actually happened "
        "(a tool call succeeded) — not things merely proposed:\n\n" + transcript
    )

    logger.info("[MarketingAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    return {
        "campaigns": [c.model_dump() for c in decision.campaigns],
        "content": [c.model_dump() for c in decision.content],
        "audience_recommendations": [a.model_dump() for a in decision.audience_recommendations],
        "insights": [i.model_dump() for i in decision.insights],
        "actions_executed": decision.actions_executed,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: MarketingPipelineState) -> dict:
    brand_id = state["brand_id"]
    campaigns = state.get("campaigns", [])
    insights = state.get("insights", [])
    audience_recommendations = state.get("audience_recommendations", [])
    summary = state.get("summary", "")

    topics = sorted({c.get("goal", "") for c in campaigns if c.get("goal")})
    platforms = sorted({c.get("platform", "") for c in campaigns if c.get("platform")})

    logger.info("[MarketingAgent] Persisting outputs for brand_id=%s (campaigns=%d, insights=%d, audience_recs=%d)", brand_id, len(campaigns), len(insights), len(audience_recommendations))
    async with AsyncSessionLocal() as session:
        campaign_ids = await crud.save_campaigns(session, brand_id, campaigns)
        if topics or platforms:
            await crud.save_content_plan(session, brand_id, topics, platforms)
        if insights:
            await crud.save_marketing_insights(session, brand_id, insights)
        if audience_recommendations:
            await crud.save_audience_recommendations(session, brand_id, audience_recommendations)
        if summary:
            await crud.save_agent_memory(session, brand_id, "marketing_agent", summary, kind="run_summary")
        await session.commit()

    db_updates = []
    if campaign_ids:
        db_updates.append(f"marketing_campaigns: +{len(campaign_ids)}")
    if insights:
        db_updates.append(f"marketing_insights: +{len(insights)}")
    if audience_recommendations:
        db_updates.append(f"audience_segments: upserted {len(audience_recommendations)}")

    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_marketing_graph():
    graph = StateGraph(MarketingPipelineState)
    graph.add_node("build_context", build_context_node)
    graph.add_node("reason", reasoning_node)
    graph.add_node("extract_decision", extract_decision_node)
    graph.add_node("persist", persist_node)

    graph.set_entry_point("build_context")
    graph.add_edge("build_context", "reason")
    graph.add_edge("reason", "extract_decision")
    graph.add_edge("extract_decision", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_marketing_graph = None


def get_marketing_graph():
    global _marketing_graph
    if _marketing_graph is None:
        _marketing_graph = build_marketing_graph()
    return _marketing_graph


async def run_marketing_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor input, e.g.:
        {"task_type": "plan_marketing", "objective": "Increase hoodie sales",
         "budget": "medium", "timeline": "7_days"}
    or:
        {"task_type": "daily_content"}
    or:
        {"task_type": "campaign_analysis"}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    logger.info("[MarketingAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
    graph = get_marketing_graph()
    initial_state: MarketingPipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("[MarketingAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "marketing_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[MarketingAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "marketing_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "campaigns": final_state.get("campaigns", []),
        "content": final_state.get("content", []),
        "audience_recommendations": final_state.get("audience_recommendations", []),
        "insights": final_state.get("insights", []),
        "actions_executed": final_state.get("actions_executed", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



marketing_agent = CompiledSubAgent(
    name="marketing_agent",
    description=(
        "Marketing & growth agent — the brand's Chief Marketing Officer. Plans campaigns, ranks target audiences "
        "from real customer segments, picks best posting times, and generates on-brand copy (social captions + "
        "hashtags, emails, SMS). Reads the Sales & Inventory agents' outputs (insights, alerts, segments) and "
        "checks stock so it never promotes out-of-stock items. "
        "OPERATIONAL: it can publish Instagram posts, create/pause/resume Meta Ads campaigns, adjust ad budgets, "
        "and schedule content for auto-publish — it launches campaigns, not just plans them — and can alert the "
        "brand owner. "
        "Delegate for anything about campaigns, ads, ad spend, social/Instagram content, audience targeting, "
        "promotions, or growth (plan_marketing, daily_content, campaign_analysis, launch_campaign, "
        "audience_analysis). Include the objective/goal in the task description, plus budget and timeline when "
        "relevant."
    ),
    runnable=get_marketing_graph()
)