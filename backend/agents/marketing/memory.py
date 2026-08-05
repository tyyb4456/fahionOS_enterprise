"""
RAG over brand marketing/brand-voice documents + this agent's own run
notes, backed by the same Chroma instance already in docker-compose.yml —
accessed through langchain_chroma.Chroma (see agents/common/vector_store.py)
so ingestion/retrieval go through LangChain's Document / similarity_search
interface, with embeddings coming from a shared HuggingFace Inference API
client (google/embeddinggemma-300m by default).

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

Chroma (and the HF embedding call) is optional infrastructure: if either
is unreachable, we log a warning and return an empty list rather than
failing the whole agent run.

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
import uuid

from agents.common.vector_store import get_chroma_collection

logger = logging.getLogger(__name__)


def _policy_store(brand_id: str):
    return get_chroma_collection(f"marketing_policies_{brand_id}")


def _memory_store(brand_id: str):
    return get_chroma_collection(f"marketing_memory_{brand_id}")


async def retrieve_policies(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            store = _policy_store(brand_id)
            if store._collection.count() == 0:
                return []
            docs = store.similarity_search(query, k=k)
            return [d.page_content for d in docs]
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
    from langchain_core.documents import Document

    def _add() -> int:
        store = _policy_store(brand_id)
        ids = [f"{document_id}-{i}" for i in range(len(chunks))]
        docs = [
            Document(page_content=chunk, metadata={"source": source, "document_id": document_id})
            for chunk in chunks
        ]
        store.add_documents(docs, ids=ids)
        return len(chunks)

    return await asyncio.to_thread(_add)


async def delete_policy_document(brand_id: str, document_id: str) -> None:
    def _delete() -> None:
        try:
            _policy_store(brand_id).delete(where={"document_id": document_id})
        except Exception:
            logger.warning("Failed to delete marketing policy document %s from Chroma", document_id, exc_info=True)

    await asyncio.to_thread(_delete)


async def retrieve_memory(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            store = _memory_store(brand_id)
            if store._collection.count() == 0:
                return []
            docs = store.similarity_search(query, k=k)
            return [d.page_content for d in docs]
        except Exception:
            logger.warning("Marketing memory RAG unavailable, continuing without it", exc_info=True)
            return []

    return await asyncio.to_thread(_query)


async def store_memory(brand_id: str, content: str, kind: str = "run_summary") -> None:
    from langchain_core.documents import Document

    def _add() -> None:
        try:
            _memory_store(brand_id).add_documents(
                [Document(page_content=content, metadata={"kind": kind})],
                ids=[uuid.uuid4().hex],
            )
        except Exception:
            logger.warning("Failed to write marketing agent memory to Chroma", exc_info=True)

    await asyncio.to_thread(_add)
