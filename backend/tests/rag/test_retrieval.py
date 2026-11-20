"""Unit tests for the pure retrieval helpers (no database or API calls)."""

import time
import uuid
from concurrent.futures import Future

from backend.rag.graph.nodes import _first_query
from backend.rag.retrieval import search
from backend.rag.retrieval.context import _similar
from backend.rag.retrieval.search import Hit, or_tsquery, provision_refs, rrf


def test_provision_refs():
    assert provision_refs("What does Article 14A say?") == ["Art.14A"]
    assert provision_refs("compare section 37 and s. 115 and Art 13") == ["s.37", "s.115", "Art.13"]
    assert provision_refs("my neighbour's dog bit me") == []


def test_or_tsquery_joins_words_with_or():
    assert or_tsquery("Bail for non-bailable offence?") == "bail | for | non <-> bailable | offence"
    assert or_tsquery("??") is None


def _hit(name: str) -> Hit:
    return Hit(uuid.uuid5(uuid.NAMESPACE_DNS, name), uuid.uuid4(), uuid.uuid4(), "leaf", name)


def test_weighted_rrf_prefers_agreement_and_weights():
    a, b, c = _hit("a"), _hit("b"), _hit("c")
    fused = rrf([a, b], [b, c], weights=[1.0, 0.5])
    assert [h.content for h in fused] == ["b", "a", "c"]   # b is found by both retrievers
    assert fused[0].score > fused[1].score > fused[2].score


def _done(value) -> Future:
    f: Future = Future()
    f.set_result(value)
    return f


def test_prefetched_results_are_used_once_and_expire():
    lists = ([_hit("v")], [_hit("k")])
    search._prefetched["bail?"] = (time.monotonic(), _done(lists))
    assert search._take_prefetched(" bail? ") == lists
    assert search._take_prefetched("bail?") is None            # used once
    search._prefetched["old"] = (time.monotonic() - search._PREFETCH_TTL - 1, _done(lists))
    assert search._take_prefetched("old") is None              # expired
    failed: Future = Future()
    failed.set_exception(RuntimeError("db down"))
    search._prefetched["broken"] = (time.monotonic(), failed)
    assert search._take_prefetched("broken") is None           # falls back to searching


def test_first_query_uses_own_words_only_for_a_first_message():
    first = {"question": "Can police hold me?", "standalone_question": "Detention period?",
             "history": []}
    assert _first_query(first) == "Can police hold me?"
    follow = {**first, "question": "and bail?", "standalone_question": "Is bail available?",
              "history": [{"role": "user", "content": "x"}]}
    assert _first_query(follow) == "Is bail available?"


def test_similar_detects_near_duplicate_sections():
    t2007 = ("any peace officer shall not detain in custody a person arrested without a warrant "
             "for a longer period than twenty-four hours exclusive of the journey")
    t2013 = t2007.replace("twenty-four", "twenty four")
    assert _similar(t2007, t2013)
    assert not _similar(t2007, "the Minister may by regulations prescribe the form of the order")
