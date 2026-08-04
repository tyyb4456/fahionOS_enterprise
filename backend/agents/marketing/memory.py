"""
RAG over brand marketing/brand-voice documents + this agent's own run
notes, backed by the same Chroma instance already in docker-compose.yml.

Mirrors agents/inventory/memory.py and agents/sales/memory.py exactly —
same on-demand-tool pattern, same optional-infra fallback behavior — just
pointed at Marketing Agent collections:

  marketing_policies_{brand_id} — ingested from Brand Guidelines.pdf, Brand
                                   Voice.pdf, Marketing SOP.pdf, Content
                                   Rules.pdf, Campaign Strategy.pdf, etc. via
                                   api/routers/policy_documents.py (agent=
                                   "marketing"), which parses + chunks
                                   uploads and calls ingest_policy_chunks
                                   below.
  marketing_memory_{brand_id}   — short notes this agent writes about its
                                   own runs (e.g. "Reels outperform static
                                   images 34% on this account — lead with
                                   video") — the semantic index over the
                                   same rows db/crud_marketing.py's
                                   save_agent_memory keeps in Postgres.

Chroma is optional infrastructure: if it's unreachable we log a warning and
return an empty list rather than failing the whole agent run.

Per instructions: the design doc's "Step 3 — RAG Knowledge" is implemented
here as on-demand TOOLS the ReAct loop calls when it decides it needs
brand-voice or past-campaign context (see agents/marketing/tools.py
::retrieve_policy / search_agent_memory) — NOT a forced pre-fetch node in
agents/marketing/graph.py. Same reasoning the other two agents already use:
a targeted retrieve_policy("tone for a discount-led campaign") call once
the agent is actually about to write copy beats a canned pre-fetch every
run, and skips the round-trip entirely on runs where brand-voice context
doesn't end up mattering.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

logger = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

_client = None


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return _client


def _policy_collection(brand_id: str):
    return _get_client().get_or_create_collection(f"marketing_policies_{brand_id}")


def _memory_collection(brand_id: str):
    return _get_client().get_or_create_collection(f"marketing_memory_{brand_id}")


async def retrieve_policies(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            col = _policy_collection(brand_id)
            if col.count() == 0:
                return []
            res = col.query(query_texts=[query], n_results=k)
            return res.get("documents", [[]])[0]
        except Exception:
            logger.warning("Marketing policy RAG unavailable, continuing without it", exc_info=True)
            return []

    return await asyncio.to_thread(_query)


async def ingest_policy_chunks(brand_id: str, chunks: list[str], source: str, document_id: str) -> int:
    """
    Add pre-chunked policy text to a brand's marketing policy collection.
    Called from api/routers/policy_documents.py after a file is uploaded
    and parsed with agent="marketing".
    """
    def _add() -> int:
        col = _policy_collection(brand_id)
        ids = [f"{document_id}-{i}" for i in range(len(chunks))]
        metadatas = [{"source": source, "document_id": document_id} for _ in chunks]
        col.add(documents=chunks, ids=ids, metadatas=metadatas)
        return len(chunks)

    return await asyncio.to_thread(_add)


async def delete_policy_document(brand_id: str, document_id: str) -> None:
    def _delete() -> None:
        try:
            col = _policy_collection(brand_id)
            col.delete(where={"document_id": document_id})
        except Exception:
            logger.warning("Failed to delete marketing policy document %s from Chroma", document_id, exc_info=True)

    await asyncio.to_thread(_delete)


async def retrieve_memory(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            col = _memory_collection(brand_id)
            if col.count() == 0:
                return []
            res = col.query(query_texts=[query], n_results=k)
            return res.get("documents", [[]])[0]
        except Exception:
            logger.warning("Marketing memory RAG unavailable, continuing without it", exc_info=True)
            return []

    return await asyncio.to_thread(_query)


async def store_memory(brand_id: str, content: str, kind: str = "run_summary") -> None:
    def _add() -> None:
        try:
            col = _memory_collection(brand_id)
            col.add(documents=[content], ids=[uuid.uuid4().hex], metadatas=[{"kind": kind}])
        except Exception:
            logger.warning("Failed to write marketing agent memory to Chroma", exc_info=True)

    await asyncio.to_thread(_add)
