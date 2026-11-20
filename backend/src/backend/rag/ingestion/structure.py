"""Turn LlamaParse per-page markdown into a legal hierarchy tree.

    Act ─┬─ Part ── Chapter ── Group ── Section ─┬─ Subsection ── Paragraph ── Subparagraph
         └─ Schedule                             └─ Definition (in "Interpretation" sections)

Design notes (from studying real Sri Lankan PDFs, see data/parsed/review/):
- One PDF can hold several Acts (consolidated code + appended amendment Acts). A new Act
  starts with the Gazette cover ("PARLIAMENT OF THE DEMOCRATIC SOCIALIST REPUBLIC...") or
  with a title line followed by "[Certified on ...]".
- Section headings are printed in the margin; the parser emits them as
  "[MARGINAL NOTE: ...]" right before the section.
- Section numbers appear as "**3.**", "**19**.", "111K.", "**113 A.**".
- Amendment Acts quote whole replacement sections ("442. If any person ...").  These must not
  become sections of the amendment Act, so a section start is accepted only if its number is
  plausible relative to the previous one (no big jumps).
- The Constitution marks amendments with footnotes: "<sup>112</sup>[Court of Appeal]" in the
  text and "112 - Substituted by the Twenty First Amendment ..." as a footnote line.
"""

from __future__ import annotations

import bisect
import re
from collections import defaultdict
from dataclasses import dataclass, field

from backend.rag.ingestion.parser import ParsedDocument, ParsedPage

# --------------------------------------------------------------------------- tree model

LEVELS = ("act", "schedule", "part", "chapter", "group", "section", "subsection",
          "explanation", "paragraph", "subparagraph", "definition")


@dataclass
class Node:
    level: str
    number: str | None = None          # "5", "111K", "(2)", "(a)", "II"
    heading: str | None = None         # marginal note / part title / chapter title
    lines: list[str] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)
    page_start: int | None = None      # PDF page (1-based)
    page_end: int | None = None
    printed_page_start: str | None = None
    printed_page_end: str | None = None
    footnotes: list[str] = field(default_factory=list)   # amendment notes attached here
    term: str | None = None            # for definitions
    unit: str = "s."                   # "Art." for the Constitution

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()

    def full_text(self) -> str:
        """This node's own text followed by all descendants' text, in reading order."""
        parts = [self.text] if self.text else []
        parts += [c.full_text() for c in self.children]
        return "\n".join(p for p in parts if p).strip()

    def touch(self, pdf_page: int, printed: str | None) -> None:
        if self.page_start is None:
            self.page_start, self.printed_page_start = pdf_page, printed
        self.page_end, self.printed_page_end = pdf_page, printed

    def label(self) -> str:
        if self.level == "act":
            return self.heading or "Act"
        if self.level == "section":
            return f"{self.unit}{self.number}"
        if self.level in ("subsection", "paragraph", "subparagraph"):
            return self.number or ""
        if self.level == "explanation":
            return self.heading or "Explanation"
        if self.level == "definition":
            return f"def. “{self.term}”"
        name = self.level.capitalize()
        return f"{name} {self.number}" if self.number else (self.heading or name)

    def walk(self, path: tuple[Node, ...] = ()):
        """Yield (node, ancestors) depth-first."""
        yield self, path
        for c in self.children:
            yield from c.walk(path + (self,))


# --------------------------------------------------------------------------- regexes

# Case-sensitive on purpose: the enacting formula "BE it enacted by the Parliament of the
# Democratic Socialist Republic..." must not start a new Act.
RE_COVER = re.compile(r"^[#*\s]*PARLIAMENT OF THE DEMOCRATIC\s+SOCIALIST REPUBLIC")
RE_ACT_TITLE = re.compile(
    r"^[#*\s]*((?:THE\s+)?[A-Z][A-Za-z0-9 ,()'’&\-]+?\s+(?:ACT|CODE|ORDINANCE|LAW),?\s+No\.?\s*\d+\s+OF\s+\d{4})\b",
    re.IGNORECASE,
)
RE_CERTIFIED = re.compile(r"^\W*\[?Certified on", re.IGNORECASE)
RE_PART = re.compile(r"^#+\s*\**PART\s+([IVXLC]+[A-Z]?|\d+[A-Z]?)\b\.?\**\s*[:.\-–—]?\s*(.*)$", re.IGNORECASE)
RE_CHAPTER = re.compile(r"^#+\s*\**CHAPTER\s+([IVXLC]+[A-Z]?|\d+[A-Z]?)\b\.?\**\s*[:.\-–—]?\s*(.*)$", re.IGNORECASE)
RE_SCHEDULE = re.compile(r"^#+\s*\**((?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)?\s*SCHEDULE)\b\**\s*(.*)$", re.IGNORECASE)
RE_GROUP = re.compile(r"^#+\s*\**([A-Z])\.\s*[-–—]\s*(.+?)\**$")          # "### A. - ARREST GENERALLY"
RE_HEADING = re.compile(r"^#+\s*(.+)$")
RE_MARGINAL_ANY = re.compile(r"\[MARGINAL NOTE:[^\]]*\]", re.IGNORECASE)
RE_MARGINAL = re.compile(r"^\[MARGINAL NOTE:\s*(.*?)\]\s*$", re.IGNORECASE)
RE_PLAIN_NOTE = re.compile(r"^[A-Z][A-Za-z ,'’&()\-]{3,140}\.$")
RE_BOLD_ONLY = re.compile(r"^\*\*([^*]{3,120})\*\*$")
# Section start: optional bold, number with optional letter suffix ("113 A"), dot, then text.
RE_SECTION = re.compile(r"^(?:<sup>\d+</sup>)?\[?\**\s*(\d{1,3})\s?([A-Z]{0,2})\s*\**\s*\.\s*\**\s*(.*)$")
RE_SUBSECTION = re.compile(r"^\((\d{1,2}[A-Z]?)\)\s*(.*)$")
RE_PARAGRAPH = re.compile(r"^\(([a-z]{1,2})\)\s*(.*)$")
RE_ROMAN = re.compile(r"^\(((?:x{0,3})(?:ix|iv|v?i{0,3}))\)\s*(.*)$")
# '"term" means ...'; LankaLAW repeats the marginal note first: '"Fine." "Fine" includes ...'
RE_DEFINITION = re.compile(
    r"^(?:[\"“][^\"”]{1,80}[\"”]\s*)?[\"“‘]\s*([^\"“”’]{1,80}?)\s*[\"”’]"
    r"[^.;]{0,120}?\b(means|mean|includes|include|shall mean|has the (?:same )?meaning)\b",
    re.IGNORECASE,
)
RE_FOOTNOTE = re.compile(
    r"^\\?\*?\s*(?:<sup>)?(\d{1,4})(?:</sup>)?\s*[-–—]\s*"
    r"(.*\b(?:Amendment|amended|repealed|substituted|inserted|added|renumbered|re-numbered)\b.*)$",
    re.IGNORECASE,
)
RE_SUP = re.compile(r"<sup>(\d+)</sup>")
# LankaLAW layout: marginal note inline before the section number. Seen variants:
#   "Short title 678-14-1991 **1**. This Act ..."     "**Interpretation. 2**. In ..."
#   "**Aid to other than ...** **20**. When ..."      "**Trial of offences ...** 5. All ..."
#   "Offences under Penal code — **10**. Subject ..." "Procedure where ... proceedings. 262. If ..."
RE_SECTION_INLINE = re.compile(
    r"^\**(?P<note>[A-Z][^*\[\]]{2,200}?)(?P<dot>\.)?\s*\**\s*(?:[\d\-]{5,}\s*)?[—–-]?\s*"
    r"(?P<bold>\*\*)?\s*(?P<num>\d{1,3})\s?(?P<suf>[A-Z]{0,2})\s*(?:\*\*)?\s*\.\s*\**\s*"
    r"(?P<rest>.*)$"
)
RE_NOTE_TAIL = re.compile(r"^[a-z][^.]{0,80}\.?$")   # "Registries of **44**. summons."
# A note ending in these words is really a sentence citing a section ("... under section 5. If")
NOTE_BAD_ENDINGS = {"section", "sections", "article", "articles", "no", "of", "and", "to",
                    "under", "act", "paragraph", "subsection", "chapter", "schedule", "the", "or"}


@dataclass
class InlineSection:
    note: str
    number: str
    rest: str


# A section number followed by closing bold: "**43**", "**43A**", "2**" (in "**Interpretation. 2**")
RE_BOLD_NUMBER = re.compile(r"(?<![\d,.])(\d{1,3})\s?([A-Z]{0,2})\s*\*\*")


def _split_note_rest(note: str, rest: str, bold_num: bool) -> InlineSection | None:
    note = re.sub(r"\s*[\d\-]{5,}$", "", _clean(note))        # drop "678-14-1991" codes
    rest = rest.strip().lstrip("*").strip()
    # Note split around the number: "Registries of **44**. summons." -> "Registries of summons"
    if bold_num and RE_NOTE_TAIL.match(rest):
        note, rest = f"{note} {rest.rstrip('.')}", ""
    rest = RE_MARGINAL_ANY.sub("", rest).strip()       # same note repeated as a marginal note
    if rest and not re.match(r"[A-Z(\"“]", rest):
        return None
    words = note.split()
    if not words or not words[0][0].isupper() or len(words) > 25:
        return None
    if words[-1].lower().strip(".,") in NOTE_BAD_ENDINGS and not bold_num:
        return None
    return InlineSection(note.rstrip("."), "", rest)


def inline_section(line: str) -> InlineSection | None:
    """Match a section line that carries its marginal note inline (LankaLAW layout)."""
    # 1) Bold section number anywhere in the line. Try each position, because the note itself
    #    may contain numbers ("... arrested under section 42. **43**. The sections ...").
    for m in RE_BOLD_NUMBER.finditer(line):
        after = line[m.end():].lstrip()
        if after.startswith("."):
            after = after[1:]
        elif after and not after.startswith("["):
            continue                      # "**43** foo" without a dot is not a section start
        found = _split_note_rest(line[: m.start()], after, bold_num=True)
        if found:
            found.number = m.group(1) + m.group(2)
            return found
    # 2) Plain note + plain number, which needs a dot after both: "Note text. 262. If ..."
    m = RE_SECTION_INLINE.match(line)
    if not m or not (m.group("dot") or line.startswith("**")):
        return None
    found = _split_note_rest(m.group("note"), m.group("rest"), bold_num=False)
    if found:
        found.number = m.group("num") + m.group("suf")
    return found
# Inline amendment reference: "[2, 28 of 1998]" = section 2 of Act No. 28 of 1998
RE_INLINE_AMEND = re.compile(r"\[\s*(\d+[A-Z]?)\s*,\s*(\d+)\s+of\s+(\d{4})\s*\]")
RE_CITED_AS = re.compile(r"may be cited as (?:the )?(.+?)(?:\s*,|\s+and\s|\.\s|\.$|;|$)", re.IGNORECASE)
RE_EXPLANATION = re.compile(r"^\*?(Explanation|Illustrations?)(?![a-z])\s*(\d*)", re.IGNORECASE)
RE_PAGE_NUM = re.compile(r"^\s*(\d{1,4}|[ivxlc]{1,6})\s*$", re.IGNORECASE)

NOISE = [
    re.compile(r"^Coat of arms", re.IGNORECASE),
    re.compile(r"Copyright\s+LankaLAW", re.IGNORECASE),
    re.compile(r"^\d+\s*[—–-]\s*PL\s*\d+", re.IGNORECASE),                 # gazette print code
    re.compile(r"^PRINTED AT THE DEPARTMENT OF GOVERNMENT PRINTING", re.IGNORECASE),
    re.compile(r"^TO BE PURCHASED AT", re.IGNORECASE),
    re.compile(r"^\**Price\s*:", re.IGNORECASE),
    re.compile(r"^\**Postage\s*:", re.IGNORECASE),
    re.compile(r"^\*?Printed on the Order of Government\*?$", re.IGNORECASE),
    re.compile(r"^-{3,}$"),
]


# --------------------------------------------------------------------------- cleanup

def normalize_line(line: str) -> str:
    s = line.strip()
    # list bullets the parser sometimes adds:  "* (b) the access ..."
    s = re.sub(r"^[*\-•]\s+(?=\()", "", s)
    # paragraph labels: "(*a*)", "(\*a)", "\(a)", "(*a)"  ->  "(a)"
    s = re.sub(r"^\\?\(\s*\\?\*?([a-z]{1,4}|\d{1,2}[A-Z]?)\*?\s*\\?\)", r"(\1)", s)
    # inline italics inside labels mid-line: "paragraph (*d*)" -> "paragraph (d)"
    s = re.sub(r"\(\*([a-z]{1,4})\*\)", r"(\1)", s)
    s = s.replace("\\;", ";").replace("\\*", "*")
    s = s.replace("<u>", "").replace("</u>", "").replace("\\<", "<")
    s = re.sub(r"\^(\d{1,4})\^", r"<sup>\1</sup>", s)      # "^16^[" footnote marker variant
    return s


def printed_page_number(page: ParsedPage) -> str | None:
    """Best-effort printed page number: footer, then header, then bare number lines in body."""
    for blob in (page.footer, page.header):
        if not blob:
            continue
        for part in reversed(blob.splitlines()):
            m = RE_PAGE_NUM.match(part)
            if m:
                return m.group(1)
    lines = [ln for ln in page.markdown.splitlines() if ln.strip()]
    for ln in lines[:2] + lines[-2:]:
        m = RE_PAGE_NUM.match(ln)
        if m:
            return m.group(1)
    if page.header:
        m = re.match(r"^\s*(\d{1,4})\s+\D", page.header)
        if m:
            return m.group(1)
    return None


def is_noise(line: str) -> bool:
    return any(p.search(line) for p in NOISE)


# --------------------------------------------------------------------------- parser

def _num_key(num: str) -> tuple[int, str]:
    m = re.match(r"(\d+)\s*([A-Z]*)", num)
    return (int(m.group(1)), m.group(2)) if m else (0, "")


class _Builder:
    """Single pass over all lines, maintaining a stack of open nodes."""

    def __init__(self, source_title: str, accepted: set[int] | None) -> None:
        """accepted=None: pass 1, accept every section-like line and record it as a candidate.
        accepted=set: pass 2, only those line ids become sections (see build_tree)."""
        self.acts: list[Node] = []
        self.source_title = source_title
        self.accepted = accepted
        self.candidates: list[tuple[int, int, str]] = []   # (segment, line_id, number)
        self.segment = 0
        self.line_id = 0
        self.pending_note: str | None = None
        self.page = 0
        self.printed: str | None = None
        self.footnotes: dict[str, str] = {}
        self.in_interpretation = False
        self.first_heading: dict[int, str] = {}
        self._new_act(None)

    # ---- stack helpers
    def _new_act(self, title: str | None) -> None:
        self.act = Node("act", heading=title)
        self.acts.append(self.act)
        self.stack: list[Node] = [self.act]
        self.in_interpretation = False
        self.segment += 1

    def _open(self, node: Node, parent_levels: tuple[str, ...]) -> Node:
        while self.stack[-1].level not in parent_levels:
            self.stack.pop()
        self.stack[-1].children.append(node)
        self.stack.append(node)
        node.touch(self.page, self.printed)
        for n in self.stack:
            n.touch(self.page, self.printed)
        return node

    def _current(self, *levels: str) -> Node | None:
        for n in reversed(self.stack):
            if n.level in levels:
                return n
        return None

    def _append_text(self, line: str) -> None:
        top = self.stack[-1]
        top.lines.append(line)
        for n in self.stack:
            n.touch(self.page, self.printed)

    # ---- main entry
    def feed_page(self, page: ParsedPage) -> None:
        self.page = page.pdf_page
        self.printed = printed_page_number(page)
        self._collect_footer_footnotes(page.footer)
        raw = [normalize_line(ln) for ln in page.markdown.splitlines()]
        lines = [ln for ln in raw if ln and not is_noise(ln)]
        # Drop a bare page-number line at the very top/bottom of the page.
        if lines and RE_PAGE_NUM.match(lines[0]):
            lines = lines[1:]
        if lines and RE_PAGE_NUM.match(lines[-1]):
            lines = lines[:-1]

        for i, line in enumerate(lines):
            self.line_id += 1
            self._feed_line(line, lines[i + 1] if i + 1 < len(lines) else "")

    def _collect_footer_footnotes(self, footer: str | None) -> None:
        """Footnotes often land in the page footer, wrapped over several lines:
        '1 - Substituted by the Seventh Amendment to the\\nConstitution Sec. 2(a).\\n2 - ...'"""
        if not footer:
            return
        entries: list[str] = []
        for ln in (normalize_line(x) for x in footer.splitlines()):
            if not ln:
                continue
            if re.match(r"^(?:<sup>)?\d{1,4}(?:</sup>)?\s*[-–—]\s", ln) or not entries:
                entries.append(ln)
            else:
                entries[-1] += " " + ln
        for e in entries:
            if (m := RE_FOOTNOTE.match(e)):
                self.footnotes[m.group(1)] = m.group(2).strip()

    def _feed_line(self, line: str, nxt: str) -> None:
        # --- Act boundaries -------------------------------------------------------
        if RE_COVER.search(line):
            self._new_act(None)
            return
        m = RE_ACT_TITLE.match(line)
        title_like = line.lstrip().startswith(("#", "*")) or RE_CERTIFIED.match(nxt)
        if m and title_like:
            title = re.sub(r"\s+", " ", m.group(1)).strip(" *#")
            if self.act.heading is None:
                self.act.heading = title.title() if title.isupper() else title
                return
            if self.act.children:            # a new Act starts without a cover page
                self._new_act(title)
                return
            return

        # --- Footnotes (amendment notes) -------------------------------------------
        m = RE_FOOTNOTE.match(line)
        if m:
            self.footnotes[m.group(1)] = m.group(2).strip()
            return

        # --- Inline amendment refs "[2, 28 of 1998]" -> history on the current section ------
        if (refs := RE_INLINE_AMEND.findall(line)):
            target = self._current("section", "schedule") or self.act
            target.footnotes.extend(f"Amended by s.{s} of Act No. {n} of {y}" for s, n, y in refs)
            line = RE_INLINE_AMEND.sub("", line).strip()
            if not line:
                return

        # --- Headings: Part / Chapter / Schedule / Group ----------------------------
        if (m := RE_PART.match(line)):
            number = m.group(1).upper()
            cur = self._current("part")
            if cur is not None and cur.number == number:      # heading repeated on a later page
                while self.stack[-1] is not cur:
                    self.stack.pop()
                return
            self._open(Node("part", number=number, heading=_clean(m.group(2)) or None), ("act",))
            return
        if (m := RE_CHAPTER.match(line)):
            self._open(Node("chapter", number=m.group(1).upper(), heading=_clean(m.group(2)) or None),
                       ("act", "part"))
            return
        if (m := RE_SCHEDULE.match(line)):
            self._open(Node("schedule", heading=_clean(" ".join(m.groups()))), ("act",))
            self.segment += 1                   # numbering restarts inside schedules
            return
        if (m := RE_GROUP.match(line)):
            self._open(Node("group", number=m.group(1), heading=_clean(m.group(2))),
                       ("act", "part", "chapter"))
            return
        if (m := RE_HEADING.match(line)):
            # Title line under a Part/Chapter heading (e.g. "## COMPUTER CRIME")
            top = self.stack[-1]
            if top.level in ("part", "chapter", "schedule") and not top.heading and not top.children:
                top.heading = _clean(m.group(1))
                return
            if top.level in ("part", "chapter") and not top.children and top.heading:
                top.heading += " — " + _clean(m.group(1))
                return
            line = _clean(m.group(1))    # otherwise keep as plain text
            # Title of an untitled Act = consecutive headings on its first page
            # ("# THE CONSTITUTION OF THE" + "# DEMOCRATIC SOCIALIST REPUBLIC ...").
            idx = len(self.acts) - 1
            if self.act.heading is None and self.page == (self.act.page_start or self.page):
                prev = self.first_heading.get(idx)
                self.first_heading[idx] = f"{prev} {line}" if prev else line
                self.act.touch(self.page, self.printed)

        # --- Marginal notes ------------------------------------------------------------
        if (m := RE_MARGINAL.match(line)):
            self.pending_note = _clean(m.group(1)).rstrip(".")
            return
        if (m := RE_BOLD_ONLY.match(line)) and RE_SECTION.match(nxt):
            self.pending_note = _clean(m.group(1)).rstrip(".")   # missed marginal note
            return
        # Plain title-like line right before a section: "Person arrested not to be detained
        # more than twenty-four hours." It might also be the last sentence of the previous
        # provision, so it is ALSO kept as text below (never lose legal wording).
        if (RE_PLAIN_NOTE.match(line) and len(line.split()) <= 12 and RE_SECTION.match(nxt)
                and not line.lower().startswith(("provided", "explanation", "illustration"))):
            self.pending_note = line.rstrip(".")

        # --- Section ---------------------------------------------------------------------
        inline = inline_section(line)
        inline_ok = inline is not None and self._accept_section(inline.number)
        if inline_ok:
            self.pending_note = inline.note
            line = f"{inline.number}. {inline.rest}"
        m = None if (inline and not inline_ok) else RE_SECTION.match(line)
        accepted = bool(m) and (inline_ok or self._accept_section(m.group(1) + m.group(2)))
        if (inline or m) and not accepted:
            # A rejected section-like line is quoted text (e.g. a replacement section inside
            # an amendment Act). Its marginal note belongs to the quote, not the next section.
            if self.pending_note:
                self._append_text(f"[{self.pending_note}]")
            self.pending_note = None
        if accepted:
            number = m.group(1) + m.group(2)
            sec = self._open(Node("section", number=number, heading=self.pending_note),
                             ("act", "part", "chapter", "group", "schedule"))
            self.pending_note = None
            self.in_interpretation = bool(sec.heading and "interpretation" in sec.heading.lower())
            rest = m.group(3).strip()
            if rest:
                self._feed_line(rest, nxt) if RE_SUBSECTION.match(rest) else self._append_text(
                    self._mark_footnotes(rest))
            return

        # --- Subsection / paragraph / sub-paragraph --------------------------------------
        sec = self._current("section")
        if sec is not None:
            if (m := RE_SUBSECTION.match(line)):
                self._open(Node("subsection", number=f"({m.group(1)})"), ("section",))
                self._append_text(self._mark_footnotes(m.group(2)))
                return
            if (m := RE_EXPLANATION.match(line)):
                label = f"{m.group(1).capitalize()} {m.group(2)}".strip()
                self._open(Node("explanation", heading=label), ("section", "subsection"))
                self._append_text(self._mark_footnotes(line))
                return
            roman = RE_ROMAN.match(line)
            para = RE_PARAGRAPH.match(line)
            if roman and roman.group(1) and self._is_roman_context(roman.group(1)):
                self._open(Node("subparagraph", number=f"({roman.group(1)})"), ("paragraph",))
                self._append_text(self._mark_footnotes(roman.group(2)))
                return
            if para:
                self._open(Node("paragraph", number=f"({para.group(1)})"),
                           ("explanation", "subsection", "section", "definition"))
                self._append_text(self._mark_footnotes(para.group(2)))
                return
            if self.in_interpretation and (m := RE_DEFINITION.match(line)):
                self._open(Node("definition", term=_clean(m.group(1))), ("section", "subsection"))
                self._append_text(self._mark_footnotes(line))
                return

        self.pending_note = None if self.pending_note and not line else self.pending_note
        self._append_text(self._mark_footnotes(line))

    # ---- heuristics
    def _accept_section(self, number: str) -> bool:
        if self.accepted is None:                      # pass 1: record every candidate
            self.candidates.append((self.segment, self.line_id, number))
            return True
        return self.line_id in self.accepted

    def _is_roman_context(self, label: str) -> bool:
        """'(i)' is a paragraph letter if the previous sibling paragraph was '(h)'."""
        para = self._current("paragraph")
        if para is None:
            return False
        return not (label in ("i", "v", "x") and para.number in ("(h)", "(u)", "(w)"))

    def _mark_footnotes(self, text: str) -> str:
        """Remove <sup>n</sup> markers but remember them on the current section."""
        refs = RE_SUP.findall(text)
        if refs:
            target = self._current("section", "schedule") or self.act
            target.footnotes.extend(f"#{r}" for r in refs)
        return RE_SUP.sub("", text)

    def finish(self) -> list[Node]:
        # Resolve "#112" refs to the footnote text collected anywhere in the document.
        for act in self.acts:
            for node, _ in act.walk():
                node.footnotes = [self.footnotes.get(f[1:], f) if f.startswith("#") else f
                                  for f in node.footnotes]
        acts = []
        for i, act in enumerate(self.acts):
            if not act.children:
                continue
            if act.heading is None:   # consolidated texts have no Gazette cover/title line
                first_sec = next((n for n, _ in act.walk() if n.level == "section"), None)
                cited = RE_CITED_AS.search(first_sec.full_text()) if first_sec else None
                act.heading = (cited.group(1).strip() if cited
                               else self.first_heading.get(i) or self.source_title)
            if "constitution" in act.heading.lower():
                for node, _ in act.walk():
                    node.unit = "Art."
            acts.append(act)
        return acts


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("**", "").replace("*", "")).strip(" #:-–—")


def _longest_increasing(keys: list[tuple[int, str]]) -> list[int]:
    """Indices of one longest strictly increasing subsequence (O(n log n))."""
    tails: list[tuple[int, str]] = []
    tails_idx: list[int] = []
    prev = [-1] * len(keys)
    for i, k in enumerate(keys):
        j = bisect.bisect_left(tails, k)
        if j == len(tails):
            tails.append(k)
            tails_idx.append(i)
        else:
            tails[j], tails_idx[j] = k, i
        prev[i] = tails_idx[j - 1] if j > 0 else -1
    out, i = [], tails_idx[-1] if tails_idx else -1
    while i != -1:
        out.append(i)
        i = prev[i]
    return out[::-1]


def build_tree(doc: ParsedDocument) -> list[Node]:
    """Return one Act node per Act found in the PDF.

    Two passes: pass 1 collects every line that *looks* like a section start; within each
    Act/Schedule the real sections are the longest increasing run of section numbers.
    Numbered lines that break the run (e.g. a replacement "442." quoted inside an amendment
    Act's section 2) stay as ordinary text in pass 2.
    """
    probe = _Builder(doc.source_file, accepted=None)
    for page in doc.pages:
        probe.feed_page(page)

    by_segment: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for segment, line_id, number in probe.candidates:
        by_segment[segment].append((line_id, number))
    accepted: set[int] = set()
    for items in by_segment.values():
        keys = [_num_key(num) for _, num in items]
        accepted.update(items[i][0] for i in _longest_increasing(keys))

    b = _Builder(doc.source_file, accepted=accepted)
    for page in doc.pages:
        b.feed_page(page)
    return b.finish()


# --------------------------------------------------------------------------- debugging

def outline(node: Node, max_depth: int = 3, _depth: int = 0) -> str:
    """Compact outline for eyeballing the tree."""
    pages = f"p{node.page_start}" + (f"-{node.page_end}" if node.page_end != node.page_start else "")
    pr = f" [printed {node.printed_page_start}]" if node.printed_page_start else ""
    head = f" — {node.heading}" if node.heading and node.level != "act" else ""
    fn = f"  ⟨{len(node.footnotes)} amendment note(s)⟩" if node.footnotes else ""
    out = [f"{'  ' * _depth}{node.label()}{head} ({pages}{pr}){fn}"]
    if _depth < max_depth:
        for c in node.children:
            out.append(outline(c, max_depth, _depth + 1))
    return "\n".join(out)
