"""Chat with LawBuddy in the terminal (streams the answer, keeps conversation memory).

    uv run python scripts/chat.py                 # new conversation
    uv run python scripts/chat.py --thread demo1  # resume a conversation
    uv run python scripts/chat.py --once "Can the police hold me for 3 days?"
"""

import argparse
import sys
import uuid

from backend.rag.api import LawAgent

STAGES = {"understanding": "understanding your question", "searching": "searching the law",
          "searching_again": "searching more broadly", "checking": "checking relevance",
          "writing": "writing the answer"}


def run_turn(agent: LawAgent, question: str, thread: str) -> None:
    for ev in agent.stream(question, thread):
        if ev["type"] == "status":
            print(f"  … {STAGES.get(ev['stage'], ev['stage'])}", file=sys.stderr, flush=True)
        elif ev["type"] == "token":
            print(ev["text"], end="", flush=True)
        elif ev["type"] == "done":
            print("\n")
            if ev.get("standalone_question"):
                print(f"  (interpreted as: {ev['standalone_question']})")
            for c in ev["citations"]:
                amended = f"  — amended by {', '.join(c['amended_by'])}" if c["amended_by"] else ""
                print(f"  [{c['ref']}] {c['citation']} — {c['heading'] or ''} "
                      f"(PDF p.{c['page_start']}){amended}")
            print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", default=None)
    ap.add_argument("--once", default=None)
    args = ap.parse_args()
    thread = args.thread or uuid.uuid4().hex[:8]
    with LawAgent.connect() as agent:
        if args.once:
            run_turn(agent, args.once, thread)
            return
        print(f"LawBuddy (conversation {thread}). Empty line to quit.\n")
        while (q := input("You: ").strip()):
            print("\nLawBuddy: ", end="")
            run_turn(agent, q, thread)


if __name__ == "__main__":
    main()
