"""
Research Agent — LangGraph pipeline.

Same shape as agents/finance/graph.py (the closest architectural precedent
— an agent whose "operational" actions are internal records, not external
system writes):
    build_context   (Step 1 — read Postgres: catalog summary, Sales/
                      Inventory/Marketing agents' outputs, this agent's
                      own recent trends/opportunities)
        -> reason           (Steps 2-4 — ReAct loop; tools = live external
                              web data via research-mcp (web_search,
                              fetch_page_content, google_trends_search,
                              news_search, check_competitor_price), a
                              read-only shopify-mcp catalog subset, internal
                              lookups/scoring/LLM-analysis tools, RAG
                              (brand strategy + past-run notes), and
                              conditional operational writes
                              (create_product_opportunity,
                              record_competitor_analysis,
                              record_pricing_insight), all called on demand)
        -> extract_decision (Step 5/6 — condense the transcript into the
                              structured ResearchDecision: trends + insights,
                              the routine per-run analytical output)
        -> persist          (Step 7 — write trends/insights + execution log
                              + memory)

RAG note: same as every other agent in this codebase — retrieval is NOT a
forced pre-fetch node. It's the retrieve_policy / search_agent_memory tools
in agents/research/tools.py, backed by agents/research/memory.py's Chroma
collections, called only when the ReAct loop decides it needs brand-fit or
past-run context. See agents/research/memory.py for the full reasoning.

Operational note: create_product_opportunity, record_competitor_analysis,
and record_pricing_insight write real rows mid-loop, conditionally — same
pattern as Finance's record_expense/create_budget_recommendation/
assess_financial_risk — rather than being part of the always-written
persist_node output. This agent never calls another agent directly (no
agent does, in this architecture); cross-domain follow-ups go through
next_actions for the Supervisor to route, same as Sales/Finance.
"""
from __future__ import annotations

import logging
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
from db import crud_research as crud
from db.session import AsyncSessionLocal

from .mcp_client import get_research_web_tools, get_shopify_tools_for_research
from .output_schema import ResearchDecision
from .prompt import SYSTEM_PROMPT, build_task_prompt
from .state import ResearchPipelineState
from .tools import build_internal_tools


# ══════════════════════════════════════════════════════════════════════════════
# Nodes
# ══════════════════════════════════════════════════════════════════════════════

def _category_from_task(task_obj: Any) -> str | None:
    if isinstance(task_obj, dict):
        return task_obj.get("category")
    return None


async def build_context_node(state: ResearchPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[ResearchAgent] Building business context for brand_id=%s", brand_id)
    category = _category_from_task(state.get("task", {}))
    async with AsyncSessionLocal() as session:
        context = await crud.get_business_context(session, brand_id, category=category)
    return {"context": context}


async def reasoning_node(state: ResearchPipelineState) -> dict:
    brand_id = state["brand_id"]
    logger.info("[ResearchAgent] Running reasoning node for brand_id=%s", brand_id)

    shopify_tools = scope_tools_to_brand(await get_shopify_tools_for_research(), brand_id)
    web_tools = await get_research_web_tools()  # public data — never brand_id-scoped
    internal_tools = build_internal_tools(brand_id)
    tools = [*shopify_tools, *web_tools, *internal_tools]

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

    logger.info("[ResearchAgent] Reasoning node finished for brand_id=%s. Tools used: %s", brand_id, tools_used)
    return {"messages": result["messages"], "tools_used": tools_used}


async def extract_decision_node(state: ResearchPipelineState) -> dict:
    """Condense the ReAct transcript into the structured decision object."""
    logger.info("[ResearchAgent] Extracting structured decision for brand_id=%s", state["brand_id"])
    model = init_chat_model("google_genai:gemini-3.6-flash").with_structured_output(ResearchDecision)

    transcript = "\n".join(
        f"{getattr(m, 'type', 'message')}: {m.content}"
        for m in state.get("messages", [])
        if getattr(m, "content", None)
    )

    decision: ResearchDecision = await model.ainvoke(
        "Based on this analysis and its tool-call results, produce the final structured "
        "research decision. In actions_executed, list only things that actually happened "
        "(a tool call succeeded — e.g. a product opportunity or competitor analysis was "
        "actually recorded) — not things merely proposed:\n\n" + transcript
    )

    logger.info("[ResearchAgent] Decision extracted for brand_id=%s: summary=%s", state["brand_id"], decision.summary[:100] if decision.summary else "")
    return {
        "trends": [t.model_dump() for t in decision.trends],
        "insights": [i.model_dump() for i in decision.insights],
        "actions_executed": decision.actions_executed,
        "summary": decision.summary,
        "confidence": decision.confidence,
        "next_actions": decision.next_actions,
    }


async def persist_node(state: ResearchPipelineState) -> dict:
    brand_id = state["brand_id"]
    trends = state.get("trends", [])
    insights = state.get("insights", [])
    summary = state.get("summary", "")

    logger.info("[ResearchAgent] Persisting outputs for brand_id=%s (trends=%d, insights=%d)", brand_id, len(trends), len(insights))
    async with AsyncSessionLocal() as session:
        if trends:
            await crud.save_trends(session, brand_id, trends)
        if insights:
            await crud.save_research_insights(session, brand_id, insights)
        if summary:
            await crud.save_agent_memory(session, brand_id, "research_agent", summary, kind="run_summary")
        await session.commit()

    db_updates = []
    if trends:
        db_updates.append(f"market_trends: +{len(trends)}")
    if insights:
        db_updates.append(f"research_insights: +{len(insights)}")

    return {"status": "completed", "db_updates": db_updates}


# ══════════════════════════════════════════════════════════════════════════════
# Graph assembly
# ══════════════════════════════════════════════════════════════════════════════

def build_research_graph():
    graph = StateGraph(ResearchPipelineState)
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


_research_graph = None


def get_research_graph():
    global _research_graph
    if _research_graph is None:
        _research_graph = build_research_graph()
    return _research_graph


async def run_research_agent(brand_id: str, task: dict) -> dict[str, Any]:
    """
    Entry point. `task` matches the design doc's supervisor input, e.g.:
        {"task_type": "market_research", "category": "hoodies", "region": "Pakistan"}
    or:
        {"task_type": "competitor_analysis", "competitors": ["Brand A", "Brand B"]}
    or:
        {"task_type": "trend_monitoring"}

    Returns the structured object handed back to the supervisor.
    """
    start = time.perf_counter()
    logger.info("[ResearchAgent] Starting agent run for brand_id=%s, task=%s", brand_id, task)
    graph = get_research_graph()
    initial_state: ResearchPipelineState = {
        "brand_id": brand_id,
        "task": task,
        "messages": [],
        "status": "running",
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("[ResearchAgent] Run failed for brand_id=%s after %.1f ms", brand_id, duration_ms)
        async with AsyncSessionLocal() as session:
            await crud.log_execution(
                session, brand_id, "research_agent", task.get("task_type", "unknown"),
                status="failed", duration_ms=duration_ms, tools_used=[], token_usage={},
                summary=str(exc),
            )
            await session.commit()
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("[ResearchAgent] Run completed successfully for brand_id=%s in %.1f ms", brand_id, duration_ms)
    async with AsyncSessionLocal() as session:
        await crud.log_execution(
            session, brand_id, "research_agent", task.get("task_type", "unknown"),
            status="completed", duration_ms=duration_ms,
            tools_used=final_state.get("tools_used", []), token_usage={},
            summary=final_state.get("summary", ""),
        )
        await session.commit()

    return {
        "status": "completed",
        "summary": final_state.get("summary", ""),
        "trends": final_state.get("trends", []),
        "insights": final_state.get("insights", []),
        "actions_executed": final_state.get("actions_executed", []),
        "db_updates": final_state.get("db_updates", []),
        "confidence": final_state.get("confidence", 0.0),
        "next_actions": final_state.get("next_actions", []),
        "duration_ms": round(duration_ms, 1),
    }



research_agent = CompiledSubAgent(
    name="research_agent",
    description=(
        "Market intelligence agent — the brand's Head of Market Intelligence. Monitors the "
        "OUTSIDE world, not internal operations: trending products/styles/colors, competitor "
        "products/pricing/promotions, Google search demand, fashion/industry news, and customer "
        "sentiment from reviews and public discussion. Cross-checks findings against our own "
        "catalog, sales, and inventory data so it never proposes something we already sell. "
        "OPERATIONAL (in the same sense as Finance): it can formally record product opportunities, "
        "competitor analyses, and pricing intelligence — visible immediately on the dashboard — and "
        "can alert the brand owner for urgent findings. It does NOT publish content, change prices, "
        "or place orders itself; those stay with Marketing/Sales/Inventory — surface next_actions "
        "for the Supervisor to route. IMPORTANT DATA LIMIT: no official Instagram/TikTok trend API "
        "access exists in this environment — social/platform trend claims come from public web "
        "search and news, not direct platform scraping; it says so rather than overclaiming. "
        "Delegate for anything about market trends, competitors, product opportunities, pricing vs "
        "competitors, or customer sentiment from outside the brand's own data (market_research, "
        "competitor_analysis, trend_monitoring, pricing_intelligence, product_opportunity_scan). "
        "Include category/region/competitor names in the task description when relevant."
    ),
    runnable=get_research_graph()
)