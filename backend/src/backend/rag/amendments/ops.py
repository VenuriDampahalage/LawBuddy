"""Structured amendment instructions and how each one is applied to a section's text.

The LLM only *describes* the edit (operation, target, short verbatim anchors). The edit is
then applied here, in code, with two safety checks:
  * words being replaced must exist in the current section text;
  * new text must exist, verbatim, in the amending Act.
If either check fails the result carries a `problem` and is never applied automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from backend.rag.amendments.text import (
    clean_text,
    contains,
    find_part,
    find_span,
    slice_between,
    unquote,
)

Operation = Literal["substitute_words", "replace", "insert_after", "repeal", "replace_heading", "other"]


class AmendmentOp(BaseModel):
    """One edit described by an amending section (one 'by the …' clause)."""

    operation: Operation
    target_section: str = Field(
        description="Section number in the principal Act being changed, e.g. '443' or '43A'. "
        "For a NEW section being inserted: the section it is inserted after.")
    target_part: str | None = Field(
        description="Subsection/paragraph inside that section, e.g. '(2)', '(b)', '(1)(a)'. "
        "For insert_after of a subsection/paragraph: the part it goes after. Null = whole section.")
    new_section_number: str | None = Field(
        description="Only when a whole new section is inserted: its number, e.g. '432A'.")
    old_words: str | None = Field(
        description="substitute_words only: the exact words being replaced, copied verbatim.")
    new_words: str | None = Field(
        description="substitute_words only: the exact new words, copied verbatim, no quotes.")
    new_text_start: str | None = Field(
        description="replace/insert_after: the first 6-10 words of the new provision, verbatim.")
    new_text_end: str | None = Field(
        description="replace/insert_after: the last 6-10 words of the new provision, verbatim.")
    new_heading: str | None = Field(
        description="New marginal note/heading if the amendment gives one, verbatim, no quotes.")
    summary: str = Field(description="One plain-English sentence describing the change.")


class ExtractedOps(BaseModel):
    operations: list[AmendmentOp]


@dataclass
class Applied:
    text: str                 # the section's full text after the edit
    heading: str | None       # new heading, if the edit sets one
    problem: str | None = None


def norm_number(s: str | None) -> str:
    """'43<sup>A</sup>' / '43 A' / 's.43A' -> '43A'"""
    s = clean_text(s or "")
    return s.replace("s.", "").replace("section", "").replace(" ", "").strip(" .").upper()


def _new_text(op: AmendmentOp, amend_text: str) -> str | None:
    if op.new_text_start and op.new_text_end:
        return slice_between(amend_text, op.new_text_start, op.new_text_end)
    return None


def apply_op(op: AmendmentOp, current: str, heading: str | None, amend_text: str,
             label: str, repeal_note: str) -> Applied:
    """Apply `op` to `current` (a section's full text). `label` is e.g. 's.443' for messages."""
    where = f"{label}{op.target_part or ''}"
    keep = Applied(current, heading)

    def fail(msg: str) -> Applied:
        return Applied(current, heading, msg)

    if op.operation == "replace_heading":
        new = unquote(op.new_heading or "")
        if not new or not contains(amend_text, new):
            return fail("The new heading could not be found word for word in the amending Act.")
        return Applied(current, new.rstrip("."))

    if op.operation == "substitute_words":
        if not op.old_words or op.new_words is None:
            return fail("The amendment did not say which words to replace.")
        new = unquote(op.new_words)
        if new and not contains(amend_text, new):
            return fail("The new words could not be found word for word in the amending Act.")
        region = find_part(current, op.target_part) if op.target_part else (0, len(current))
        if region is None:
            return fail(f"{where} could not be found in the current text.")
        span = find_span(current[region[0]:region[1]], op.old_words)
        if span is None:
            return fail(f"The words “{unquote(op.old_words)}” were not found in {where}.")
        a, b = region[0] + span[0], region[0] + span[1]
        return Applied(current[:a] + new + current[b:], heading)

    if op.operation == "repeal":
        if not op.target_part:
            return Applied(repeal_note, heading)
        region = find_part(current, op.target_part)
        if region is None:
            return fail(f"{where} could not be found in the current text.")
        return Applied(_join(current[:region[0]], current[region[1]:]), heading)

    if op.operation in ("replace", "insert_after"):
        new = _new_text(op, amend_text)
        if not new:
            return fail("The new text could not be found word for word in the amending Act.")
        new = clean_text(new).strip("“”\"").rstrip("”\"")
        if op.operation == "replace" and not op.target_part:
            return Applied(strip_section_number(new),
                           unquote(op.new_heading).rstrip(".") if op.new_heading else heading)
        if op.operation == "insert_after" and not op.target_part:
            return keep  # a whole new section: handled by the caller (new provision)
        region = find_part(current, op.target_part)
        if region is None:
            return fail(f"{where} could not be found in the current text.")
        if op.operation == "replace":
            return Applied(_join(current[:region[0]], new, current[region[1]:]), heading)
        return Applied(_join(current[:region[1]], new, current[region[1]:]), heading)

    return fail("This kind of change can’t be applied automatically. Edit the text by hand.")


RE_LEADING_NUMBER = re.compile(r"^\s*\d{1,3}\s?[A-Z]{0,2}\s*\.\s*")


def strip_section_number(text: str) -> str:
    """'442. If any person …' -> 'If any person …' (section text never repeats its number)."""
    return RE_LEADING_NUMBER.sub("", text, count=1)


def _join(*parts: str) -> str:
    return "\n".join(p.strip("\n") for p in parts if p.strip())


def new_section_text(op: AmendmentOp, amend_text: str) -> tuple[str | None, str | None]:
    """Text + heading for an inserted section, or (None, problem)."""
    new = _new_text(op, amend_text)
    if not new:
        return None, "The new section’s text could not be found word for word in the amending Act."
    return strip_section_number(clean_text(new).strip("“”\"").rstrip("”\"")), None
