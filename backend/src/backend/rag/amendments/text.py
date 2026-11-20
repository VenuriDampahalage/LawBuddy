"""Text helpers for applying amendments: cleaning, tolerant matching, finding subsections.

Matching is tolerant of quote style, dashes, case and whitespace ("“within six months”" ==
'"within six months"'), but every span returned points into the ORIGINAL cleaned text,
so the words that end up in the law are always the source's own words.
"""

from __future__ import annotations

import re

_FOLD = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "–": "-", "—": "-",
                       "‐": "-", " ": " "})


def clean_text(s: str) -> str:
    """Readable plain text from parser markdown: drop <sup> tags, emphasis and list stars."""
    s = re.sub(r"</?sup>", "", s)
    s = re.sub(r"(?m)^[ \t]*(?:[*•-][ \t]*)+(?=\()", "", s)   # "* *(a) …" list leftovers
    s = s.replace("**", "").replace("\\*", "")
    s = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"\1", s)   # *italic*
    s = re.sub(r"[ \t]+", " ", s)
    return "\n".join(line.strip() for line in s.splitlines() if line.strip())


def _normalise(s: str) -> tuple[str, list[int]]:
    """Folded/lower-cased text with collapsed whitespace + map back to original indices."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(s):
        c = ch.translate(_FOLD).lower()
        if c.isspace():
            if prev_space:
                continue
            c, prev_space = " ", True
        else:
            prev_space = False
        out.append(c)
        idx.append(i)
    return "".join(out), idx


def _needle(s: str) -> str:
    n, _ = _normalise(clean_text(s))
    return n.strip().strip("\"'").strip()


def find_span(haystack: str, needle: str, start: int = 0) -> tuple[int, int] | None:
    """(start, end) of `needle` inside `haystack` (original indices), or None."""
    n = _needle(needle)
    if not n:
        return None
    h, idx = _normalise(haystack)
    # translate the original start offset into the normalised string
    nstart = next((k for k, orig in enumerate(idx) if orig >= start), len(h))
    p = h.find(n, nstart)
    if p < 0:
        return None
    return idx[p], idx[p + len(n) - 1] + 1


def contains(haystack: str, needle: str) -> bool:
    return find_span(haystack, needle) is not None


def slice_between(text: str, first_words: str, last_words: str) -> str | None:
    """The passage of `text` that starts with `first_words` and ends with `last_words`."""
    a = find_span(text, first_words)
    if a is None:
        return None
    b = find_span(text, last_words, start=a[0])
    if b is None:
        return None
    return text[a[0]:b[1]].strip()


def unquote(s: str) -> str:
    """Strip the quotation marks an amendment wraps new words in."""
    return clean_text(s).strip().strip("“”\"'‘’").strip()


# ---- locating a subsection / paragraph inside a section's text --------------------------

_KINDS = (
    ("number", r"\d+[A-Z]?"),
    ("roman", r"(?:x{0,3})(?:ix|iv|v?i{1,3}|v)"),
    ("letter", r"[a-z]{1,2}"),
)


def _kind(label: str) -> str:
    for name, pat in _KINDS:
        if re.fullmatch(pat, label):
            return "letter" if name == "roman" and label in ("i", "v", "x") else name
    return "letter"


def part_labels(part: str | None) -> list[str]:
    """'(2)(a)' -> ['2', 'a']; '2(a)' -> ['2', 'a']; None -> []"""
    if not part:
        return []
    labels = re.findall(r"\(\s*([0-9A-Za-z]+)\s*\)", part)
    lead = re.match(r"\s*(\d+[A-Z]?)\b", part)
    if lead and (not labels or labels[0] != lead.group(1)):
        labels.insert(0, lead.group(1))
    return labels


def find_part(text: str, part: str | None) -> tuple[int, int] | None:
    """(start, end) of the block for e.g. '(2)' or '(1)(a)' in a section's text, or None.

    A block starts at its label (at the start of a line, or right after its parent's label as
    in '(1) (a) …') and runs until the next label of the same kind at the start of a line,
    or until the next label of a higher level, or the end of the parent block."""
    labels = part_labels(part)
    if not labels:
        return None
    region_start, region_end = 0, len(text)
    higher: list[str] = []
    for label in labels:
        kind = _kind(label)
        region = text[region_start:region_end]
        m = re.search(rf"(?m)(?:^|(?<=\)\s))\(\s*{re.escape(label)}\s*\)", region)
        if not m:
            return None
        start = region_start + m.start()
        same = dict(_KINDS)["number" if kind == "number" else "letter"]
        enders = [rf"(?m)^\(\s*{same}\s*\)"] + [rf"(?m)^\(\s*{dict(_KINDS)[h]}\s*\)" for h in higher]
        end = region_end
        for pat in enders:
            nxt = re.compile(pat).search(text, start + len(m.group(0)), region_end)
            if nxt and nxt.start() < end:
                end = nxt.start()
        region_start, region_end = start, end
        higher.append("number" if kind == "number" else "letter")
    return region_start, region_end
