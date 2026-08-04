"""
Bookkeeping for uploaded policy documents. The chunk text + embeddings
themselves live in Chroma (agents/inventory/memory.py) — this is just the
"what's been uploaded" list for the dashboard.
"""
from __future__ import annotations

import logging
import uuid as uuid_module
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PolicyDocument

logger = logging.getLogger(__name__)


async def create_policy_document(
    session: AsyncSession, brand_id: str, filename: str, chunk_count: int, document_id: uuid_module.UUID,
    agent: str = "inventory",
) -> PolicyDocument:
    logger.info("Creating policy document for brand=%s agent=%s filename=%s chunks=%d",
                brand_id, agent, filename, chunk_count)
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
    results = [
        {"id": str(d.id), "filename": d.filename, "chunk_count": d.chunk_count, "created_at": d.created_at.isoformat()}
        for d in (await session.execute(stmt)).scalars().all()
    ]
    logger.info("Listed %d policy documents for brand=%s agent=%s", len(results), brand_id, agent)
    return results


async def get_policy_document(
    session: AsyncSession, brand_id: str, document_id: str, agent: str = "inventory"
) -> Optional[PolicyDocument]:
    try:
        doc_uuid = uuid_module.UUID(document_id)
    except ValueError:
        logger.error("Invalid document_id=%s for brand=%s", document_id, brand_id)
        return None
    stmt = select(PolicyDocument).where(
        PolicyDocument.brand_id == brand_id, PolicyDocument.id == doc_uuid, PolicyDocument.agent == agent,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_policy_document_record(session: AsyncSession, document: PolicyDocument) -> None:
    logger.info("Deleting policy document id=%s filename=%s", document.id, document.filename)
    await session.delete(document)
    await session.flush()
