"""
Shared Chroma access for every agent's RAG collections (policy docs + each
agent's own run notes) — Inventory, Sales, and Marketing all import
get_chroma_collection() instead of each standing up their own chromadb/
langchain_chroma client + embedding function. One Chroma connection config,
one embedding model, reused across every agent.

Embeddings: HuggingFace Inference API (google/embeddinggemma-300m by
default) via langchain_huggingface.HuggingFaceEndpointEmbeddings — a
*hosted* feature-extraction endpoint, not a locally-loaded model (that
would be HuggingFaceEmbeddings instead). This replaces the previous
behavior where no embedding_function was ever passed to Chroma, so it
silently fell back to its own bundled local default. Matches the model
already validated in backend/test.ipynb.

Vector store access goes through langchain_chroma.Chroma (not the raw
chromadb client) so ingestion/retrieval use LangChain's Document /
similarity_search interface everywhere, instead of raw chromadb calls
duplicated across three files.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "google/embeddinggemma-300m")

_embeddings = None
_collections: dict[str, "Chroma"] = {}


def get_embedding_function():
    """Lazily builds and caches one HuggingFaceEndpointEmbeddings client
    for the whole process — every agent's memory.py shares this instead of
    each constructing its own."""
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEndpointEmbeddings

        if not (os.getenv("HUGGINGFACEHUB_API_TOKEN") or os.getenv("HF_TOKEN")):
            logger.warning(
                "HUGGINGFACEHUB_API_TOKEN / HF_TOKEN not set — HF embedding "
                "calls will fail until one is configured. RAG reads degrade "
                "gracefully to [] on failure; RAG writes will raise."
            )

        logger.info("Initializing HuggingFaceEndpointEmbeddings model=%s", EMBEDDING_MODEL)
        _embeddings = HuggingFaceEndpointEmbeddings(model=EMBEDDING_MODEL)
    return _embeddings


def get_chroma_collection(collection_name: str):
    """Returns a cached langchain_chroma.Chroma vector store bound to the
    given collection name on the shared Chroma server (see
    docker-compose.yml). One instance per collection name for the life of
    the process — no reason to reopen the HTTP connection and re-resolve
    the embedding function on every tool call."""
    if collection_name not in _collections:
        from langchain_chroma import Chroma

        _collections[collection_name] = Chroma(
            collection_name=collection_name,
            embedding_function=get_embedding_function(),
            host=CHROMA_HOST,
            port=CHROMA_PORT,
        )
    return _collections[collection_name]