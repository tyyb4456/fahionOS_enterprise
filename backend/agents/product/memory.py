"""
RAG over brand strategy/design documents (Brand Strategy.pdf, Design
Guidelines.pdf, Target Customer.pdf, Pricing Philosophy.pdf, past
Collection Specs.pdf) + this agent's own run notes, backed by the same
Chroma instance already in docker-compose.yml — accessed through
langchain_chroma.Chroma (see agents/common/vector_store.py), with
embeddings from a shared HuggingFace Inference API client
(google/embeddinggemma-300m by default).

Mirrors agents/research/memory.py (and inventory's/sales'/marketing's/
finance's/supplier's) exactly — same on-demand-tool pattern, same
optional-infra fallback behavior — just pointed at Product Agent
collections so its chunks never mix with the other six domains':

  product_policies_{brand_id} — ingested from Brand Strategy.pdf, Design
                                 Guidelines.pdf, Target Customer.pdf,
                                 Pricing Philosophy.pdf, past Collection
                                 Specs.pdf, etc. via
                                 api/routers/policy_documents.py (agent=
                                 "product"). This is what keeps a proposal
                                 on-brand — e.g. "premium minimal
                                 streetwear" ruling out a neon cartoon
                                 T-shirt no matter how well it's trending.
  product_memory_{brand_id}   — short notes this agent writes about its
                                 own runs (e.g. "customers prefer neutral
                                 colors", "limited drops generate higher
                                 urgency") — the semantic index over the
                                 same rows db/crud_product.py's
                                 save_agent_memory keeps in Postgres.

Chroma (and the HF embedding call) is optional infrastructure: if either
is unreachable, we log a warning and return an empty list rather than
failing the whole agent run.

Per instructions: retrieval is an on-demand TOOL the ReAct loop calls when
it decides it needs brand-fit or past-run context (see
agents/product/tools.py::retrieve_policy / search_agent_memory) — NOT a
forced pre-fetch node in agents/product/graph.py. Same reasoning every
other agent in this codebase already uses.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from agents.common.vector_store import get_chroma_collection

logger = logging.getLogger(__name__)


def _policy_store(brand_id: str):
    return get_chroma_collection(f"product_policies_{brand_id}")


def _memory_store(brand_id: str):
    return get_chroma_collection(f"product_memory_{brand_id}")


async def retrieve_policies(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            store = _policy_store(brand_id)
            if store._collection.count() == 0:
                return []
            docs = store.similarity_search(query, k=k)
            return [d.page_content for d in docs]
        except Exception:
            logger.warning("Product policy RAG unavailable, continuing without it", exc_info=True)
            return []

    return await asyncio.to_thread(_query)


async def ingest_policy_chunks(brand_id: str, chunks: list[str], source: str, document_id: str) -> int:
    """Called from api/routers/policy_documents.py after a file is
    uploaded and parsed with agent="product"."""
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
            logger.warning("Failed to delete product policy document %s from Chroma", document_id, exc_info=True)

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
            logger.warning("Product memory RAG unavailable, continuing without it", exc_info=True)
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
            logger.warning("Failed to write product agent memory to Chroma", exc_info=True)

    await asyncio.to_thread(_add)