"""
FashionOS Deep Agent — Runtime Singletons
============================================
Per-process singletons (Redis store, Redis checkpointer, per-brand agent
cache) and the agent factory itself. Split out from supervisor.py so both
supervisor.py (chat/stream_chat) and conversations.py (message replay) can
depend on this without importing each other — avoids circular imports.

Note: no MCP clients are built here. The deep agent never talks to
Shopify/Meta/Instagram directly — that only happens inside the real LangGraph
pipeline (agents/supervisor.py), reached exclusively via start_agent_analysis
(deep_agents/tools/pipeline_tools.py). The old SHOPIFY_MCP_URL / SOCIAL_MCP_URL
/ TRENDS_MCP_URL / ADS_MCP_URL constants and the HuggingFaceEndpoint/
ChatHuggingFace model experiment are gone — the latter was dead code anyway
(shadowed by `from deep_agents.load_model import llm` before it was ever used).
"""

import asyncio
import logging
import os
from pathlib import Path

from typing import Any

from deepagents import DeepAgentState, FilesystemPermission, create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend, FilesystemBackend
from dotenv import load_dotenv
from langgraph.store.redis.aio import AsyncRedisStore
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from deep_agent.memory import ensure_brand_seeded
from deep_agent.prompts import build_prompt
from deep_agent.load_model import mistral

from agents.inventory.graph import inventory_agent
from agents.sales.graph import sales_agent
from agents.marketing.graph import marketing_agent

logger = logging.getLogger(__name__)
load_dotenv()

REDIS_URL  = os.getenv("REDIS_URL", "redis://localhost:6379")
BASE_DIR   = Path(__file__).parent.resolve()
SKILLS_DIR = BASE_DIR / "skills"


class FashionOSAgentState(DeepAgentState, total=False):
    """
    Supervisor state schema = DeepAgentState + brand identity.

    DeepAgents' SubAgentMiddleware forwards the parent's full state (minus a
    few excluded keys) into each CompiledSubAgent run. The inventory/sales/
    marketing graphs read `state["brand_id"]` (and `state.get("task")`) on
    their very first node, so without `brand_id` in the supervisor's schema
    delegation crashed with `KeyError: 'brand_id'` the instant the main agent
    called a subagent — before any pipeline node ran. Declaring the key here
    makes it flow: API -> supervisor state -> subagent state.
    """
    brand_id: str
    task: dict[str, Any]


# ── Singletons ────────────────────────────────────────────────────────────────

_store: AsyncRedisStore | None = None

async def get_store() -> AsyncRedisStore:
    global _store
    if _store is None:
        try:
            candidate = AsyncRedisStore(redis_url=REDIS_URL)
            await candidate.setup()     # if this throws, _store stays None — next request retries clean
            _store = candidate
            logger.info("[Store] AsyncRedisStore ready (index created)")
        except Exception:
            logger.exception("[Store] Failed to initialize AsyncRedisStore")
            raise
    return _store


_checkpointer: AsyncRedisSaver | None = None

async def get_checkpointer() -> AsyncRedisSaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = AsyncRedisSaver(redis_url=REDIS_URL)
        # No custom msgpack allowlist needed — every tool in the current
        # architecture (start_agent_analysis, check_agent_analysis_status,
        # get_db_tools()) returns plain dicts/lists, and LangChain message
        # types already have first-class serde support. The old allowlist
        # existed only for the now-deleted subagents' Pydantic response
        # schemas (InventoryAnalysis, TrendAnalysis, etc.) flowing directly
        # into message history.
        await _checkpointer.asetup()
        logger.info("AsyncRedisSaver checkpointer ready")
    return _checkpointer


# ── Per-brand agent cache ──────────────────────────────────────────────────────

_agent_cache: dict[str, object] = {}


async def build_supervisor(brand_id: str, brand_name: str):
    """
    Builds one deep agent instance for a brand: DB tools + pipeline tools
    (start_agent_analysis, check_agent_analysis_status), backed by Redis
    memory (/memories/AGENTS.md) and a read-only virtual /skills/ filesystem.
    """
    store, checkpointer = await asyncio.gather(get_store(), get_checkpointer())

    await ensure_brand_seeded(brand_id, brand_name, store)

    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/memories/": StoreBackend(namespace=lambda rt: (brand_id,)),
            # "/skills/":   FilesystemBackend(root_dir=str(SKILLS_DIR), virtual_mode=True),
        },
    )

    agent = create_deep_agent(
        name          = f"fashionos-{brand_id}",
        model         = mistral,
        system_prompt = build_prompt(brand_id, brand_name),
        subagents     = [inventory_agent, sales_agent, marketing_agent],
        backend       = backend,
        store         = store,
        memory        = ["/memories/AGENTS.md"],
        # skills        = ["/skills/"],
        checkpointer  = checkpointer,
        state_schema  = FashionOSAgentState,
    )
    return agent


async def get_cached_agent(brand_id: str, brand_name: str):
    if brand_id not in _agent_cache:
        agent = await build_supervisor(brand_id, brand_name)
        _agent_cache[brand_id] = agent
        logger.info("Built and cached agent for brand=%s", brand_id)
    return _agent_cache[brand_id]