"""Admin document management + PDF download for citations."""

import logging
import uuid
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.db import new_session
from backend.core.security import (
    FILE_TOKEN_SECONDS,
    AdminUser,
    CurrentUser,
    create_file_token,
    file_token_valid,
    get_current_user,
)
from backend.rag import api as engine
from backend.schemas import ActOut, DocumentDetailOut, DocumentOut, UploadOut

log = logging.getLogger(__name__)

admin = APIRouter(prefix="/admin/documents", tags=["admin: documents"])
public = APIRouter(prefix="/documents", tags=["documents"])


def _process(document_id: uuid.UUID) -> None:
    """Background job. Failures are recorded on the document row by the engine."""
    try:
        engine.process_document(document_id)
    except Exception:
        log.exception("processing document %s failed", document_id)


def _doc_out(document_id: uuid.UUID) -> DocumentOut:
    found = engine.get_document(document_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentOut.model_validate(asdict(found[0]))


@admin.post("", response_model=UploadOut, status_code=status.HTTP_202_ACCEPTED)
async def upload(file: UploadFile, background: BackgroundTasks, user: AdminUser) -> UploadOut:
    """Upload a legislation PDF. Processing runs in the background; poll the document's
    status (pending -> parsing -> chunking -> embedding -> ready | failed)."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"PDF is larger than {get_settings().max_upload_mb} MB")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a PDF")

    path = engine.store_upload(data, file.filename or "document.pdf")
    doc_id, created = engine.register_document(path, uploaded_by=user.id)
    if created:
        background.add_task(_process, doc_id)
    else:
        # Same PDF already stored under another name: don't leave a second copy on disk.
        existing = engine.document_path(doc_id)
        if existing is not None and existing.resolve() != path.resolve():
            path.unlink(missing_ok=True)
    return UploadOut(document=_doc_out(doc_id), created=created)


@admin.get("", response_model=list[DocumentOut])
def list_documents(_: AdminUser) -> list[DocumentOut]:
    return [DocumentOut.model_validate(asdict(d)) for d in engine.list_documents()]


@admin.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: uuid.UUID, _: AdminUser) -> DocumentDetailOut:
    found = engine.get_document(document_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    info, acts = found
    return DocumentDetailOut(**asdict(info),
                             act_list=[ActOut.model_validate(asdict(a)) for a in acts])


@admin.post("/{document_id}/reprocess", response_model=DocumentOut,
            status_code=status.HTTP_202_ACCEPTED)
def reprocess(document_id: uuid.UUID, background: BackgroundTasks, _: AdminUser) -> DocumentOut:
    current = _doc_out(document_id)
    if current.status in ("pending", "parsing", "chunking", "embedding"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is already being processed")
    engine.set_pending(document_id)
    background.add_task(_process, document_id)
    return _doc_out(document_id)


@admin.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(document_id: uuid.UUID, _: AdminUser) -> None:
    if not engine.delete_document(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


class FileLinkOut(BaseModel):
    url: str
    expires_in: int


@public.get("/{document_id}/link", response_model=FileLinkOut)
def file_link(document_id: uuid.UUID, _: CurrentUser) -> FileLinkOut:
    """A short-lived URL for the source PDF. A new browser tab can't send the Authorization
    header, so the citation's "Open PDF" button opens this URL instead (+ #page=N)."""
    if engine.document_path(document_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    token = create_file_token(document_id)
    return FileLinkOut(url=f"/api/documents/{document_id}/file?token={token}",
                       expires_in=FILE_TOKEN_SECONDS)


@public.get("/{document_id}/file")
def download(document_id: uuid.UUID, request: Request, token: str | None = None) -> FileResponse:
    """The source PDF. Accepts either the usual Bearer token or a `token` from /link."""
    if not (token and file_token_valid(token, document_id)):
        # Fall back to normal authentication (raises 401 if missing/invalid).
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                                headers={"WWW-Authenticate": "Bearer"})
        with new_session() as db:
            get_current_user(auth.removeprefix("Bearer "), db)
    path = engine.document_path(document_id)
    if path is None or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name,
                        content_disposition_type="inline")
