"""Check LawBuddy against the test set of questions with known correct sections.

    uv run python eval/run_eval.py                 # retrieval check (fast, cheap)
    uv run python eval/run_eval.py --mode full     # full answers (slower, more LLM calls)
    uv run python eval/run_eval.py --only custody-24h,hacking

Modes
  retrieval  Runs the agent's planning step (1 small LLM call) and search for each question and
             checks that the expected sections are among the candidates the answer step can use.
  full       Runs the real agent (3 LLM calls per question) and checks that the answer CITES the
             expected sections, mentions the key facts, classifies greetings/off-topic correctly
             and says when the library doesn't cover a question.

Each run is saved in backend/eval/results/ and compared with the previous run of the same
mode. The exit code is 1 if a question that passed last time fails now (a regression), so the
script can guard changes in CI.

Test cases live in golden.jsonl, one JSON object per line:
  id, question
  expect           [[act title (or part of it), provision]], e.g. [["Computer Crime Act", "s.3"]]
  expect_mode      "all" (default) or "any": all / at least one expected section must be found
  expect_definition  true if the answer comes from a definition (checked via retrieved definitions)
  must_mention     [[phrase, alternative, …], …]: each group must appear in the answer (full mode)
  expect_category  "greeting" / "off_topic" for non-legal messages
  expect_not_covered  true if the library has no law for this; the answer must say so
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden.jsonl"
RESULTS = HERE / "results"
NOT_COVERED_PHRASES = ("couldn't find", "could not find", "couldn’t find", "not include",
                       "don't include", "do not include", "doesn’t include", "doesn't include",
                       "not cover", "doesn't cover", "doesn’t cover", "no provision",
                       "not in the library", "not available")


def load_cases(only: set[str] | None) -> list[dict]:
    cases = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    ready = [c for c in cases if c.get("expect") or c.get("expect_category")
             or c.get("expect_not_covered")]
    skipped = len(cases) - len(ready)
    if skipped:
        print(f"Skipping {skipped} case(s) with no expectations filled in yet.")
    return [c for c in ready if not only or c["id"] in only]


def _matches(expected: list[str], items: list[dict], key: str = "provision") -> int | None:
    """1-based position of the expected [act, provision] in items, or None."""
    act, prov = expected
    for i, it in enumerate(items, start=1):
        item_prov = (it.get(key) or "").split("/def:")[0]
        if item_prov == prov and act.lower() in (it.get("act_title") or "").lower():
            return i
    return None


def _expect_ok(case: dict, found: list[int | None]) -> bool:
    if not case.get("expect"):
        return True
    hits = [f is not None for f in found]
    return any(hits) if case.get("expect_mode") == "any" else all(hits)


# ---- modes ------------------------------------------------------------------------------

def run_retrieval(case: dict) -> dict:
    from backend.rag.graph import nodes

    t0 = time.time()
    state: dict = {"question": case["question"], "history": []}
    state.update(nodes.plan(state))
    out: dict = {"category": state["category"]}
    problems = []
    if case.get("expect_category"):
        if state["category"] != case["expect_category"]:
            problems.append(f"classified as {state['category']}, expected {case['expect_category']}")
    elif state["category"] != "legal":
        problems.append(f"classified as {state['category']}, expected a legal question")
    if case.get("expect"):
        state.update(nodes.retrieve(state))
        pool = state["candidates"] + ([{"provision": d["provision"], "act_title": d["act_title"]}
                                        for d in state["definitions"]] if case.get("expect_definition") else [])
        found = [_matches(e, pool) for e in case["expect"]]
        out["ranks"] = {f"{e[1]}": r for e, r in zip(case["expect"], found, strict=True)}
        out["candidates"] = [c["provision"] for c in state["candidates"]]
        if not _expect_ok(case, found):
            missing = [e[1] for e, r in zip(case["expect"], found, strict=True) if r is None]
            problems.append(f"not among the {len(state['candidates'])} candidates: {', '.join(missing)}")
    out.update(passed=not problems, problems=problems, seconds=round(time.time() - t0, 1))
    if case.get("expect_not_covered") and not case.get("expect"):
        out["note"] = "checked in full mode only"
    return out


def run_full(case: dict) -> dict:
    from backend.rag.api import LawAgent

    t0 = time.time()
    res = LawAgent().ask(case["question"], thread_id=f"eval-{uuid.uuid4().hex[:8]}")
    answer, cites = res.get("answer", ""), res.get("citations", [])
    low = answer.lower()
    problems = []
    if case.get("expect_category") and res.get("category") != case["expect_category"]:
        problems.append(f"classified as {res.get('category')}, expected {case['expect_category']}")
    if case.get("expect_not_covered"):
        said_so = any(p in low for p in NOT_COVERED_PHRASES)
        if not said_so:
            problems.append("didn't say the library doesn't cover this"
                            + (f" (cited {', '.join(c['provision'] or '?' for c in cites)})" if cites else ""))
    if case.get("expect") and not case.get("expect_definition"):
        found = [_matches(e, cites) for e in case["expect"]]
        if not _expect_ok(case, found):
            missing = [e[1] for e, r in zip(case["expect"], found, strict=True) if r is None]
            problems.append(f"didn't cite {', '.join(missing)} (cited "
                            f"{', '.join(c['provision'] or '?' for c in cites) or 'nothing'})")
    for group in case.get("must_mention", []):
        if not any(p.lower() in low for p in group):
            problems.append(f"didn't mention {' / '.join(group)}")
    return {"passed": not problems, "problems": problems, "category": res.get("category"),
            "cited": [f"{c['provision']} ({c['act_title'][:40]})" for c in cites],
            "answer": answer, "seconds": round(time.time() - t0, 1)}


# ---- reporting ---------------------------------------------------------------------------

def previous_run(mode: str) -> dict | None:
    runs = sorted(RESULTS.glob(f"{mode}-*.json"))
    return json.loads(runs[-1].read_text(encoding="utf-8")) if runs else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["retrieval", "full"], default="retrieval")
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--workers", type=int, default=4, help="questions evaluated in parallel")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each question N times; it passes only if every run passes "
                         "(shows unstable answers as e.g. 2/3)")
    args = ap.parse_args()

    import logging
    logging.disable(logging.WARNING)

    cases = load_cases(set(args.only.split(",")) if args.only else None)
    if not cases:
        print("No matching test cases.")
        return 2
    runner = run_full if args.mode == "full" else run_retrieval
    print(f"Running {len(cases)} cases in {args.mode} mode…\n")

    t0 = time.time()

    def safe(case: dict) -> dict:
        try:
            return runner(case)
        except Exception as e:  # noqa: BLE001 - one broken case must not stop the run
            return {"passed": False, "problems": [f"error: {type(e).__name__}: {e}"]}

    repeat = max(1, args.repeat)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        flat = list(pool.map(safe, [c for c in cases for _ in range(repeat)]))
    outcomes = []
    for k in range(len(cases)):
        runs = flat[k * repeat:(k + 1) * repeat]
        ok = sum(r["passed"] for r in runs)
        first_fail = next((r for r in runs if not r["passed"]), runs[0])
        outcomes.append({**first_fail, "passed": ok == repeat,
                         "runs_passed": f"{ok}/{repeat}" if repeat > 1 else None,
                         "problems": first_fail.get("problems", [])})

    results = {c["id"]: {"question": c["question"], **o} for c, o in zip(cases, outcomes, strict=True)}
    passed = sum(r["passed"] for r in results.values())

    width = max(len(i) for i in results)
    for cid, r in results.items():
        mark = "PASS" if r["passed"] else "FAIL"
        extra = ""
        if r.get("ranks"):
            extra = "  rank " + ", ".join(f"{k}={v or '-'}" for k, v in r["ranks"].items())
        runs = f"  [{r['runs_passed']} runs passed]" if r.get("runs_passed") else ""
        print(f"{mark}  {cid:{width}}  {r.get('seconds', '?')}s{extra}{runs}")
        for p in r.get("problems", []):
            print(f"      - {p}")

    prev = previous_run(args.mode)
    regressions, fixed = [], []
    if prev:
        for cid, r in results.items():
            before = prev["results"].get(cid)
            if before is None:
                continue
            if before["passed"] and not r["passed"]:
                regressions.append(cid)
            elif not before["passed"] and r["passed"]:
                fixed.append(cid)

    print(f"\n{passed}/{len(results)} passed ({100 * passed / len(results):.0f}%) "
          f"in {time.time() - t0:.0f}s")
    if prev:
        print(f"Compared with {prev['run_at']} ({prev['passed']}/{prev['total']}): "
              f"{len(regressions)} worse, {len(fixed)} better")
        for cid in regressions:
            print(f"  WORSE   {cid}")
        for cid in fixed:
            print(f"  BETTER  {cid}")

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"{args.mode}-{stamp}.json"
    out.write_text(json.dumps({"mode": args.mode, "run_at": stamp, "passed": passed,
                               "total": len(results), "results": results}, indent=2,
                              ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out.relative_to(HERE.parent.parent)}")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
