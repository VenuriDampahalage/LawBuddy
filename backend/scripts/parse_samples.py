"""Phase 0: parse sample PDFs with LlamaParse and write readable markdown for review.

Usage (from repo root):
    uv run python scripts/parse_samples.py                      # all PDFs, default tier
    uv run python scripts/parse_samples.py --file constitution.pdf --pages "150-155"
    uv run python scripts/parse_samples.py --tier agentic --pages "1-5"

Output: data/parsed/review/<pdf-name>.<tier>.md  (one '---- PDF PAGE n ----' block per page)
"""

import argparse
from pathlib import Path

from backend.core.config import get_settings
from backend.rag.ingestion.parser import parse_pdf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="single PDF name inside data/raw_pdfs")
    ap.add_argument("--tier", help="fast | cost_effective | agentic | agentic_plus")
    ap.add_argument("--pages", help='LlamaParse target_pages, e.g. "1-5" or "1,3,10-12"')
    ap.add_argument("--force", action="store_true", help="ignore cache and re-parse")
    args = ap.parse_args()

    s = get_settings()
    files = [s.raw_pdf_dir / args.file] if args.file else sorted(s.raw_pdf_dir.glob("*.pdf"))
    out_dir = s.parsed_dir / "review"
    out_dir.mkdir(parents=True, exist_ok=True)

    for pdf in files:
        print(f"Parsing {pdf.name} ...", flush=True)
        doc = parse_pdf(pdf, tier=args.tier, target_pages=args.pages, force=args.force)
        tag = doc.tier + (f".p{args.pages}" if args.pages else "")
        out = out_dir / f"{Path(pdf.name).stem}.{tag}.md"
        with out.open("w", encoding="utf-8") as f:
            for p in doc.pages:
                f.write(f"\n\n---- PDF PAGE {p.pdf_page} | header={p.header!r} | footer={p.footer!r} ----\n\n")
                f.write(p.markdown)
        print(f"  {len(doc.pages)} pages -> {out}")


if __name__ == "__main__":
    main()
