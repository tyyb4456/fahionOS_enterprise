"""
Bookkeeping for uploaded policy documents. The chunk text + embeddings
themselves live in Chroma (agents/inventory/memory.py) — this is just the
"what's been uploaded" list for the dashboard.
"""
from __future__ import annotations

import uuid as uuid_module
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PolicyDocument


async def create_policy_document(
    session: AsyncSession, brand_id: str, filename: str, chunk_count: int, document_id: uuid_module.UUID,
    agent: str = "inventory",
) -> PolicyDocument:
    doc = PolicyDocument(id=document_id, brand_id=brand_id, agent=agent, filename=filename, chunk_count=chunk_count)
    session.add(doc)
    await session.flush()
    return doc


async def list_policy_documents(session: AsyncSession, brand_id: str, agent: str = "inventory") -> list[dict]:
    stmt = (
        select(PolicyDocument)
        .where(PolicyDocument.brand_id == brand_id, PolicyDocument.agent == agent)
        .order_by(PolicyDocument.created_at.desc())
    )
    return [
        {"id": str(d.id), "filename": d.filename, "chunk_count": d.chunk_count, "created_at": d.created_at.isoformat()}
        for d in (await session.execute(stmt)).scalars().all()
    ]


async def get_policy_document(
    session: AsyncSession, brand_id: str, document_id: str, agent: str = "inventory"
) -> Optional[PolicyDocument]:
    try:
        doc_uuid = uuid_module.UUID(document_id)
    except ValueError:
        return None
    stmt = select(PolicyDocument).where(
        PolicyDocument.brand_id == brand_id, PolicyDocument.id == doc_uuid, PolicyDocument.agent == agent,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_policy_document_record(session: AsyncSession, document: PolicyDocument) -> None:
    await session.delete(document)
    await session.flush()
