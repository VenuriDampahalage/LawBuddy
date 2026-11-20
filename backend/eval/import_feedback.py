"""Turn answers users rated 👎 into draft test cases.

    uv run python eval/import_feedback.py

Writes backend/eval/drafts.jsonl (not committed to git: it contains real users'
questions). For each draft:
  1. remove or reword any personal details in the question;
  2. look up which sections a correct answer must use and fill in "expect"
     (and "must_mention" if useful);
  3. move the line into golden.jsonl.
Drafts with an empty "expect" are skipped by run_eval.py until you fill them in.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from backend.core.db import get_engine

HERE = Path(__file__).resolve().parent
GOLDEN, DRAFTS = HERE / "golden.jsonl", HERE / "drafts.jsonl"


def _questions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["question"].strip().lower()
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def main() -> None:
    known = _questions(GOLDEN) | _questions(DRAFTS)
    with get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT m.id, m.created_at, m.citations,
                   (SELECT u.content FROM messages u
                     WHERE u.conversation_id = m.conversation_id AND u.role = 'user'
                       AND u.created_at <= m.created_at
                     ORDER BY u.created_at DESC LIMIT 1) AS question
            FROM messages m
            WHERE m.role = 'assistant' AND m.feedback = -1
            ORDER BY m.created_at DESC""")).all()

    new = []
    for r in rows:
        q = (r.question or "").strip()
        if not q or q.lower() in known:
            continue
        known.add(q.lower())
        cited = ", ".join(f"{c.get('provision')} ({(c.get('act_title') or '')[:40]})"
                          for c in (r.citations or []))
        new.append({"id": f"feedback-{str(r.id)[:8]}", "question": q, "expect": [],
                    "must_mention": [],
                    "notes": f"Rated not helpful on {r.created_at:%Y-%m-%d}. "
                             f"The answer cited: {cited or 'nothing'}."})

    with DRAFTS.open("a", encoding="utf-8") as f:
        for d in new:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"{len(rows)} answers rated not helpful; {len(new)} new draft(s) added to {DRAFTS.name}.")
    if new:
        print("Fill in each draft's \"expect\", remove personal details, then move it to golden.jsonl.")


if __name__ == "__main__":
    main()
