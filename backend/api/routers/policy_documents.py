"""
Policy Document Upload — brand owner uploads Inventory Policy.pdf, Sales
SOP.pdf, Pricing Strategy.pdf, etc.; this parses, chunks, and indexes them
into Chroma so an agent's retrieve_policy tool can find them.

Routed per agent so Inventory and Sales policy documents (and their Chroma
collections — see agents/inventory/memory.py vs agents/sales/memory.py)
never mix:

POST   /api/v1/brands/me/policies/{agent}         → upload + index a document
GET    /api/v1/brands/me/policies/{agent}          → list uploaded documents
DELETE /api/v1/brands/me/policies/{agent}/{id}     → remove a document + its chunks

agent: "inventory" | "sales"
"""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_brand
from db import crud_policy_documents as crud
from db.models import Brand
from db.session import get_session
from documents.chunking import chunk_text
from documents.parsing import UnsupportedDocumentType, extract_text

router = APIRouter(prefix="/api/v1/brands/me/policies", tags=["policy-documents"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB

AgentName = Literal["inventory", "sales"]


def _rag_module(agent: AgentName):
    if agent == "sales":
        from agents.sales import memory as rag
        return rag
    from agents.inventory import memory as rag
    return rag


@router.post("/{agent}")
async def upload_policy_document(
    agent: AgentName,
    file: UploadFile,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    rag = _rag_module(agent)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB limit.")

    try:
        text = extract_text(file.filename, content)
    except UnsupportedDocumentType as e:
        raise HTTPException(400, str(e))

    if not text.strip():
        raise HTTPException(400, "No extractable text found in this file.")

    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(400, "Text extracted but produced no usable chunks.")

    document_id = uuid.uuid4()
    indexed = await rag.ingest_policy_chunks(brand.brand_id, chunks, source=file.filename, document_id=str(document_id))
    record = await crud.create_policy_document(
        session, brand.brand_id, file.filename, indexed, document_id=document_id, agent=agent,
    )
    await session.commit()

    return {"id": str(record.id), "agent": agent, "filename": record.filename, "chunks_indexed": indexed}


@router.get("/{agent}")
async def list_policy_documents(
    agent: AgentName,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_policy_documents(session, brand.brand_id, agent=agent)


@router.delete("/{agent}/{document_id}", status_code=204)
async def delete_policy_document(
    agent: AgentName,
    document_id: str,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    record = await crud.get_policy_document(session, brand.brand_id, document_id, agent=agent)
    if not record:
        raise HTTPException(404, "Policy document not found.")

    rag = _rag_module(agent)
    await rag.delete_policy_document(brand.brand_id, document_id=str(record.id))
    await crud.delete_policy_document_record(session, record)
    await session.commit()