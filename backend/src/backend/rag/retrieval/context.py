"""Turn ranked chunk hits into the context the LLM answers from.

1. Auto-merge: hits are grouped by the section they belong to; a section's score is its best
   hit plus a bonus for every extra matching part. The whole section is used when it is small
   enough (its stored 'section' chunk), otherwise only the matching parts.
2. De-duplicate near-identical sections across Acts of the same law (e.g. the 2007 and 2013
   Special Provisions Acts) and keep the most recent one.
3. Attach definitions (from the same Acts) for terms that the selected text uses.
4. Attach later amendments: sections of amendment Acts whose heading names the section
   ("Amendment of section 443 ..."), until amendments are applied to the text itself.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.rag.retrieval.search import Hit

MAX_SECTIONS = 6
EXTRA_PART_BONUS = 0.1          # small reward for several matching parts in one section ...
MAX_EXTRA_PARTS = 2             # ... capped, so long sections don't win just by being long
DUPLICATE_SIMILARITY = 0.8      # word-set Jaccard above which two sections are "the same"
MAX_DEFINITIONS = 5
GENERIC_TERMS = {"chapter", "section", "schedule", "code", "court", "act", "law", "person",
                 "prescribed", "writing", "written", "enactment", "minister", "regulation"}
RE_SECTION_IN_HEADING = re.compile(r"\bsections?\s+(\d{1,3}\s?[A-Z]?)\b", re.IGNORECASE)
RE_TOKENS = re.compile(r"[a-z]{3,}")
# The question asks what a term means ("What does 'computer' mean?", "meaning of", "define …")
RE_ASKS_MEANING = re.compile(
    r"\bmean(s|ing)?\b|\bdefin(e|ed|es|ition|itions)\b|\bwhat (is|are) (a|an|the)?\s*[\"'“‘]",
    re.IGNORECASE)


def _similar(a: str, b: str) -> bool:
    sa, sb = set(RE_TOKENS.findall(a.lower())), set(RE_TOKENS.findall(b.lower()))
    return bool(sa and sb) and len(sa & sb) / len(sa | sb) >= DUPLICATE_SIMILARITY


@dataclass
class LaterAmendment:
    act_title: str
    year: int | None
    provision: str
    heading: str | None
    text: str


@dataclass
class ContextBlock:
    ref: int                         # [1], [2] ... used for citations
    node_id: uuid.UUID
    act_title: str
    act_kind: str
    act_year: int | None
    provision: str | None            # "s.37", "Art.14A"
    heading: str | None
    path: str
    page_start: int | None
    page_end: int | None
    printed_page_start: str | None
    printed_page_end: str | None
    text: str
    score: float
    amendment_notes: list[str] = field(default_factory=list)
    later_amendments: list[LaterAmendment] = field(default_factory=list)
    document_id: uuid.UUID | None = None   # for linking to the source PDF page

    def citation(self) -> str:
        page = self.printed_page_start or str(self.page_start)
        end = self.printed_page_end or str(self.page_end)
        pages = f"p. {page}" if page == end else f"pp. {page}-{end}"
        return f"{self.act_title}, {self.provision or self.path.split(' › ')[-1]}, {pages}"


@dataclass
class Definition:
    term: str
    act_title: str
    provision: str | None        # "s.38/def:computer"
    text: str
    # Where it is, so a definition can be cited and opened like a section.
    node_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    page_start: int | None = None
    page_end: int | None = None
    printed_page_start: str | None = None
    printed_page_end: str | None = None
    #: true when the question itself asks about this term ("What does 'computer' mean?")
    asked: bool = False


@dataclass
class RetrievedContext:
    blocks: list[ContextBlock]
    definitions: list[Definition]


def _body(content: str) -> str:
    """Strip the breadcrumb line the chunker prepends."""
    return content.split("\n", 1)[1] if "\n" in content else content


def build_context(
    db: Session, hits: list[Hit], query: str = "", max_sections: int = MAX_SECTIONS
) -> RetrievedContext:
    if not hits:
        return RetrievedContext([], [])
    node_ids = list({h.node_id for h in hits})

    # --- map every hit node to its enclosing section (or itself if not inside one)
    rows = db.execute(text("""
        WITH RECURSIVE up AS (
            SELECT id AS start_id, id, parent_id, level FROM legal_nodes WHERE id = ANY(:ids)
            UNION ALL
            SELECT up.start_id, n.id, n.parent_id, n.level
            FROM legal_nodes n JOIN up ON n.id = up.parent_id
            WHERE up.level <> 'section'
        )
        SELECT start_id, id FROM up WHERE level = 'section'"""), {"ids": node_ids})
    section_of = {r.start_id: r.id for r in rows}

    groups: dict[uuid.UUID, list[Hit]] = defaultdict(list)
    for h in hits:
        if h.kind == "definition":
            continue                       # handled by the definitions step
        groups[section_of.get(h.node_id, h.node_id)].append(h)

    def group_score(hs: list[Hit]) -> float:
        scores = sorted((h.score for h in hs), reverse=True)
        return scores[0] + EXTRA_PART_BONUS * sum(scores[1: 1 + MAX_EXTRA_PARTS])

    ranked = sorted(groups.items(), key=lambda kv: group_score(kv[1]), reverse=True)

    # --- load metadata for candidate units (a few extra for de-duplication)
    cand_ids = [uid for uid, _ in ranked[: max_sections * 2]]
    meta = {r.id: r for r in db.execute(text("""
        SELECT n.id, n.provision_key, n.heading, n.path, n.number, n.text AS own_text,
               n.page_start, n.page_end, n.printed_page_start, n.printed_page_end,
               n.amendment_notes, a.id AS act_id, a.title AS act_title, a.kind AS act_kind,
               a.year AS act_year, a.law_key, a.document_id,
               (SELECT c.content FROM chunks c
                 WHERE c.node_id = n.id AND c.kind = 'section' AND c.is_current LIMIT 1)
               AS section_content
        FROM legal_nodes n JOIN acts a ON a.id = n.act_id
        WHERE n.id = ANY(:ids)"""), {"ids": cand_ids})}

    blocks: list[ContextBlock] = []
    for uid, hs in ranked[: max_sections * 2]:
        m = meta.get(uid)
        if m is None:
            continue
        # Interpretation sections are huge lists; the definitions step covers them.
        if (m.heading or "").lower().startswith("interpretation") and not any(
            h.via == "ref" for h in hs
        ):
            continue
        if m.section_content:
            body = _body(m.section_content)
        else:   # section too large to include whole: use only the matching parts, in order
            body = "\n…\n".join(_body(h.content) for h in hs) or m.own_text
        # Near-identical text in the same law (e.g. Special Provisions Acts of 2007 and 2013)
        # -> keep only the most recent Act's version.
        dup = next((i for i, b in enumerate(blocks)
                    if meta[b.node_id].law_key == m.law_key and _similar(b.text, body)), None)
        if dup is not None:
            if (m.act_year or 0) <= (blocks[dup].act_year or 0):
                continue
            blocks.pop(dup)
        blocks.append(ContextBlock(
            ref=0, node_id=uid, act_title=m.act_title, act_kind=m.act_kind, act_year=m.act_year,
            provision=m.provision_key, heading=m.heading, path=m.path,
            page_start=m.page_start, page_end=m.page_end,
            printed_page_start=m.printed_page_start, printed_page_end=m.printed_page_end,
            text=body, score=group_score(hs), amendment_notes=list(m.amendment_notes or []),
            document_id=m.document_id,
        ))
        if len(blocks) == max_sections:
            break

    for i, b in enumerate(blocks, start=1):
        b.ref = i
    _attach_later_amendments(db, blocks, meta)
    definitions = _definitions(db, blocks, meta, hits, query)
    return RetrievedContext(blocks, definitions)


def _attach_later_amendments(db: Session, blocks: list[ContextBlock], meta: dict) -> None:
    law_keys = {meta[b.node_id].law_key for b in blocks if meta[b.node_id].act_kind == "principal"}
    if not law_keys:
        return
    rows = db.execute(text("""
        SELECT a.title, a.year, a.law_key, n.provision_key, n.heading,
               (SELECT c.content FROM chunks c WHERE c.node_id = n.id AND c.kind = 'section'
                 LIMIT 1) AS content
        FROM legal_nodes n JOIN acts a ON a.id = n.act_id
        WHERE a.kind = 'amendment' AND a.law_key = ANY(:keys) AND n.level = 'section'
          -- Amending sections already applied to the text (approved, nothing left open)
          -- are part of the current section now, so they are not "later" amendments.
          AND NOT (
            EXISTS (SELECT 1 FROM amendment_proposals p
                    WHERE p.amendment_node_id = n.id AND p.status = 'approved')
            AND NOT EXISTS (SELECT 1 FROM amendment_proposals p
                            WHERE p.amendment_node_id = n.id
                              AND p.status IN ('pending', 'needs_attention'))
          )
        ORDER BY a.year"""), {"keys": list(law_keys)})
    by_target: dict[tuple[str, str], list[LaterAmendment]] = defaultdict(list)
    for r in rows:
        body = _body(r.content or "")
        # Target sections come from the operative words ("Section 443 of the principal
        # enactment is hereby amended ..."), which are reliable; marginal-note headings can be
        # misplaced by the parser. Only the first sentence counts, so quoted replacement text
        # mentioning other sections is ignored.
        first_sentence = re.split(r"(?<=[:\-—–])\s|\.\s", body, maxsplit=1)[0][:400]
        targets = dict.fromkeys(n.replace(" ", "").upper()
                                for n in RE_SECTION_IN_HEADING.findall(first_sentence))
        for num in targets:
            by_target[(r.law_key, "s." + num)].append(LaterAmendment(
                r.title, r.year, r.provision_key, r.heading, body))
    for b in blocks:
        m = meta[b.node_id]
        if m.act_kind == "principal":
            b.later_amendments = by_target.get((m.law_key, b.provision or ""), [])


def _definitions(
    db: Session, blocks: list[ContextBlock], meta: dict, hits: list[Hit], query: str
) -> list[Definition]:
    act_ids = list({meta[b.node_id].act_id for b in blocks})
    directly_hit = {h.node_id for h in hits if h.kind == "definition"}
    if not act_ids and not directly_hit:
        return []
    rows = db.execute(text("""
        SELECT n.id, n.term, n.provision_key, a.title AS act_title, a.document_id,
               n.page_start, n.page_end, n.printed_page_start, n.printed_page_end,
               (SELECT c.content FROM chunks c WHERE c.node_id = n.id LIMIT 1) AS content
        FROM legal_nodes n JOIN acts a ON a.id = n.act_id
        WHERE n.level = 'definition' AND n.is_current
          AND (n.act_id = ANY(:acts) OR n.id = ANY(:hit))"""),
        {"acts": act_ids, "hit": list(directly_hit)})
    texts = [b.text.lower() for b in blocks]
    q = query.lower()
    scored: list[tuple[float, Definition]] = []
    for r in rows:
        term = (r.term or "").strip()
        low = term.lower()
        if len(low) < 4 or low in GENERIC_TERMS:
            continue
        pat = re.compile(rf"\b{re.escape(low)}\b")
        # Relevance: named in the question > used by top-ranked blocks > used anywhere.
        score = (3.0 if pat.search(q) else 0.0) + (2.0 if r.id in directly_hit else 0.0)
        score += sum(1.0 / i for i, t in enumerate(texts, start=1) if pat.search(t))
        if score > 0:
            scored.append((score, Definition(
                term, r.act_title, r.provision_key, _body(r.content or ""), node_id=r.id,
                document_id=r.document_id, page_start=r.page_start, page_end=r.page_end,
                printed_page_start=r.printed_page_start, printed_page_end=r.printed_page_end,
                asked=bool(pat.search(q)) and bool(RE_ASKS_MEANING.search(q)))))
    scored.sort(key=lambda sd: -sd[0])
    return [d for _, d in scored[:MAX_DEFINITIONS]]
