"""
RAG over brand business/sales policy documents + this agent's own run
notes, backed by the same Chroma instance already in docker-compose.yml.

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

Chroma is optional infrastructure: if it's unreachable we log a warning and
return an empty list rather than failing the whole agent run.

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
    return _get_client().get_or_create_collection(f"sales_policies_{brand_id}")


def _memory_collection(brand_id: str):
    return _get_client().get_or_create_collection(f"sales_memory_{brand_id}")


async def retrieve_policies(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            col = _policy_collection(brand_id)
            if col.count() == 0:
                return []
            res = col.query(query_texts=[query], n_results=k)
            return res.get("documents", [[]])[0]
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
            logger.warning("Failed to delete sales policy document %s from Chroma", document_id, exc_info=True)

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
            logger.warning("Sales memory RAG unavailable, continuing without it", exc_info=True)
            return []

    return await asyncio.to_thread(_query)


async def store_memory(brand_id: str, content: str, kind: str = "run_summary") -> None:
    def _add() -> None:
        try:
            col = _memory_collection(brand_id)
            col.add(documents=[content], ids=[uuid.uuid4().hex], metadatas=[{"kind": kind}])
        except Exception:
            logger.warning("Failed to write sales agent memory to Chroma", exc_info=True)

    await asyncio.to_thread(_add)