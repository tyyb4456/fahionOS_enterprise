"""
RAG over brand policy documents + this agent's own run notes, backed by
the Chroma instance already in docker-compose.yml — accessed through
langchain_chroma.Chroma (see agents/common/vector_store.py) rather than
the raw chromadb client, so ingestion/retrieval go through LangChain's
Document / similarity_search interface like the rest of the codebase.
Embeddings come from a shared HuggingFace Inference API client
(google/embeddinggemma-300m by default — see backend/test.ipynb for the
exploratory version of this call).

Two collections per brand:
  inventory_policies_{brand_id}  — ingested from Inventory Policy.pdf,
                                    Supplier Contracts.pdf, Warehouse SOP.pdf,
                                    Restocking Rules.pdf, etc. via
                                    api/routers/policy_documents.py, which
                                    parses + chunks uploads and calls
                                    ingest_policy_chunks below.
  inventory_memory_{brand_id}    — short notes this agent writes about its
                                    own runs (see db/crud_inventory.py for
                                    the structured Postgres copy of the same
                                    notes — that's the audit trail, this is
                                    the semantic index over it).

Chroma (and the HF embedding call) is optional infrastructure: if either
is unreachable, we log a warning and return an empty list rather than
failing the whole agent run.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from agents.common.vector_store import get_chroma_collection

logger = logging.getLogger(__name__)


def _policy_store(brand_id: str):
    return get_chroma_collection(f"inventory_policies_{brand_id}")


def _memory_store(brand_id: str):
    return get_chroma_collection(f"inventory_memory_{brand_id}")


async def retrieve_policies(brand_id: str, query: str, k: int = 3) -> list[str]:
    def _query() -> list[str]:
        try:
            store = _policy_store(brand_id)
            if store._collection.count() == 0:
                return []
            docs = store.similarity_search(query, k=k)
            return [d.page_content for d in docs]
        except Exception:
            logger.warning("Policy RAG unavailable, continuing without it", exc_info=True)
            return []

    return await asyncio.to_thread(_query)


async def ingest_policy_chunks(brand_id: str, chunks: list[str], source: str, document_id: str) -> int:
    """
    Add pre-chunked policy text to a brand's policy collection. Called from
    api/routers/policy_documents.py after a file is uploaded and parsed.

    `document_id` tags every chunk so a specific upload can be deleted later
    even if two uploads share a filename — see delete_policy_document.
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
            logger.warning("Failed to delete policy document %s from Chroma", document_id, exc_info=True)

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
            logger.warning("Memory RAG unavailable, continuing without it", exc_info=True)
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
            logger.warning("Failed to write agent memory to Chroma", exc_info=True)

    await asyncio.to_thread(_add)