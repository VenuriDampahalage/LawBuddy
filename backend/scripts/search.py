"""Show what the retriever would hand to the LLM for a question.

    uv run python scripts/search.py "Can the police keep me in custody for 2 days?"
"""

import sys

from backend.core.db import get_session
from backend.rag.retrieval.context import build_context
from backend.rag.retrieval.search import hybrid_search


def main() -> None:
    query = " ".join(sys.argv[1:]) or "What happens if someone hacks into my computer?"
    with get_session() as db:
        hits = hybrid_search(db, query)
        ctx = build_context(db, hits, query)
    print(f"Q: {query}\n")
    for b in ctx.blocks:
        print(f"[{b.ref}] {b.citation()}  — {b.heading or ''}  (score {b.score:.4f})")
        print(f"     PDF pages {b.page_start}-{b.page_end} | {len(b.text)} chars")
        for n in b.amendment_notes[:3]:
            print(f"     history: {n}")
        for la in b.later_amendments:
            print(f"     LATER AMENDMENT: {la.act_title} {la.provision} — {la.heading}")
    print("\nDefinitions:", ", ".join(f"“{d.term}” ({d.provision})" for d in ctx.definitions) or "-")


if __name__ == "__main__":
    main()
