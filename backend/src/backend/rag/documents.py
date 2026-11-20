"""Document management used by the admin API: store uploads, list, inspect, delete."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, update

from backend.core.config import get_settings
from backend.core.db import get_session
from backend.rag.db.models import Act, Chunk, Document, LegalNode

IN_PROGRESS = ("pending", "parsing", "chunking", "embedding")


@dataclass
class ActInfo:
    id: uuid.UUID
    title: str
    kind: str
    act_number: int | None
    year: int | None
    page_start: int | None
    page_end: int | None
    sections: int


@dataclass
class DocumentInfo:
    id: uuid.UUID
    filename: str
    status: str
    error: str | None
    page_count: int | None
    uploaded_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    acts: int
    chunks: int


def store_upload(data: bytes, original_name: str) -> Path:
    """Save uploaded bytes into raw_pdf_dir under a collision-free, filesystem-safe name."""
    digest = hashlib.sha256(data).hexdigest()[:12]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name).stem)[:80] or "document"
    path = get_settings().raw_pdf_dir / f"{digest}_{stem}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return path


def document_path(document_id: uuid.UUID) -> Path | None:
    with get_session() as db:
        name = db.scalar(select(Document.filename).where(Document.id == document_id))
    return get_settings().raw_pdf_dir / name if name else None


def list_documents() -> list[DocumentInfo]:
    with get_session() as db:
        acts = (select(Act.document_id, func.count().label("n")).group_by(Act.document_id)
                .subquery())
        chunks = (select(Act.document_id, func.count(Chunk.id).label("n"))
                  .join(Chunk, Chunk.act_id == Act.id).group_by(Act.document_id).subquery())
        rows = db.execute(
            select(Document, func.coalesce(acts.c.n, 0), func.coalesce(chunks.c.n, 0))
            .outerjoin(acts, acts.c.document_id == Document.id)
            .outerjoin(chunks, chunks.c.document_id == Document.id)
            .order_by(Document.created_at.desc())
        ).all()
        return [_info(d, a, c) for d, a, c in rows]


def get_document(document_id: uuid.UUID) -> tuple[DocumentInfo, list[ActInfo]] | None:
    docs = {d.id: d for d in list_documents()}
    if document_id not in docs:
        return None
    with get_session() as db:
        n_sections = (select(LegalNode.act_id, func.count().label("n"))
                      .where(LegalNode.level == "section").group_by(LegalNode.act_id).subquery())
        rows = db.execute(
            select(Act, func.coalesce(n_sections.c.n, 0))
            .outerjoin(n_sections, n_sections.c.act_id == Act.id)
            .where(Act.document_id == document_id).order_by(Act.ord)
        ).all()
    acts = [ActInfo(a.id, a.title, a.kind, a.act_number, a.year, a.page_start, a.page_end, n)
            for a, n in rows]
    return docs[document_id], acts


@dataclass
class LawInfo:
    title: str
    kind: str              # principal | amendment | special | constitution
    act_number: int | None
    year: int | None


def list_laws() -> list[LawInfo]:
    """Acts that are searchable right now (their document is 'ready'), for the public site."""
    with get_session() as db:
        rows = db.execute(
            select(Act.title, Act.kind, Act.act_number, Act.year)
            .join(Document, Document.id == Act.document_id)
            .where(Document.status == "ready")
            .order_by(Act.kind != "constitution", Act.kind != "principal", Act.year, Act.title)
        ).all()
    seen, out = set(), []
    for r in rows:
        if r.title.lower() not in seen:
            seen.add(r.title.lower())
            out.append(LawInfo(r.title, r.kind, r.act_number, r.year))
    return out


def set_pending(document_id: uuid.UUID) -> bool:
    with get_session() as db:
        res = db.execute(update(Document).where(Document.id == document_id)
                         .values(status="pending", error=None))
        db.commit()
        return res.rowcount > 0


def delete_document(document_id: uuid.UUID) -> bool:
    """Delete the document, everything derived from it (cascade) and the stored PDF."""
    with get_session() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return False
        path = get_settings().raw_pdf_dir / doc.filename
        db.delete(doc)
        db.commit()
    path.unlink(missing_ok=True)
    return True


def fail_interrupted() -> int:
    """At startup: documents left mid-processing by a crash/restart are marked failed."""
    with get_session() as db:
        res = db.execute(update(Document).where(Document.status.in_(IN_PROGRESS))
                         .values(status="failed", error="Interrupted by a server restart; "
                                                        "re-process the document."))
        db.commit()
        return res.rowcount


def _info(d: Document, acts: int, chunks: int) -> DocumentInfo:
    return DocumentInfo(d.id, d.filename, d.status, d.error, d.page_count, d.uploaded_by,
                        d.created_at, d.updated_at, acts, chunks)
