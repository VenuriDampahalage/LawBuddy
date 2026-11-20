"""Hierarchical chunking: legal tree -> rows for legal_nodes + retrieval chunks.

Chunk kinds
  leaf        subsection-sized piece (precise matching). Oversized subsections are split by
              paragraph, each piece keeping the subsection's lead-in words for context.
  section     a whole section (broad questions, and the unit auto-merge expands to).
              Small sections with no subsections produce only this chunk (no duplicate leaf).
  definition  one per defined term ("“peace officer” includes a police officer ...")

Every chunk's content starts with its breadcrumb, so the embedding knows which Act, Part
and section the text comes from.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken

from backend.rag.ingestion.structure import Node

LEAF_MAX_TOKENS = 600
SECTION_MAX_TOKENS = 2000
PREAMBLE_MAX_TOKENS = 800      # longer act-level text is a table of contents, not a preamble
HARD_MAX_TOKENS = 6000         # safety net below the embedding model's 8191 limit
WINDOW_TOKENS = 500
MIN_CHUNK_TOKENS = 8
SMALL_WORDS = {"of", "the", "and", "in", "to", "for", "on", "by", "or", "a", "an"}


@lru_cache
def _enc() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")  # tokenizer of text-embedding-3-*


def count_tokens(text: str) -> int:
    return len(_enc().encode(text))


# --------------------------------------------------------------------------- act metadata

RE_ACT_NO = re.compile(r"No\.?\s*(\d+)\s+of\s+(\d{4})", re.IGNORECASE)


@dataclass
class ActMeta:
    title: str
    kind: str              # principal | amendment | special | constitution
    law_key: str
    act_number: int | None
    year: int | None


def act_meta(title: str) -> ActMeta:
    t = re.sub(r"\s+", " ", title).strip()
    letters = [c for c in t if c.isalpha()]
    mostly_upper = letters and sum(c.isupper() for c in letters) / len(letters) > 0.7
    pretty = t.title() if mostly_upper else t        # "COMPUTER CRIME ACT, No. 24 OF 2007"
    words = pretty.split(" ")
    pretty = " ".join([words[0]] + [w.lower() if w.lower() in SMALL_WORDS else w
                                    for w in words[1:]])
    m = RE_ACT_NO.search(t)
    number, year = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    low = t.lower()
    if "constitution" in low:
        kind = "constitution"
    elif "(amendment)" in low or re.search(r"\bamendment\)?\s+act\b", low):
        kind = "amendment"
    elif "special provisions" in low:
        kind = "special"
    else:
        kind = "principal"
    base = RE_ACT_NO.sub("", low)
    base = re.sub(r"\(amendment\)|\bamendment\b|,", " ", base)
    base = re.sub(r"\bact\b|\bthe\b", " ", base)
    law_key = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return ActMeta(pretty, kind, law_key, number, year)


# --------------------------------------------------------------------------- output rows

@dataclass
class NodeRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    level: str
    number: str | None
    heading: str | None
    term: str | None
    provision_key: str | None
    path: str
    ord: int
    text: str
    page_start: int | None
    page_end: int | None
    printed_page_start: str | None
    printed_page_end: str | None
    amendment_notes: list[str]


@dataclass
class ChunkRow:
    node_id: uuid.UUID
    kind: str
    content: str
    token_count: int


@dataclass
class ChunkedAct:
    meta: ActMeta
    page_start: int | None
    page_end: int | None
    nodes: list[NodeRow] = field(default_factory=list)
    chunks: list[ChunkRow] = field(default_factory=list)


# --------------------------------------------------------------------------- helpers

def _segment(n: Node) -> str:
    """Breadcrumb segment for one node."""
    if n.level == "section":
        return f"{n.label()} — {n.heading}" if n.heading else n.label()
    if n.level in ("part", "chapter"):
        return f"{n.label()} — {n.heading}" if n.heading and n.number else n.label()
    if n.level == "group":
        return n.heading or n.label()
    return n.label()


def _provision_key(n: Node, ancestors: tuple[Node, ...]) -> str | None:
    if n.level in ("act", "part", "chapter", "group"):
        return None
    sched = next((a for a in ancestors if a.level == "schedule"), None)
    prefix = f"{sched.heading}/" if sched and n.level != "schedule" else ""
    if n.level == "schedule":
        return n.heading
    sec = n if n.level == "section" else next((a for a in reversed(ancestors)
                                                if a.level == "section"), None)
    if sec is None:
        return None
    key = f"{prefix}{sec.unit}{sec.number}"
    chain = [a for a in ancestors if a.level in ("subsection", "paragraph", "subparagraph")]
    if n.level in ("subsection", "paragraph", "subparagraph"):
        chain.append(n)
    key += "".join(c.number or "" for c in chain)
    if n.level == "definition":
        key += f"/def:{(n.term or '').lower()}"
    elif n.level == "explanation":
        key += f"/{(n.heading or 'explanation').lower().replace(' ', '')}"
    return key


def _fmt(breadcrumb: str, body: str, notes: list[str] | None = None) -> str:
    text = f"{breadcrumb}\n{body.strip()}"
    if notes:
        text += "\n[Amendment history: " + "; ".join(dict.fromkeys(notes)) + "]"
    return text


# --------------------------------------------------------------------------- main

def chunk_act(act: Node) -> ChunkedAct:
    meta = act_meta(act.heading or "Untitled Act")
    out = ChunkedAct(meta=meta, page_start=act.page_start, page_end=act.page_end)
    ids: dict[int, uuid.UUID] = {}

    # 1) flatten the tree into legal_nodes rows (reading order)
    for order, (n, anc) in enumerate(act.walk()):
        nid = uuid.uuid4()
        ids[id(n)] = nid
        crumbs = [meta.title] + [_segment(a) for a in anc[1:]] + ([_segment(n)] if anc else [])
        out.nodes.append(NodeRow(
            id=nid,
            parent_id=ids[id(anc[-1])] if anc else None,
            level=n.level,
            number=n.number,
            heading=n.heading if n.level != "act" else meta.title,
            term=n.term,
            provision_key=_provision_key(n, anc),
            path=" › ".join(crumbs),
            ord=order,
            text=n.text,
            page_start=n.page_start,
            page_end=n.page_end,
            printed_page_start=n.printed_page_start,
            printed_page_end=n.printed_page_end,
            amendment_notes=list(dict.fromkeys(n.footnotes)),
        ))
    path_of = {row.id: row.path for row in out.nodes}

    def add(node: Node, kind: str, body: str, notes: list[str] | None = None) -> None:
        crumb = path_of[ids[id(node)]]
        content = _fmt(crumb, body, notes)
        tokens = count_tokens(content)
        if tokens > HARD_MAX_TOKENS:                       # never exceed the embedding limit
            toks = _enc().encode(body)
            for i in range(0, len(toks), WINDOW_TOKENS):
                piece = _enc().decode(toks[max(0, i - 50): i + WINDOW_TOKENS])
                add(node, kind, piece, notes)
            return
        if tokens >= MIN_CHUNK_TOKENS:
            out.chunks.append(ChunkRow(ids[id(node)], kind, content, tokens))

    # 2) chunks
    preamble_tokens = count_tokens(act.text) if act.text else 0
    if 20 <= preamble_tokens <= PREAMBLE_MAX_TOKENS:       # long title / preamble
        add(act, "section", act.text)

    for n, _anc in act.walk():
        if n.level == "definition":
            add(n, "definition", n.full_text())
            continue
        if n.level != "section":
            continue

        full = n.full_text()
        notes = list(n.footnotes)
        full_tokens = count_tokens(full)
        subsections = [c for c in n.children if c.level == "subsection"]

        if full_tokens <= SECTION_MAX_TOKENS:
            add(n, "section", full, notes)
        if not subsections and full_tokens <= LEAF_MAX_TOKENS:
            continue                                       # the section chunk is the leaf

        if subsections:
            if n.text:                                     # lead-in before (1)
                add(n, "leaf", n.text, notes)
            for sub in subsections:
                _leaf_chunks(sub, add, notes)
            for other in (c for c in n.children if c.level not in ("subsection", "definition")):
                add(other, "leaf", other.full_text(), notes)
        else:
            _leaf_chunks(n, add, notes, include_own=True)
    return out


def _leaf_chunks(node: Node, add, notes: list[str], include_own: bool = False) -> None:
    """One leaf for `node`, or one per child paragraph if it is too large."""
    full = node.full_text()
    if count_tokens(full) <= LEAF_MAX_TOKENS:
        add(node, "leaf", full, notes)
        return
    lead = node.text
    kids = [c for c in node.children if c.level != "definition"]
    if not kids:                                           # one huge block: window it
        words, step = full.split(), 350
        for i in range(0, len(words), step):
            add(node, "leaf", " ".join(words[max(0, i - 40): i + step]), notes)
        return
    if include_own and lead:
        add(node, "leaf", lead, notes)
    lead_in = (lead[:300] + " …\n") if lead else ""
    for c in kids:
        body = c.full_text()
        if count_tokens(body) > LEAF_MAX_TOKENS and c.children:
            _leaf_chunks(c, add, notes)
        else:
            add(c, "leaf", lead_in + body, notes)
