"""Print the detected legal hierarchy for a parsed PDF (Phase 0/2 debugging aid).

    uv run python scripts/show_tree.py constitution.pdf --depth 2
"""

import argparse

from backend.core.config import get_settings
from backend.rag.ingestion.parser import parse_pdf
from backend.rag.ingestion.structure import build_tree, outline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--depth", type=int, default=2)
    args = ap.parse_args()
    doc = parse_pdf(get_settings().raw_pdf_dir / args.file)   # cached: no API call
    for act in build_tree(doc):
        n_sec = sum(1 for n, _ in act.walk() if n.level == "section")
        n_def = sum(1 for n, _ in act.walk() if n.level == "definition")
        print(f"\n######## {act.heading}  — {n_sec} sections, {n_def} definitions")
        print(outline(act, args.depth))


if __name__ == "__main__":
    main()
