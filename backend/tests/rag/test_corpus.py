"""Regression tests against the real sample PDFs.

They read the cached LlamaParse output in data/parsed/ (never call the API) and are skipped
when that cache is missing, e.g. in CI or on a fresh clone. Thresholds are the measured
values from the first full run; raise them as the detector improves, never lower them
without understanding why.
"""

import pytest

from backend.core.config import get_settings
from backend.rag.ingestion.parser import _cache_path, file_sha256, parse_pdf
from backend.rag.ingestion.structure import Node, build_tree

S = get_settings()


def _tree(name: str) -> list[Node]:
    path = S.raw_pdf_dir / name
    if not path.exists() or not _cache_path(file_sha256(path), S.llamaparse_tier, None).exists():
        pytest.skip(f"no cached parse for {name}")
    return build_tree(parse_pdf(path))


def _sections(act: Node) -> list[Node]:
    return [n for n, anc in act.walk()
            if n.level == "section" and not any(a.level == "schedule" for a in anc)]


def _count(act: Node, level: str) -> int:
    return sum(1 for n, _ in act.walk() if n.level == level)


def test_computer_crime_act():
    acts = _tree("ComputerCrimesActNo24of2007.pdf")
    assert len(acts) == 1
    secs = _sections(acts[0])
    assert [s.number for s in secs] == [str(i) for i in range(1, 39)]
    assert _count(acts[0], "definition") >= 11


def test_criminal_procedure_bundle():
    acts = _tree("Criminal-Procedure.pdf")
    assert len(acts) == 9, "principal Code + 8 later Acts"
    assert acts[0].heading == "Code of Criminal Procedure Act"
    assert len(_sections(acts[0])) >= 455
    assert _count(acts[0], "definition") >= 48
    amendment_2022 = next(a for a in acts if "18 OF 2022" in a.heading.upper())
    assert [s.number for s in _sections(amendment_2022)] == ["1", "2", "3", "4"]


def test_constitution():
    acts = _tree("constitution.pdf")
    assert len(acts) == 1
    numbers = {s.number for s in _sections(acts[0])}
    missing = [i for i in range(1, 173) if str(i) not in numbers]
    assert missing == []
    notes = [f for n, _ in acts[0].walk() for f in n.footnotes]
    assert len(notes) >= 146
    assert not any(f.startswith("#") for f in notes), "every footnote marker resolved"
