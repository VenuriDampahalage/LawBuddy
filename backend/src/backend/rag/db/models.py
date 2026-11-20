"""Database schema owned by the RAG engine.

documents    one uploaded PDF (may contain several Acts)
acts         one Act inside a document (principal, amendment, special provisions, constitution)
legal_nodes  the hierarchy tree. Each row is ONE VERSION of a provision:
               - is_current=False rows are history (superseded by an amendment)
               - superseded_by_id / amended_by_act_id link the version chain
chunks       the retrieval units (embedded + full-text indexed), pointing at a legal_node

Migrations live in backend/alembic (one place for every table in the database).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 1536  # text-embedding-3-small

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid()
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # pending -> parsing -> chunking -> embedding -> ready | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    parse_tier: Mapped[str | None] = mapped_column(String(32))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # backend user id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    acts: Mapped[list[Act]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Act(Base):
    __tablename__ = "acts"

    id: Mapped[uuid.UUID] = _uuid()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    act_number: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    # principal | amendment | special | constitution
    kind: Mapped[str] = mapped_column(String(20), default="principal")
    # Stable identity of the law this Act is or amends, e.g. "code-of-criminal-procedure-act"
    law_key: Mapped[str] = mapped_column(String(200), index=True)
    amends_act_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("acts.id", ondelete="SET NULL")
    )
    certified_on: Mapped[date | None] = mapped_column(Date)
    ord: Mapped[int] = mapped_column(Integer, default=0)  # position inside the document
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="acts")


class LegalNode(Base):
    __tablename__ = "legal_nodes"

    id: Mapped[uuid.UUID] = _uuid()
    act_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("acts.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_nodes.id", ondelete="CASCADE"), index=True
    )
    # act | schedule | part | chapter | group | section | subsection | explanation |
    # paragraph | subparagraph | definition
    level: Mapped[str] = mapped_column(String(20))
    number: Mapped[str | None] = mapped_column(String(20))
    heading: Mapped[str | None] = mapped_column(Text)        # marginal note / title
    term: Mapped[str | None] = mapped_column(String(200))    # definitions only
    # Version identity within a law, e.g. "s.443", "s.443(b)", "Art.14A", "s.2/def:peace officer"
    provision_key: Mapped[str | None] = mapped_column(String(200), index=True)
    path: Mapped[str] = mapped_column(Text)                   # "Part II › Chapter XV › Art.111M"
    ord: Mapped[int] = mapped_column(Integer)                 # reading order inside the Act
    text: Mapped[str] = mapped_column(Text, default="")       # own text (children separate)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    printed_page_start: Mapped[str | None] = mapped_column(String(10))
    printed_page_end: Mapped[str | None] = mapped_column(String(10))
    amendment_notes: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # --- versioning ---
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_nodes.id", ondelete="SET NULL")
    )
    amended_by_act_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("acts.id", ondelete="SET NULL")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)


class AmendmentProposal(Base):
    """One edit an amendment Act makes to a principal Act, waiting for (or after) review.

    Created by scanning amendment Acts (LLM extraction + code application); approving one
    creates a new current version of the target section in legal_nodes."""

    __tablename__ = "amendment_proposals"

    id: Mapped[uuid.UUID] = _uuid()
    amendment_act_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("acts.id", ondelete="CASCADE"), index=True)
    amendment_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legal_nodes.id", ondelete="CASCADE"), index=True)   # the amending section
    target_act_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("acts.id", ondelete="CASCADE"), index=True)          # the principal Act
    op_index: Mapped[int] = mapped_column(Integer, default=0)
    operation: Mapped[str] = mapped_column(String(30))
    target_provision: Mapped[str] = mapped_column(String(50))           # "s.443"
    target_part: Mapped[str | None] = mapped_column(String(50))         # "(b)"
    new_provision: Mapped[str | None] = mapped_column(String(50))       # "s.432A" (insertions)
    instruction: Mapped[dict] = mapped_column(JSONB)                   # the extracted op
    summary: Mapped[str] = mapped_column(Text)
    # Version of the target section the proposal was computed against (None for insertions)
    base_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_nodes.id", ondelete="SET NULL"))
    current_text: Mapped[str] = mapped_column(Text, default="")
    proposed_text: Mapped[str] = mapped_column(Text, default="")
    current_heading: Mapped[str | None] = mapped_column(Text)
    proposed_heading: Mapped[str | None] = mapped_column(Text)
    # pending | needs_attention | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    problem: Mapped[str | None] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)       # text changed by an admin
    created_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_nodes.id", ondelete="SET NULL"))              # version made on approval
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = _uuid()
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legal_nodes.id", ondelete="CASCADE"), index=True
    )
    act_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("acts.id", ondelete="CASCADE"), index=True)
    # leaf (subsection-sized) | section (whole section) | definition
    kind: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)       # what gets embedded: breadcrumb + text
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_current_kind", "is_current", "kind"),
    )
