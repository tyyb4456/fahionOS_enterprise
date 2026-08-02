"""
Policy Document Upload — brand owner uploads Inventory Policy.pdf, Supplier
Contracts.pdf, etc.; this parses, chunks, and indexes them into Chroma so
the Inventory Agent's retrieve_policy tool can find them (see
agents/inventory/tools.py, agents/inventory/memory.py).

POST   /api/v1/brands/me/policies         → upload + index a document
GET    /api/v1/brands/me/policies         → list uploaded documents
DELETE /api/v1/brands/me/policies/{id}    → remove a document + its chunks

Wire into your app with:
    from api.routers import policy_documents
    app.include_router(policy_documents.router)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from agents.inventory import memory as rag
from api.auth import get_current_brand
from db import crud_policy_documents as crud
from db.models import Brand
from db.session import get_session
from documents.chunking import chunk_text
from documents.parsing import UnsupportedDocumentType, extract_text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/brands/me/policies", tags=["policy-documents"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


@router.post("")
async def upload_policy_document(
    file: UploadFile,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
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
    indexed = await rag.ingest_policy_chunks(
        brand.brand_id, chunks, source=file.filename, document_id=str(document_id)
    )

    record = await crud.create_policy_document(
        session, brand.brand_id, file.filename, indexed, document_id=document_id
    )
    await session.commit()

    return {
        "id": str(record.id),
        "filename": record.filename,
        "chunks_indexed": indexed,
    }


@router.get("")
async def list_policy_documents(
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_policy_documents(session, brand.brand_id)


@router.delete("/{document_id}", status_code=204)
async def delete_policy_document(
    document_id: str,
    brand: Brand = Depends(get_current_brand),
    session: AsyncSession = Depends(get_session),
):
    record = await crud.get_policy_document(session, brand.brand_id, document_id)
    if not record:
        raise HTTPException(404, "Policy document not found.")

    # record.id IS the document_id Chroma's chunks were tagged with at
    # ingest time (see crud_policy_documents.create_policy_document) — same
    # string form, so this reliably finds and removes them.
    await rag.delete_policy_document(brand.brand_id, document_id=str(record.id))
    await crud.delete_policy_document_record(session, record)
    await session.commit()
