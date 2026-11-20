"""Hybrid search over current chunks: pgvector + Postgres full-text, fused with RRF.

Plain-language questions ("can the police keep me ...") rely on the vector side; exact
references ("section 37", "Article 14A") and rare legal terms rely on the keyword side and
on direct provision lookup.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.db import get_session
from backend.rag.llm.embeddings import embed_query, embed_texts

# Rank-fusion constant. The common default (60) scores rank 1 and rank 15 almost the same, so a
# section that is a middling match in many result lists beats one that is the TOP match in a
# few (e.g. a short, decisive section like CCPA s.37). 10 rewards top ranks; measured with the
# eval set (backend/eval): s.37 reached the top-12 candidates in 10/10 runs vs 8/10.
RRF_K = 10
CANDIDATES_PER_RETRIEVER = 40
# Keyword search is precise for legal terms but noisy for everyday wording ("data", "hours"),
# so it gets half the vote of the vector retriever.
VECTOR_WEIGHT = 1.0
KEYWORD_WEIGHT = 0.5
DIRECT_REF_SCORE = 1.0          # explicitly named provisions always come first

RE_REF = re.compile(
    r"\b(?P<kind>sections?|s\.|sec\.?|articles?|art\.?)\s*(?P<num>\d{1,3}\s?[A-Z]?)\b",
    re.IGNORECASE,
)
RE_WORD = re.compile(r"[a-z0-9][a-z0-9\-]{1,}")


@dataclass
class Hit:
    chunk_id: uuid.UUID
    node_id: uuid.UUID
    act_id: uuid.UUID
    kind: str
    content: str
    score: float = 0.0
    via: str = ""          # "vector", "keyword", "ref" (comma-joined when several)


def provision_refs(query: str) -> list[str]:
    """'section 37 and Art 14A' -> ['s.37', 'Art.14A']"""
    out = []
    for m in RE_REF.finditer(query):
        unit = "Art." if m.group("kind").lower().startswith("art") else "s."
        out.append(unit + m.group("num").replace(" ", "").upper())
    return out


def or_tsquery(query: str) -> str | None:
    """OR-combine query words so a partial match still ranks (AND would return nothing for
    most natural-language questions). Postgres drops stop words itself."""
    words = dict.fromkeys(RE_WORD.findall(query.lower()))
    return " | ".join(w.replace("-", " <-> ") for w in words) or None


def rrf(*ranked_lists: list[Hit], weights: list[float] | None = None) -> list[Hit]:
    """Weighted Reciprocal Rank Fusion: score = sum over lists of w / (k + rank)."""
    weights = weights or [1.0] * len(ranked_lists)
    fused: dict[uuid.UUID, Hit] = {}
    for hits, w in zip(ranked_lists, weights, strict=True):
        for rank, h in enumerate(hits, start=1):
            cur = fused.setdefault(h.chunk_id, Hit(h.chunk_id, h.node_id, h.act_id, h.kind,
                                                   h.content))
            cur.score += w / (RRF_K + rank)
            cur.via = ",".join(filter(None, dict.fromkeys(cur.via.split(",") + [h.via])))
    return sorted(fused.values(), key=lambda h: h.score, reverse=True)


_COLS = "c.id, c.node_id, c.act_id, c.kind, c.content"


def _rows_to_hits(rows, via: str) -> list[Hit]:
    return [Hit(r.id, r.node_id, r.act_id, r.kind, r.content, via=via) for r in rows]


def vector_search(db: Session, query: str, k: int = CANDIDATES_PER_RETRIEVER,
                  vector: list[float] | None = None) -> list[Hit]:
    vec = str(vector if vector is not None else embed_query(query))
    rows = db.execute(text(f"""
        SELECT {_COLS} FROM chunks c
        WHERE c.is_current
        ORDER BY c.embedding <=> CAST(:v AS vector)
        LIMIT :k"""), {"v": vec, "k": k})
    return _rows_to_hits(rows, "vector")


def keyword_search(db: Session, query: str, k: int = CANDIDATES_PER_RETRIEVER) -> list[Hit]:
    tsq = or_tsquery(query)
    if not tsq:
        return []
    rows = db.execute(text(f"""
        SELECT {_COLS} FROM chunks c, to_tsquery('english', :q) q
        WHERE c.is_current AND c.tsv @@ q
        ORDER BY ts_rank_cd(c.tsv, q, 32) DESC
        LIMIT :k"""), {"q": tsq, "k": k})
    return _rows_to_hits(rows, "keyword")


def reference_lookup(db: Session, refs: list[str]) -> list[Hit]:
    """Chunks of provisions named explicitly in the question (whole-section chunks first)."""
    if not refs:
        return []
    rows = db.execute(text(f"""
        SELECT {_COLS} FROM chunks c JOIN legal_nodes n ON n.id = c.node_id
        WHERE c.is_current AND n.provision_key = ANY(:refs)
        ORDER BY (c.kind = 'section') DESC
        LIMIT 20"""), {"refs": refs})
    return _rows_to_hits(rows, "ref")


# --------------------------------------------------------------------------- concurrency
# Every search is one round trip to the (remote) database, ~0.15s each. They are independent,
# so they run side by side on their own pooled connections instead of one after another.

_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="search")


def _in_session[T](fn: Callable[..., T], *args, **kwargs) -> T:
    with get_session() as db:
        return fn(db, *args, **kwargs)


def _submit[T](fn: Callable[..., T], *args, **kwargs) -> Future[T]:
    return _pool.submit(_in_session, fn, *args, **kwargs)


# Prefetch: the agent starts searching with the user's own words while the LLM is still
# planning, then picks the result up here. Entries are used once and expire quickly.
_PREFETCH_TTL = 120.0
_PREFETCH_MAX = 64
_prefetched: OrderedDict[str, tuple[float, Future[tuple[list[Hit], list[Hit]]]]] = OrderedDict()
_prefetch_lock = threading.Lock()


def _both_searches(db: Session, query: str) -> tuple[list[Hit], list[Hit]]:
    return vector_search(db, query), keyword_search(db, query)


def prefetch(query: str) -> None:
    """Start the vector + keyword search for `query` in the background (non-blocking)."""
    query = query.strip()
    if not query:
        return
    fut = _submit(_both_searches, query)
    with _prefetch_lock:
        _prefetched[query] = (time.monotonic(), fut)
        _prefetched.move_to_end(query)
        while len(_prefetched) > _PREFETCH_MAX:
            _prefetched.popitem(last=False)


def _take_prefetched(query: str) -> tuple[list[Hit], list[Hit]] | None:
    with _prefetch_lock:
        entry = _prefetched.pop(query.strip(), None)
    if entry is None or time.monotonic() - entry[0] > _PREFETCH_TTL:
        return None
    try:
        return entry[1].result()
    except Exception:  # noqa: BLE001 - a failed prefetch just means searching normally
        return None


def hybrid_search(db: Session, query: str | list[str], k: int = 25) -> list[Hit]:
    """Search with one or more phrasings of the question (e.g. the user's words plus an
    LLM rewrite into legal terminology) and fuse everything into one ranking.

    All searches run concurrently (keyword searches start while the embeddings are being
    computed); the fused ranking is the same as running them one by one. `db` is kept for
    the signature — each search uses its own pooled session."""
    queries = [query] if isinstance(query, str) else [q for q in query if q.strip()]
    refs_f = _submit(reference_lookup,
                     list(dict.fromkeys(r for q in queries for r in provision_refs(q))))
    ready = {q: got for q in queries if (got := _take_prefetched(q)) is not None}
    todo = list(dict.fromkeys(q for q in queries if q not in ready))
    kw_f = {q: _submit(keyword_search, q) for q in todo}
    vectors = embed_texts(todo) if todo else []    # one embeddings call for all phrasings
    vec_f = {q: _submit(vector_search, q, vector=v) for q, v in zip(todo, vectors, strict=True)}

    lists, weights = [], []
    for q in queries:                               # fixed order -> deterministic fusion
        vec_hits, kw_hits = ready[q] if q in ready else (vec_f[q].result(), kw_f[q].result())
        lists += [vec_hits, kw_hits]
        weights += [VECTOR_WEIGHT, KEYWORD_WEIGHT]
    fused = rrf(*lists, weights=weights)
    refs = refs_f.result()
    seen = {h.chunk_id for h in refs}
    for h in refs:
        h.score = DIRECT_REF_SCORE
    return (refs + [h for h in fused if h.chunk_id not in seen])[:k]
