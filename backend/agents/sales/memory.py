"""
RAG over brand business/sales policy documents + this agent's own run
notes, backed by the same Chroma instance already in docker-compose.yml —
accessed through langchain_chroma.Chroma (see agents/common/vector_store.py)
so ingestion/retrieval go through LangChain's Document / similarity_search
interface, with embeddings coming from a shared HuggingFace Inference API
client (google/embeddinggemma-300m by default).

Mirrors agents/inventory/memory.py exactly — same on-demand-tool pattern,
same optional-infra fallback behavior — just pointed at Sales Agent
collections instead of Inventory's, so the two domains never mix chunks:

  sales_policies_{brand_id}  — ingested from Pricing Strategy.pdf, Sales
                                SOP.pdf, Promotion Policy.pdf, business
                                goals / target KPI docs, etc. via
                                api/routers/policy_documents.py (agent=
                                "sales"), which parses + chunks uploads and
                                calls ingest_policy_chunks below.
  sales_memory_{brand_id}    — short notes this agent writes about its own
                                runs (e.g. "Eid campaign lifted revenue
                                62%, reuse the playbook") — the semantic
                                index over the same rows db/crud_sales.py's
                                save_agent_memory keeps in Postgres.

Chroma (and the HF embedding call) is optional infrastructure: if either
is unreachable, we log a warning and return an empty list rather than
failing the whole agent run.

Per design: retrieval is an on-demand TOOL the ReAct loop calls when it
decides it needs policy or past-run context (see agents/sales/tools.py) —
NOT a forced pre-fetch node in agents/sales/graph.py. A blind pre-fetch
runs one fixed query every run regardless of whether it ends up mattering;
a targeted retrieve_policy("minimum gross margin policy") call once the
agent has actually seen a margin-relevant number beats a canned query
every time, and skips the round-trip entirely on runs where policy
context doesn't end up being needed.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from agents.common.vector_store import get_chroma_collection

logger = logging.getLogger(__name__)


def _policy_store(brand_id: str):
    return get_chroma_collection(f"sales_policies_{brand_id}")


def _memory_store(brand_id: str):
    return get_chroma_collection(f"sales_memory_{brand_id}")


async def retrieve_policies(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            store = _policy_store(brand_id)
            if store._collection.count() == 0:
                return []
            docs = store.similarity_search(query, k=k)
            return [d.page_content for d in docs]
        except Exception:
            logger.warning("Sales policy RAG unavailable, continuing without it", exc_info=True)
            return []

    return await asyncio.to_thread(_query)


async def ingest_policy_chunks(brand_id: str, chunks: list[str], source: str, document_id: str) -> int:
    """
    Add pre-chunked policy text to a brand's sales policy collection.
    Called from api/routers/policy_documents.py after a file is uploaded
    and parsed with agent="sales".
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
            logger.warning("Failed to delete sales policy document %s from Chroma", document_id, exc_info=True)

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
            logger.warning("Sales memory RAG unavailable, continuing without it", exc_info=True)
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
            logger.warning("Failed to write sales agent memory to Chroma", exc_info=True)

    await asyncio.to_thread(_add)