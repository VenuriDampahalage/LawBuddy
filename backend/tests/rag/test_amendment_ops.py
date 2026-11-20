"""Applying amendment instructions to section text (no LLM, no database).

The amending texts below are the real ones from the Code of Criminal Procedure amendment
Acts in the sample corpus (shortened where noted)."""

from backend.rag.amendments.ops import AmendmentOp, apply_op, new_section_text, norm_number
from backend.rag.amendments.text import clean_text, find_part, find_span

NOTE = "[Repealed]"


def op(**kw) -> AmendmentOp:
    base = {"target_part": None, "new_section_number": None, "old_words": None, "new_words": None,
            "new_text_start": None, "new_text_end": None, "new_heading": None, "summary": "test"}
    return AmendmentOp(**{**base, **kw})


S431 = clean_text("""(1) Where property is seized the Magistrate shall publish a notification.
(2) If no person within six months from such publication establishes his claim, the property shall vest.
(3) Where the value is two thousand five hundred rupees or more. the property may be sold.""")

A431 = clean_text("""Section 431 of the Code of Criminal Procedure Act, No. 15 of 1979 is hereby amended as follows:—
in subsection (2) of that section, by the substitution for the words “within six months” of the words “within two months”; and
in subsection (3) of that section, by the substitution for the words “two thousand five hundred rupees or more.” of the words “one hundred thousand rupees or more.”.""")


def test_tolerant_matching_points_into_original_text():
    text = "the words “within six months” here"
    a, b = find_span(text, '"WITHIN   six months"')
    assert text[a:b] == "within six months"


def test_substitute_words_inside_a_subsection():
    r = apply_op(op(operation="substitute_words", target_section="431", target_part="(2)",
                    old_words="within six months", new_words="“within two months”"),
                 S431, None, A431, "s.431", NOTE)
    assert r.problem is None
    assert "within two months from such publication" in r.text
    assert "six months" not in r.text and "(1) Where property" in r.text


def test_substitution_with_trailing_full_stop():
    r = apply_op(op(operation="substitute_words", target_section="431", target_part="(3)",
                    old_words="two thousand five hundred rupees or more.",
                    new_words="one hundred thousand rupees or more."),
                 S431, None, A431, "s.431", NOTE)
    assert r.problem is None and "one hundred thousand rupees or more. the property" in r.text


def test_paraphrased_new_words_are_refused():
    r = apply_op(op(operation="substitute_words", target_section="431", target_part="(2)",
                    old_words="within six months", new_words="within 2 months"),
                 S431, None, A431, "s.431", NOTE)
    assert r.problem and "word for word" in r.problem and r.text == S431


def test_missing_old_words_are_refused():
    r = apply_op(op(operation="substitute_words", target_section="431", target_part="(1)",
                    old_words="within six months", new_words="within two months"),
                 S431, None, A431, "s.431", NOTE)
    assert r.problem and "were not found in s.431(1)" in r.problem


S195 = clean_text("""The Attorney-General shall-
(a) forward the indictment to the High Court;
(b) serve a copy on the accused;
(c) inform the accused of the date of trial;
(ee) notify the Fiscal.""")

A195 = clean_text("""Section 195 of the principal enactment is hereby amended as follows:-
by the repeal of paragraph (c) thereof and the substitution therefor of the following paragraph:-
"(c) inform the accused and the aggrieved party of the date of the pre-trial conference to be held under section 195<sup>A</sup>;";
by the repeal of paragraph (ee) thereof.""")


def test_replace_and_repeal_paragraphs():
    r = apply_op(op(operation="replace", target_section="195", target_part="(c)",
                    new_text_start="(c) inform the accused and the aggrieved party",
                    new_text_end="to be held under section 195A;"),
                 S195, None, A195, "s.195", NOTE)
    assert r.problem is None
    assert "(c) inform the accused and the aggrieved party of the date of the pre-trial conference to be held under section 195A;" in r.text
    assert "date of trial" not in r.text and "(b) serve a copy" in r.text
    r2 = apply_op(op(operation="repeal", target_section="195", target_part="(ee)"), r.text, None, A195, "s.195", NOTE)
    assert r2.problem is None and "(ee)" not in r2.text and r2.text.endswith("section 195A;")


def test_find_part_nested_and_inline():
    text = "(1) (a) The counsel may apply;\n(b) the judge shall record it.\n(2) Other matters."
    a, b = find_part(text, "(1)")
    assert text[a:b].startswith("(1) (a)") and "(2)" not in text[a:b]
    a, b = find_part(text, "(1)(b)")
    assert text[a:b].strip() == "(b) the judge shall record it."


def test_replace_heading_and_whole_section():
    a432 = 'Section 432 is hereby amended by the repeal of the marginal note and the substitution therefor of the following:— “Procedure where no claimant appears within two months.”.'
    r = apply_op(op(operation="replace_heading", target_section="432",
                    new_heading="Procedure where no claimant appears within two months."),
                 "text", "Old heading", a432, "s.432", NOTE)
    assert r.problem is None and r.heading == "Procedure where no claimant appears within two months"
    rep = apply_op(op(operation="repeal", target_section="9"), "old text", "H", "x", "s.9", NOTE)
    assert rep.text == NOTE


def test_inserted_section_text_and_numbers():
    a = clean_text("""The following new section is hereby inserted immediately after section 43<sup>A</sup> and shall have effect as section 43<sup>B</sup> of that Act:—
43<sup>B</sup>. (1) It shall be the duty of every Magistrate to visit every police station at least once in every month.
(2) The Magistrate shall record his observations.""")
    text, problem = new_section_text(op(operation="insert_after", target_section="43A", new_section_number="43B",
                                        new_text_start="43B. (1) It shall be the duty",
                                        new_text_end="shall record his observations."), a)
    assert problem is None and text.startswith("(1) It shall be") and text.endswith("observations.")
    assert norm_number("43<sup>A</sup>") == "43A" and norm_number("s. 432 A") == "432A"


def test_replaced_and_inserted_sections_drop_their_leading_number():
    a = clean_text("""Section 288 is hereby repealed and the following section is substituted therefor:–
288. When any person has been sentenced under section 53 of the Penal Code (Chapter 19), such person shall be detained.”.""")
    r = apply_op(op(operation="replace", target_section="288",
                    new_text_start="288. When any person has been sentenced",
                    new_text_end="such person shall be detained."), "old", "H", a, "s.288", NOTE)
    assert r.problem is None and r.text.startswith("When any person") and r.text.endswith("detained.")
