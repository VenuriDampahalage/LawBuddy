"""Ingest every PDF in data/raw_pdfs (or one file) into Postgres.

    uv run python scripts/ingest_folder.py
    uv run python scripts/ingest_folder.py --file constitution.pdf --force
"""

import argparse
import logging

from backend.core.config import get_settings
from backend.rag.ingestion.pipeline import ingest_pdf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--force", action="store_true", help="re-ingest even if already ready")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    s = get_settings()
    files = [s.raw_pdf_dir / args.file] if args.file else sorted(s.raw_pdf_dir.glob("*.pdf"))
    for pdf in files:
        ingest_pdf(pdf, force=args.force)


if __name__ == "__main__":
    main()
