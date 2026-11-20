"""Graph nodes. Each takes the state and returns a partial update.

Progress and answer tokens are pushed to the caller with LangGraph's stream writer:
    {"type": "status", "stage": "..."}   and   {"type": "token", "text": "..."}
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import asdict

from langgraph.config import get_stream_writer

from backend.core.config import get_settings
from backend.core.db import get_session
from backend.rag.graph import prompts
from backend.rag.graph.state import AgentState, Broaden, Plan, Selection, Turn
from backend.rag.llm.chat import stream_text, structured
from backend.rag.retrieval import search
from backend.rag.retrieval.context import ContextBlock, build_context

MAX_CANDIDATES = 12
MAX_HITS = 40
MAX_SELECTED = 6
MAX_ATTEMPTS = 1            # how many times we broaden the search before giving up
HISTORY_TURNS = 6
EXCERPT_CHARS = 900
RE_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _emit(event: dict) -> None:
    # RuntimeError: called outside a graph run (e.g. a node unit-tested directly)
    with contextlib.suppress(RuntimeError):
        get_stream_writer()(event)


def _history_text(state: AgentState, turns: int = HISTORY_TURNS, clip: int = 600) -> str:
    hist = state.get("history", [])[-turns:]
    if not hist:
        return "(no earlier messages)"
    return "\n".join(f"{'User' if t['role'] == 'user' else 'LawBuddy'}: {t['content'][:clip]}"
                     for t in hist)


def _source(b: ContextBlock) -> dict:
    d = asdict(b)
    d["node_id"] = str(b.node_id)
    d["document_id"] = str(b.document_id) if b.document_id else None
    d["citation"] = b.citation()
    return d


def _definition_source(d) -> dict:
    """A definition shaped like a section source (citable, with pages and a PDF link)."""
    section = (d.provision or "").split("/def:")[0] or None
    page = d.printed_page_start or (str(d.page_start) if d.page_start else "")
    citation = f"{d.act_title}, {section}" + (f", p. {page}" if page else "") + f" (definition of “{d.term}”)"
    return {
        "ref": 0, "node_id": str(d.node_id) if d.node_id else None, "act_title": d.act_title,
        "act_kind": None, "act_year": None, "provision": section,
        "heading": f"Definition of “{d.term}”", "path": "", "page_start": d.page_start,
        "page_end": d.page_end, "printed_page_start": d.printed_page_start,
        "printed_page_end": d.printed_page_end, "text": d.text, "score": 0.0,
        "amendment_notes": [], "later_amendments": [],
        "document_id": str(d.document_id) if d.document_id else None, "citation": citation,
    }


def _turns(question: str, answer: str) -> list[Turn]:
    return [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]


# --------------------------------------------------------------------------- nodes

def _first_query(state: AgentState) -> str:
    """The main search phrasing. A first message is searched in the user's own words, so that
    search can start before planning finishes; a follow-up ("and what about bail?") needs the
    planner's standalone rewrite."""
    if not state.get("history"):
        return state["question"]
    return state.get("standalone_question") or state["question"]


def plan(state: AgentState) -> dict:
    _emit({"type": "status", "stage": "understanding"})
    if not state.get("history"):
        search.prefetch(state["question"])     # runs during the LLM call below
    out = structured(
        prompts.PLAN,
        f"Conversation so far:\n{_history_text(state)}\n\nNew message: {state['question']}",
        Plan,
        effort=get_settings().plan_effort or None,
    )
    return {
        "category": out.category,
        "standalone_question": out.standalone_question.strip() or state["question"],
        "search_queries": [q for q in out.search_queries if q.strip()][:3],
    }


def retrieve(state: AgentState) -> dict:
    _emit({"type": "status", "stage": "searching"})
    question = state.get("standalone_question") or state["question"]
    queries = [_first_query(state), *state.get("search_queries", [])]
    with get_session() as db:
        ctx = build_context(db, search.hybrid_search(db, queries, k=MAX_HITS), question,
                            max_sections=MAX_CANDIDATES)
    # Definitions the question asks about ("What does 'computer' mean?") are candidates in
    # their own right, so they can be selected and cited like sections. The rest stay as
    # background for understanding terms.
    asked = [d for d in ctx.definitions if d.asked]
    return {
        "candidates": [_source(b) for b in ctx.blocks] + [_definition_source(d) for d in asked],
        "definitions": [asdict(d) for d in ctx.definitions if not d.asked],
    }


def select(state: AgentState) -> dict:
    cands = state.get("candidates", [])
    if not cands:
        return {"selected": [], "sufficient": False, "missing": "no candidates found"}
    _emit({"type": "status", "stage": "checking"})
    listing = "\n\n".join(
        f"[{i}] {c['citation']} — {c.get('heading') or ''}\n{c['text'][:EXCERPT_CHARS]}"
        for i, c in enumerate(cands, start=1)
    )
    out = structured(
        prompts.SELECT,
        f"Question: {state.get('standalone_question') or state['question']}\n\n"
        f"Candidates:\n{listing}",
        Selection,
        effort=get_settings().select_effort or None,
    )
    picked = list(dict.fromkeys(i for i in out.relevant if 1 <= i <= len(cands)))
    selected = [cands[i - 1] for i in picked][:MAX_SELECTED]
    return {"selected": selected, "sufficient": bool(selected) and out.sufficient,
            "missing": out.missing}


def broaden(state: AgentState) -> dict:
    _emit({"type": "status", "stage": "searching_again"})
    out = structured(
        prompts.BROADEN,
        f"Question: {state.get('standalone_question')}\n"
        f"Earlier queries: {state.get('search_queries')}\n"
        f"What was missing: {state.get('missing')}",
        Broaden,
    )
    return {"search_queries": out.search_queries[:3], "attempts": state.get("attempts", 0) + 1}


def answer(state: AgentState) -> dict:
    _emit({"type": "status", "stage": "writing"})
    sources = state["selected"]
    lines = []
    for i, s in enumerate(sources, start=1):
        head = f"[{i}] {s['citation']}" + (f" — {s['heading']}" if s.get("heading") else "")
        block = [head]
        if s.get("amendment_notes"):
            block.append("Amendment history: " + "; ".join(s["amendment_notes"][:5]))
        for la in s.get("later_amendments", []):
            block.append(f"LATER AMENDMENT by {la['act_title']} ({la['provision']} — "
                         f"{la['heading']}):\n{la['text']}")
        block.append("Text:\n" + s["text"])
        lines.append("\n".join(block))
    defs = state.get("definitions", [])
    if defs:
        lines.append("Definitions (for understanding terms; cite the section they belong to):\n"
                     + "\n".join(f"- {d['act_title']} {d['provision']}: {d['text']}" for d in defs))

    user_input = (
        f"Conversation so far (context only):\n{_history_text(state, 4)}\n\n"
        f"Question: {state.get('standalone_question') or state['question']}\n\n"
        "Sources:\n\n" + "\n\n".join(lines)
    )
    parts: list[str] = []
    for delta in stream_text(prompts.ANSWER, user_input, effort=get_settings().answer_effort or None):
        parts.append(delta)
        _emit({"type": "token", "text": delta})
    text, citations = verify_citations("".join(parts), sources)
    return {"answer": text, "citations": citations,
            "history": _turns(state["question"], text)}


def chit_chat(state: AgentState) -> dict:
    instructions = prompts.GREETING if state.get("category") == "greeting" else prompts.OFF_TOPIC
    parts: list[str] = []
    for delta in stream_text(instructions, state["question"]):
        parts.append(delta)
        _emit({"type": "token", "text": delta})
    text = "".join(parts)
    return {"answer": text, "citations": [], "history": _turns(state["question"], text)}


def not_found(state: AgentState) -> dict:
    _emit({"type": "token", "text": prompts.NOT_FOUND})
    return {"answer": prompts.NOT_FOUND, "citations": [],
            "history": _turns(state["question"], prompts.NOT_FOUND)}


# --------------------------------------------------------------------------- routing

def route_after_plan(state: AgentState) -> str:
    return "retrieve" if state.get("category") == "legal" else "chit_chat"


def route_after_select(state: AgentState) -> str:
    if state.get("selected"):
        return "answer"          # partial coverage is handled by the answer prompt
    if state.get("attempts", 0) < MAX_ATTEMPTS:
        return "broaden"
    return "not_found"


# --------------------------------------------------------------------------- citations

def verify_citations(text: str, sources: list[dict]) -> tuple[str, list[dict]]:
    """Drop citation markers that point at no source; list the sources actually cited,
    in order of first use."""
    valid = set(range(1, len(sources) + 1))
    used: list[int] = []

    def fix(m: re.Match) -> str:
        nums = [int(n) for n in re.split(r"\s*,\s*", m.group(1))]
        keep = [n for n in nums if n in valid]
        used.extend(n for n in keep if n not in used)
        return "".join(f"[{n}]" for n in keep)

    cleaned = RE_CITE.sub(fix, text)
    citations = []
    for n in used:
        s = sources[n - 1]
        citations.append({
            "ref": n,
            "citation": s["citation"],
            "act_title": s["act_title"],
            "provision": s["provision"],
            "heading": s.get("heading"),
            "document_id": s.get("document_id"),
            "page_start": s["page_start"],
            "page_end": s["page_end"],
            "printed_page_start": s.get("printed_page_start"),
            "printed_page_end": s.get("printed_page_end"),
            "excerpt": s["text"][:400],
            "amended_by": [la["act_title"] for la in s.get("later_amendments", [])],
        })
    return cleaned, citations
