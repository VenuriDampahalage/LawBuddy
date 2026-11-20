"""Find amendments, propose the amended text, and (after admin review) apply them.

scan_amendments()   amendment Acts -> LLM extraction -> code applies edits -> proposals
approve_proposal()  creates a NEW current version of the section (old one kept as history),
                    indexes it for search; revert_proposal() undoes that
"""

from __future__ import annotations

import itertools
import logging
import re
import threading
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import exists, func, select, text, update
from sqlalchemy.orm import Session

from backend.core.db import get_session
from backend.rag.amendments.ops import (
    AmendmentOp,
    ExtractedOps,
    apply_op,
    new_section_text,
    norm_number,
)
from backend.rag.amendments.text import clean_text
from backend.rag.db.models import Act, AmendmentProposal, Chunk, LegalNode
from backend.rag.ingestion.chunker import LEAF_MAX_TOKENS, SECTION_MAX_TOKENS, count_tokens
from backend.rag.llm.chat import structured
from backend.rag.llm.embeddings import embed_texts

log = logging.getLogger(__name__)

OPEN = ("pending", "needs_attention")
RE_OPERATIVE = re.compile(r"\b(amended|repealed|inserted|substitut)", re.IGNORECASE)
RE_TOP_PART = re.compile(r"(?m)^\(\d+[A-Z]?\)")


class AmendmentError(ValueError):
    """A review action that can't be done (message is shown to the admin)."""


EXTRACT_PROMPT = """\
You convert one section of a Sri Lankan amending Act into structured edits to the principal Act.

Sri Lankan amending Acts use fixed wording. Map each "by the …" clause to ONE operation:
- "by the substitution for the words “X” of the words “Y”" -> substitute_words (old_words=X, new_words=Y)
- "by the repeal of subsection (2) … and the substitution therefor of the following" -> replace
  with target_part "(2)" and the new text's first/last words
- "Section N … is hereby repealed and the following section is substituted therefor" -> replace
  with target_part null (whole section)
- "the following new section is inserted immediately after section N … shall have effect as
  section NA" -> insert_after with target_section N and new_section_number NA
- "by the insertion immediately after subsection (3) of the following new subsection" ->
  insert_after with target_part "(3)"
- "by the repeal of paragraph (ee)" -> repeal with target_part "(ee)"; a whole section repealed
  without replacement -> repeal with target_part null
- "by the repeal of the marginal note … and the substitution therefor of …" -> replace_heading
- anything else (renumbering, "wherever it appears", schedules) -> other

Rules:
- Copy old_words, new_words, new_text_start, new_text_end and new_heading EXACTLY from the
  text, without the surrounding quotation marks. Never paraphrase or correct them.
- new_text_start / new_text_end: 6-10 consecutive words from the beginning / end of the new
  provision (for a new section, start at its number, e.g. "432A. (1) Where the person").
- target_part uses brackets: "(2)", "(b)", "(1)(a)".
- If the section is not an amendment to the principal Act (short title, "Sinhala text to
  prevail", interpretation, validation, transitional provisions), return no operations.
"""


# ---- reading sections --------------------------------------------------------------------

def section_text(db: Session, node_id: uuid.UUID) -> str:
    """A section's full text, rebuilt from its node tree with "(1)" / "(a)" labels."""
    rows = db.execute(text("""
        WITH RECURSIVE sub AS (
            SELECT id, level, number, text, ord, 0 AS depth FROM legal_nodes WHERE id = :id
            UNION ALL
            SELECT n.id, n.level, n.number, n.text, n.ord, sub.depth + 1
            FROM legal_nodes n JOIN sub ON n.parent_id = sub.id
        ) SELECT level, number, text, depth FROM sub ORDER BY ord"""), {"id": node_id}).all()
    lines = []
    for r in rows:
        body = (r.text or "").strip()
        if r.depth and r.level in ("subsection", "paragraph", "subparagraph") and r.number:
            body = f"{r.number} {body}".strip()
        if body:
            lines.append(body)
    return clean_text("\n".join(lines))


def _current_section(db: Session, act_id: uuid.UUID, key: str) -> LegalNode | None:
    return db.scalar(select(LegalNode).where(
        LegalNode.act_id == act_id, LegalNode.level == "section", LegalNode.provision_key == key,
        LegalNode.is_current).limit(1))


def _descendant_ids(db: Session, node_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(text("""
        WITH RECURSIVE sub AS (
            SELECT id FROM legal_nodes WHERE id = :id
            UNION ALL SELECT n.id FROM legal_nodes n JOIN sub ON n.parent_id = sub.id
        ) SELECT id FROM sub"""), {"id": node_id}))


def _unit(act: Act) -> str:
    return "Art." if act.kind == "constitution" else "s."


# ---- scanning ----------------------------------------------------------------------------

def link_amendment_acts(db: Session) -> None:
    """Point unlinked amendment Acts at their principal Act (any document, same law_key)."""
    for a in db.scalars(select(Act).where(Act.kind == "amendment", Act.amends_act_id.is_(None))):
        principal = db.scalar(select(Act.id).where(Act.law_key == a.law_key,
                                                   Act.kind.in_(("principal", "constitution")))
                              .limit(1))
        if principal:
            a.amends_act_id = principal
    db.commit()


_scan_lock = threading.Lock()


def scan_in_progress() -> bool:
    return _scan_lock.locked()


def scan_amendments() -> int:
    """Create proposals for every amending section that hasn't been scanned yet, then
    refresh open proposals. Returns the number of proposals created (0 if a scan is
    already running)."""
    if not _scan_lock.acquire(blocking=False):
        return 0
    try:
        created = _scan()
        recompute_open_proposals()
        return created
    finally:
        _scan_lock.release()


def _scan() -> int:
    created = 0
    with get_session() as db:
        link_amendment_acts(db)
        acts = db.scalars(select(Act).where(Act.kind == "amendment", Act.amends_act_id.is_not(None))
                          .order_by(Act.year, Act.act_number)).all()
        for amend in acts:
            principal = db.get(Act, amend.amends_act_id)
            sections = db.scalars(select(LegalNode).where(
                LegalNode.act_id == amend.id, LegalNode.level == "section",
                ~exists().where(AmendmentProposal.amendment_node_id == LegalNode.id))
                .order_by(LegalNode.ord)).all()
            for sec in sections:
                body = section_text(db, sec.id)
                if not RE_OPERATIVE.search(body):
                    continue
                try:
                    ops = _extract(amend, principal, sec, body)
                except Exception:
                    log.exception("extracting %s %s failed", amend.title, sec.provision_key)
                    continue
                created += _propose(db, amend, principal, sec, body, ops)
                db.commit()
    log.info("amendment scan: %d new proposals", created)
    return created


def _extract(amend: Act, principal: Act, sec: LegalNode, body: str) -> list[AmendmentOp]:
    user = (f"Principal Act: {principal.title}\nAmending Act: {amend.title}\n"
            f"Amending section {sec.provision_key}"
            + (f" (marginal note: {sec.heading})" if sec.heading else "")
            + f":\n\n{body}")
    return structured(EXTRACT_PROMPT, user, ExtractedOps, effort="medium").operations


def _propose(db: Session, amend: Act, principal: Act, sec: LegalNode, body: str,
             ops: list[AmendmentOp]) -> int:
    unit = _unit(principal)
    groups: dict[str, list[AmendmentOp]] = defaultdict(list)
    inserts: list[AmendmentOp] = []
    for op in ops:
        is_new_section = op.operation == "insert_after" and not op.target_part and op.new_section_number
        (inserts.append(op) if is_new_section else groups[norm_number(op.target_section)].append(op))

    n = 0
    for number, group in groups.items():
        key = f"{unit}{number}"
        target = _current_section(db, principal.id, key)
        p = AmendmentProposal(
            amendment_act_id=amend.id, amendment_node_id=sec.id, target_act_id=principal.id,
            op_index=n, operation=group[0].operation if len(group) == 1 else "multiple",
            target_provision=key, target_part=group[0].target_part if len(group) == 1 else None,
            instruction={"ops": [o.model_dump() for o in group]},
            summary=" ".join(o.summary for o in group))
        if target is None:
            p.status, p.problem = "needs_attention", f"{key} was not found in {principal.title}."
        else:
            _compute(db, p, target, body, amend, sec)
        db.add(p)
        n += 1

    for op in inserts:
        new_key = f"{unit}{norm_number(op.new_section_number)}"
        p = AmendmentProposal(
            amendment_act_id=amend.id, amendment_node_id=sec.id, target_act_id=principal.id,
            op_index=n, operation="insert_section",
            target_provision=f"{unit}{norm_number(op.target_section)}", new_provision=new_key,
            instruction={"ops": [op.model_dump()]}, summary=op.summary,
            proposed_heading=clean_text(op.new_heading or "").strip("“”\"").rstrip(".") or None)
        new_text, problem = new_section_text(op, body)
        p.proposed_text = new_text or ""
        if _current_section(db, principal.id, p.target_provision) is None:
            problem = problem or f"{p.target_provision} (the section to insert after) was not found."
        if _current_section(db, principal.id, new_key) is not None:
            problem = problem or f"{new_key} already exists in {principal.title}."
        p.status, p.problem = ("needs_attention", problem) if problem else ("pending", None)
        db.add(p)
        n += 1
    return n


def _compute(db: Session, p: AmendmentProposal, target: LegalNode, amend_text: str,
             amend: Act, amend_sec: LegalNode) -> None:
    """(Re)compute the proposed text against the target's current version."""
    current = section_text(db, target.id)
    heading = target.heading
    note = f"[Repealed by {amend.title}, {amend_sec.provision_key}.]"
    problems = []
    proposed, new_heading = current, heading
    for raw in p.instruction["ops"]:
        r = apply_op(AmendmentOp(**raw), proposed, new_heading, amend_text,
                     p.target_provision, note)
        if r.problem:
            problems.append(r.problem)
        else:
            proposed, new_heading = r.text, r.heading
    p.base_node_id, p.current_text, p.current_heading = target.id, current, heading
    p.proposed_text, p.proposed_heading = proposed, new_heading
    p.status, p.problem = ("needs_attention", " ".join(problems)) if problems else ("pending", None)


def recompute_open_proposals() -> int:
    """Re-apply the saved instructions of open, unedited proposals (no LLM calls), e.g. after
    the applying code improved or another amendment changed a section. Returns the count."""
    n = 0
    with get_session() as db:
        for p in db.scalars(select(AmendmentProposal).where(
                AmendmentProposal.status.in_(OPEN), AmendmentProposal.edited.is_(False))):
            amend, sec = db.get(Act, p.amendment_act_id), db.get(LegalNode, p.amendment_node_id)
            body = section_text(db, sec.id)
            if p.operation == "insert_section":
                new_text, problem = new_section_text(AmendmentOp(**p.instruction["ops"][0]), body)
                p.proposed_text = new_text or ""
                p.status, p.problem = ("needs_attention", problem) if problem else ("pending", None)
            else:
                target = _current_section(db, p.target_act_id, p.target_provision)
                if target is None:
                    continue
                _compute(db, p, target, body, amend, sec)
            n += 1
        db.commit()
    return n


# ---- listing and review --------------------------------------------------------------------

def list_proposals(status: str | None = None) -> list[dict]:
    with get_session() as db:
        amend_act, target_act = Act.__table__.alias("amend_act"), Act.__table__.alias("target_act")
        stmt = (select(AmendmentProposal, amend_act.c.title, amend_act.c.year,
                       LegalNode.provision_key, LegalNode.heading, target_act.c.title)
                .join(amend_act, amend_act.c.id == AmendmentProposal.amendment_act_id)
                .join(target_act, target_act.c.id == AmendmentProposal.target_act_id)
                .join(LegalNode, LegalNode.id == AmendmentProposal.amendment_node_id)
                .order_by(amend_act.c.year, amend_act.c.act_number, LegalNode.ord,
                          AmendmentProposal.op_index))
        if status == "open":
            stmt = stmt.where(AmendmentProposal.status.in_(OPEN))
        elif status:
            stmt = stmt.where(AmendmentProposal.status == status)
        rows = db.execute(stmt).all()
        out = []
        for p, a_title, a_year, a_prov, a_heading, t_title in rows:
            out.append({
                "id": p.id, "status": p.status, "operation": p.operation, "summary": p.summary,
                "problem": p.problem, "edited": p.edited,
                "amendment_act": a_title, "amendment_year": a_year,
                "amendment_provision": a_prov, "amendment_heading": a_heading,
                "amendment_text": section_text(db, p.amendment_node_id),
                "target_act": t_title, "target_provision": p.target_provision,
                "new_provision": p.new_provision,
                "current_heading": p.current_heading, "proposed_heading": p.proposed_heading,
                "current_text": p.current_text, "proposed_text": p.proposed_text,
                "reviewed_at": p.reviewed_at, "created_at": p.created_at,
            })
        return out


def proposal_counts() -> dict[str, int]:
    with get_session() as db:
        return dict(db.execute(select(AmendmentProposal.status, func.count())
                               .group_by(AmendmentProposal.status)).all())


def _get(db: Session, proposal_id: uuid.UUID) -> AmendmentProposal:
    p = db.get(AmendmentProposal, proposal_id)
    if p is None:
        raise LookupError("Proposal not found")
    return p


def edit_proposal(proposal_id: uuid.UUID, proposed_text: str,
                  proposed_heading: str | None) -> None:
    with get_session() as db:
        p = _get(db, proposal_id)
        if p.status not in OPEN:
            raise AmendmentError("Only proposals waiting for review can be edited.")
        if not proposed_text.strip():
            raise AmendmentError("The proposed text can’t be empty.")
        p.proposed_text = clean_text(proposed_text)
        p.proposed_heading = (proposed_heading or "").strip() or None
        p.edited, p.status, p.problem = True, "pending", None
        db.commit()


def reject_proposal(proposal_id: uuid.UUID, reviewer: uuid.UUID | None) -> None:
    with get_session() as db:
        p = _get(db, proposal_id)
        if p.status not in OPEN:
            raise AmendmentError("Only proposals waiting for review can be rejected.")
        p.status, p.reviewed_by, p.reviewed_at = "rejected", reviewer, datetime.now(UTC)
        db.commit()


def reopen_proposal(proposal_id: uuid.UUID) -> None:
    """Move a rejected proposal back to review."""
    with get_session() as db:
        p = _get(db, proposal_id)
        if p.status != "rejected":
            raise AmendmentError("Only rejected proposals can be reopened.")
        p.status = "needs_attention" if p.problem else "pending"
        db.commit()


def approve_proposal(proposal_id: uuid.UUID, reviewer: uuid.UUID | None) -> None:
    """Make the proposed text the current version of the section and index it for search."""
    with get_session() as db:
        p = _get(db, proposal_id)
        if p.status not in OPEN:
            raise AmendmentError("This proposal has already been reviewed.")
        if p.status == "needs_attention":
            raise AmendmentError("Fix the proposed text first (Edit), then approve it.")
        amend = db.get(Act, p.amendment_act_id)
        amend_sec = db.get(LegalNode, p.amendment_node_id)
        principal = db.get(Act, p.target_act_id)
        note = f"{'Inserted' if p.operation == 'insert_section' else 'Amended'} by {amend.title}, {amend_sec.provision_key}"

        if p.operation == "insert_section":
            if _current_section(db, principal.id, p.new_provision) is not None:
                raise AmendmentError(f"{p.new_provision} already exists.")
            anchor = _current_section(db, principal.id, p.target_provision)
            if anchor is None:
                raise AmendmentError(f"{p.target_provision} (the section to insert after) no longer exists.")
            number = p.new_provision.split(".", 1)[1]
            label = f"{p.new_provision} — {p.proposed_heading}" if p.proposed_heading else p.new_provision
            node = LegalNode(
                act_id=principal.id, parent_id=anchor.parent_id, level="section", number=number,
                heading=p.proposed_heading, provision_key=p.new_provision,
                path=" › ".join(anchor.path.split(" › ")[:-1] + [label]), ord=anchor.ord,
                text=p.proposed_text, page_start=amend_sec.page_start, page_end=amend_sec.page_end,
                printed_page_start=amend_sec.printed_page_start,
                printed_page_end=amend_sec.printed_page_end, amendment_notes=[note],
                is_current=True, amended_by_act_id=amend.id)
            db.add(node)
            db.flush()
            old = None
        else:
            current = _current_section(db, principal.id, p.target_provision)
            if current is None:
                raise AmendmentError(f"{p.target_provision} no longer exists.")
            if current.id != p.base_node_id:
                # The section changed (another amendment was approved) since this was computed.
                if p.edited:
                    p.status = "needs_attention"
                    p.problem = (f"{p.target_provision} has changed since you edited this. "
                                 "Check the text against the current version.")
                    _compute(db, p, current, section_text(db, amend_sec.id), amend, amend_sec)
                    db.commit()
                    raise AmendmentError(p.problem)
                _compute(db, p, current, section_text(db, amend_sec.id), amend, amend_sec)
                if p.status != "pending":
                    db.commit()
                    raise AmendmentError(p.problem or "The amendment no longer applies cleanly.")
            old = current
            path = current.path
            if p.proposed_heading and current.heading and p.proposed_heading != current.heading:
                path = path.replace(f"— {current.heading}", f"— {p.proposed_heading}")
            node = LegalNode(
                act_id=principal.id, parent_id=current.parent_id, level="section",
                number=current.number, heading=p.proposed_heading or current.heading,
                provision_key=current.provision_key, path=path, ord=current.ord,
                text=p.proposed_text, page_start=current.page_start, page_end=current.page_end,
                printed_page_start=current.printed_page_start,
                printed_page_end=current.printed_page_end,
                amendment_notes=list(dict.fromkeys([*(current.amendment_notes or []), note])),
                is_current=True, amended_by_act_id=amend.id)
            db.add(node)
            db.flush()
            old_ids = _descendant_ids(db, current.id)
            db.execute(update(LegalNode).where(LegalNode.id.in_(old_ids)).values(is_current=False))
            db.execute(update(Chunk).where(Chunk.node_id.in_(old_ids)).values(is_current=False))
            current.superseded_by_id = node.id

        _index_version(db, node, principal.id)
        p.status, p.problem = "approved", None
        p.created_node_id = node.id
        p.reviewed_by, p.reviewed_at = reviewer, datetime.now(UTC)
        if old is not None:
            p.base_node_id = old.id
        db.commit()


def revert_proposal(proposal_id: uuid.UUID) -> None:
    """Undo an approval: the previous version becomes current again."""
    with get_session() as db:
        p = _get(db, proposal_id)
        if p.status != "approved" or p.created_node_id is None:
            raise AmendmentError("Only approved proposals can be reverted.")
        node = db.get(LegalNode, p.created_node_id)
        if node is None or not node.is_current:
            raise AmendmentError("A later amendment has been applied on top of this one. "
                                 "Revert that one first.")
        if p.operation != "insert_section" and p.base_node_id:
            old_ids = _descendant_ids(db, p.base_node_id)
            db.execute(update(LegalNode).where(LegalNode.id.in_(old_ids)).values(is_current=True))
            db.execute(update(Chunk).where(Chunk.node_id.in_(old_ids)).values(is_current=True))
            db.execute(update(LegalNode).where(LegalNode.id == p.base_node_id)
                       .values(superseded_by_id=None))
        db.delete(node)                       # its chunks cascade
        p.status, p.created_node_id, p.reviewed_at = "pending", None, None
        db.commit()


# ---- indexing a new version ---------------------------------------------------------------

def _index_version(db: Session, node: LegalNode, act_id: uuid.UUID) -> None:
    """Chunks + embeddings for a section version that has no child nodes (flat text)."""
    body = node.text.strip()
    notes = node.amendment_notes or []
    history = ("\n[Amendment history: " + "; ".join(notes) + "]") if notes else ""

    def content(piece: str) -> str:
        return f"{node.path}\n{piece.strip()}{history}"

    pieces: list[tuple[str, str]] = []
    total = count_tokens(body)
    if total <= SECTION_MAX_TOKENS:
        pieces.append(("section", body))
    if total > LEAF_MAX_TOKENS:
        # One leaf per top-level subsection "(1) …", "(2) …" (plus any lead-in text).
        starts = [m.start() for m in RE_TOP_PART.finditer(body)]
        if starts:
            bounds = ([0] if starts[0] > 0 else []) + starts + [len(body)]
            blocks = [body[a:b] for a, b in itertools.pairwise(bounds)]
        else:
            blocks = [body]
        for block in blocks:
            words = block.split()
            if count_tokens(block) <= LEAF_MAX_TOKENS:
                pieces.append(("leaf", block))
            else:
                for i in range(0, len(words), 350):
                    pieces.append(("leaf", " ".join(words[max(0, i - 40): i + 350])))
    pieces = [(k, b) for k, b in pieces if b.strip()]
    texts = [content(b) for _, b in pieces]
    vectors = embed_texts(texts) if texts else []
    for (kind, _), txt, vec in zip(pieces, texts, vectors, strict=True):
        db.add(Chunk(node_id=node.id, act_id=act_id, kind=kind, content=txt,
                     token_count=count_tokens(txt), embedding=vec, is_current=True))


def get_proposal(proposal_id: uuid.UUID) -> dict:
    found = next((p for p in list_proposals() if p["id"] == proposal_id), None)
    if found is None:
        raise LookupError("Proposal not found")
    return found
