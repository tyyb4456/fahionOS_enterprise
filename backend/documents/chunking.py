"""
Chunking for RAG ingestion. Thin wrapper around
langchain_text_splitters.RecursiveCharacterTextSplitter — isolated in its
own function so callers don't need to know or care which splitter we use.
"""
from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = [c.strip() for c in splitter.split_text(text)]
    return [c for c in chunks if c]
