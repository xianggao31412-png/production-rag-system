"""
Document management routes.

    POST   /v1/documents          upload + ingest a file (multipart)
    GET    /v1/documents          list documents (optionally by namespace)
    DELETE /v1/documents/{id}     remove a document and all its chunks

Upload accepts the raw file plus an optional ``namespace`` (query param or form
field) and an optional ``title``. The heavy lifting lives in ``IngestService``;
these handlers just adapt HTTP <-> service calls.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.deps import get_container, require_api_key
from app.container import Container
from app.errors import NotFoundError
from app.models.schemas import (
    DeleteResponse,
    DocumentList,
    DocumentSummary,
    UploadResponse,
)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("", response_model=UploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    namespace: str = Query("default", max_length=128),
    namespace_form: Optional[str] = Form(None, alias="namespace"),
    title: Optional[str] = Form(None),
    _: str = Depends(require_api_key),
    container: Container = Depends(get_container),
) -> UploadResponse:
    ns = namespace_form or namespace
    raw = await file.read()
    return container.ingest_service.ingest(
        raw=raw,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "",
        namespace=ns,
        title=title,
    )


@router.get("", response_model=DocumentList)
async def list_documents(
    namespace: Optional[str] = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_api_key),
    container: Container = Depends(get_container),
) -> DocumentList:
    docs, total = container.metadata_store.list_documents(
        namespace=namespace, limit=limit, offset=offset
    )
    return DocumentList(
        namespace=namespace,
        total=total,
        documents=[
            DocumentSummary(
                id=d.id,
                namespace=d.namespace,
                filename=d.filename,
                content_type=d.content_type,
                char_count=d.char_count,
                chunk_count=d.chunk_count,
                size_bytes=d.size_bytes,
                created_at=d.created_at,
                title=d.title,
            )
            for d in docs
        ],
    )


@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: str,
    _: str = Depends(require_api_key),
    container: Container = Depends(get_container),
) -> DeleteResponse:
    namespace, deleted = container.ingest_service.delete_document(document_id)
    if namespace is None:
        raise NotFoundError(f"Document '{document_id}' not found.")
    return DeleteResponse(document_id=document_id, deleted_chunks=deleted, deleted=True)
