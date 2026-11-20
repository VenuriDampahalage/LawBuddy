"""PDF -> per-page markdown using LlamaParse (llama-cloud >= 1.0), with a local cache.

Parsing costs credits, so every result is cached in data/parsed/<sha256>.<tier>.json.
Re-chunking never re-parses unless the cache is deleted or force=True.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llama_cloud import LlamaCloud
from pydantic import BaseModel

from backend.core.config import get_settings

# Sri Lankan Acts put section headings in the margin ("Short title.", "Interpretation.").
# Text-layer extraction scatters these notes mid-sentence, so we ask the parser to
# pull them out explicitly. The structure detector relies on this marker format.
LEGAL_PARSE_PROMPT = """\
This is a Sri Lankan legal document (an Act of Parliament, a consolidated code, or the Constitution).
Preserve the legal structure exactly:
- Keep PART / CHAPTER / Schedule headings as markdown headings.
- Keep section/article numbers exactly as printed (e.g. "5.", "111K.", "(1)", "(a)", "(i)").
- Marginal notes (short headings printed in the side margin next to a section) must NOT be
  merged into the body text. Emit each one on its own line immediately BEFORE the section it
  belongs to, formatted as:  [MARGINAL NOTE: <text>]
- Keep footnote reference markers and footnotes (e.g. amendment notes such as
  "112 - Substituted by the Twenty First Amendment ...") as written.
- Do not summarise, translate or correct the legal text.
"""


class ParsedPage(BaseModel):
    pdf_page: int  # 1-based index in the PDF file
    printed_page: str | None = None  # page number printed on the page, if detected
    header: str | None = None
    footer: str | None = None
    markdown: str


class ParsedDocument(BaseModel):
    source_file: str
    file_hash: str
    tier: str
    job_id: str | None = None
    pages: list[ParsedPage]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(file_hash: str, tier: str, target_pages: str | None) -> Path:
    suffix = f".p{target_pages.replace(',', '_')}" if target_pages else ""
    return get_settings().parsed_dir / f"{file_hash}.{tier}{suffix}.json"


def parse_pdf(
    path: Path,
    *,
    tier: str | None = None,
    target_pages: str | None = None,
    force: bool = False,
) -> ParsedDocument:
    """Parse a PDF into per-page markdown, using the on-disk cache when available."""
    settings = get_settings()
    tier = tier or settings.llamaparse_tier
    file_hash = file_sha256(path)
    cache = _cache_path(file_hash, tier, target_pages)

    if cache.exists() and not force:
        return ParsedDocument.model_validate_json(cache.read_text(encoding="utf-8"))

    api_key = settings.llama_cloud_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("LLAMA_CLOUD_API_KEY is not set (see .env.example)")

    client = LlamaCloud(api_key=api_key)
    kwargs: dict = {
        "tier": tier,
        "version": settings.llamaparse_version,
        "upload_file": path,
        "expand": ["markdown"],
        "output_options": {"extract_printed_page_number": True},
        "client_name": "lawbuddy",
    }
    if tier != "fast":
        kwargs["agentic_options"] = {"custom_prompt": LEGAL_PARSE_PROMPT}
    if target_pages:
        kwargs["page_ranges"] = {"target_pages": target_pages}

    result = client.parsing.parse(**kwargs)

    if result.markdown is None:
        raise RuntimeError(f"LlamaParse returned no markdown (job status: {result.job.status})")

    pages: list[ParsedPage] = []
    for p in result.markdown.pages:
        if not p.success:
            # Keep a placeholder so page numbering stays aligned; surface the error.
            pages.append(ParsedPage(pdf_page=p.page_number, markdown=f"[PARSE FAILED: {p.error}]"))
            continue
        pages.append(
            ParsedPage(
                pdf_page=p.page_number,
                header=p.header,
                footer=p.footer,
                markdown=p.markdown,
            )
        )

    doc = ParsedDocument(
        source_file=path.name, file_hash=file_hash, tier=tier, job_id=result.job.id, pages=pages
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    # Also dump raw response metadata once, to learn where printed page numbers land.
    meta = cache.with_suffix(".meta.json")
    meta.write_text(json.dumps(result.metadata.model_dump() if result.metadata else {}, indent=2,
                               default=str), encoding="utf-8")
    return doc
