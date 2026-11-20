"""End-to-end ingestion: PDF -> parse -> legal tree -> chunks -> embeddings -> Postgres.

Status on the documents row moves pending -> parsing -> chunking -> embedding -> ready,
or to failed with the error message, so the admin UI can show progress.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.db import get_session
from backend.rag.db.models import Act, Chunk, Document, LegalNode
from backend.rag.ingestion.chunker import ChunkedAct, chunk_act
from backend.rag.ingestion.parser import file_sha256, parse_pdf
from backend.rag.ingestion.structure import build_tree
from backend.rag.llm.embeddings import embed_texts

log = logging.getLogger(__name__)


def _set_status(db: Session, doc: Document, status: str, error: str | None = None) -> None:
    doc.status, doc.error = status, error
    db.commit()
    log.info("%s: %s", doc.filename, status)


def register_document(path: Path, *, uploaded_by: uuid.UUID | None = None) -> tuple[uuid.UUID, bool]:
    """Create a 'pending' documents row for a PDF stored in raw_pdf_dir (fast; no parsing).
    Returns (document_id, created). created=False means this exact file already exists."""
    file_hash = file_sha256(path)
    with get_session() as db:
        existing = db.scalar(select(Document).where(Document.file_hash == file_hash))
        if existing:
            return existing.id, False
        doc = Document(filename=path.name, file_hash=file_hash, uploaded_by=uploaded_by)
        db.add(doc)
        db.commit()
        return doc.id, True


def ingest_pdf(path: Path, *, uploaded_by: uuid.UUID | None = None, force: bool = False) -> uuid.UUID:
    """Register + process in one call (scripts). Re-ingesting a ready file is a no-op
    unless force=True."""
    doc_id, created = register_document(path, uploaded_by=uploaded_by)
    with get_session() as db:
        status = db.scalar(select(Document.status).where(Document.id == doc_id))
    if not created and status == "ready" and not force:
        log.info("%s already ingested (%s)", path.name, doc_id)
        return doc_id
    process_document(doc_id)
    return doc_id


def process_document(document_id: uuid.UUID) -> None:
    """Parse, chunk, embed and store a registered document. Safe to call again to re-process:
    previous Acts/nodes/chunks of this document are replaced. Raises on failure (the
    document is left in status 'failed' with the error message)."""
    with get_session() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            raise LookupError(f"document {document_id} not found")
        path = get_settings().raw_pdf_dir / doc.filename
        db.execute(delete(Act).where(Act.document_id == doc.id))   # re-process: start clean
        db.commit()
        try:
            if not path.exists():
                raise FileNotFoundError(f"stored PDF is missing: {doc.filename}")
            _set_status(db, doc, "parsing")
            parsed = parse_pdf(path)
            doc.page_count, doc.parse_tier = len(parsed.pages), parsed.tier

            _set_status(db, doc, "chunking")
            chunked = [chunk_act(a) for a in build_tree(parsed)]
            if not chunked:
                raise ValueError("No Acts/sections could be detected in this PDF")

            _set_status(db, doc, "embedding")
            all_chunks = [c for ca in chunked for c in ca.chunks]
            vectors = embed_texts([c.content for c in all_chunks])
            vec_iter = iter(vectors)

            for order, ca in enumerate(chunked):
                _store_act(db, doc.id, order, ca, vec_iter)
            _link_amendments(db, doc.id)
            _set_status(db, doc, "ready")
            _scan_amendments_quietly()
            log.info("%s: %d acts, %d nodes, %d chunks", path.name, len(chunked),
                     sum(len(ca.nodes) for ca in chunked), len(all_chunks))
        except Exception as exc:
            db.rollback()
            # Remove partial rows but keep the document so the admin sees the failure.
            db.execute(delete(Act).where(Act.document_id == doc.id))
            _set_status(db, doc, "failed", f"{type(exc).__name__}: {exc}"[:2000])
            raise


def _store_act(db: Session, document_id: uuid.UUID, order: int, ca: ChunkedAct, vectors) -> None:
    act = Act(
        document_id=document_id, title=ca.meta.title, act_number=ca.meta.act_number,
        year=ca.meta.year, kind=ca.meta.kind, law_key=ca.meta.law_key, ord=order,
        page_start=ca.page_start, page_end=ca.page_end,
    )
    db.add(act)
    db.flush()
    if ca.nodes:
        db.execute(insert(LegalNode), [
            {**n.__dict__, "act_id": act.id, "is_current": True} for n in ca.nodes
        ])
    if ca.chunks:
        db.execute(insert(Chunk), [
            {"node_id": c.node_id, "act_id": act.id, "kind": c.kind, "content": c.content,
             "token_count": c.token_count, "embedding": next(vectors), "is_current": True}
            for c in ca.chunks
        ])
    db.commit()


def _link_amendments(db: Session, document_id: uuid.UUID) -> None:
    """Point amendment Acts at the principal Act they amend (same law_key).
    Applying the amendments to section text is a separate, admin-reviewed step."""
    amendments = db.scalars(select(Act).where(Act.document_id == document_id,
                                              Act.kind == "amendment")).all()
    for a in amendments:
        principal = db.scalar(select(Act.id).where(Act.law_key == a.law_key,
                                                   Act.kind == "principal").limit(1))
        if principal:
            db.execute(update(Act).where(Act.id == a.id).values(amends_act_id=principal))
    db.commit()


def _scan_amendments_quietly() -> None:
    """Propose amended section text for any new amendment Acts (reviewed in Admin).
    A failure here must never make the document itself fail."""
    try:
        from backend.rag.amendments.service import scan_amendments

        scan_amendments()
    except Exception:
        log.exception("amendment scan after ingestion failed")
