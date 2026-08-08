"""
FashionOS Deep Agent Supervisor — Entry Point
================================================
Thin orchestrator. All actual logic now lives in:
  deep_agents/memory.py          — AGENTS.md long-term memory seeding
  deep_agents/prompt.py         — system prompt
  deep_agents/runtime.py         — singletons (store, checkpointer, agent cache) + agent factory
  deep_agents/conversations.py   — conversation metadata CRUD + message replay
  deep_agents/streaming.py       — chat() / stream_chat() + tool-result persistence

This file exists so api/routers/chat.py's existing imports
(`from deep_agents.supervisor import ...`) keep working unchanged — nothing
in that router needed to change for this split.

Architecture summary:
  SHORT-TERM: automatic via LangGraph + thread_id (brand_id:session_id scoped).
  LONG-TERM:  /memories/AGENTS.md, StoreBackend namespaced per brand_id.
  EPHEMERAL:  StateBackend() for /workspace/ scratch, gone after conversation.
"""

from deep_agent.runtime import get_cached_agent
from deep_agent.streaming import chat, stream_chat, PERSISTABLE_TOOLS

from deep_agent.conversations import (
    save_conversation_meta,
    list_conversations,
    delete_conversation,
    get_thread_messages,
)

__all__ = [
    "chat",
    "stream_chat",
    "save_conversation_meta",
    "list_conversations",
    "delete_conversation",
    "get_thread_messages",
    "get_cached_agent",
    "PERSISTABLE_TOOLS",
]