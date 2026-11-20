"""Unit tests for the legal structure detector, one per layout quirk found in real PDFs."""

from backend.rag.ingestion.parser import ParsedDocument, ParsedPage
from backend.rag.ingestion.structure import Node, build_tree


def doc(*pages: str | tuple[str, str | None, str | None]) -> ParsedDocument:
    out = []
    for i, p in enumerate(pages, start=1):
        md, header, footer = (p, None, None) if isinstance(p, str) else p
        out.append(ParsedPage(pdf_page=i, markdown=md, header=header, footer=footer))
    return ParsedDocument(source_file="test.pdf", file_hash="x", tier="test", pages=out)


def sections(act: Node) -> list[str]:
    return [n.number for n, _ in act.walk() if n.level == "section"]


def find(act: Node, level: str, number: str) -> Node:
    return next(n for n, _ in act.walk() if n.level == level and n.number == number)


GAZETTE_ACT = """\
# PARLIAMENT OF THE DEMOCRATIC SOCIALIST REPUBLIC OF SRI LANKA

# COMPUTER CRIME ACT, No. 24 OF 2007

BE it enacted by the Parliament of the Democratic Socialist Republic of Sri Lanka as follows :-

[MARGINAL NOTE: Short title.]

**1.** This Act may be cited as the Computer Crime Act, No.24 of 2007.

# PART I

## COMPUTER CRIME

[MARGINAL NOTE: Application of this Act.]

**2.** (1) The provisions of this Act shall apply where—

(*a*) a person commits an offence ;

(\\*b) the computer was in Sri Lanka ;

(2) For the purposes of paragraph (*d*) "person" includes a body of persons.

Explanation 1— for the purposes of paragraph (a) the mere turning on is sufficient.

[MARGINAL NOTE: Interpretation.]

**3.** In this Act, unless the context otherwise requires,—

“computer” means an electronic or similar device;

“document” includes an electronic record;
"""


def test_gazette_act_hierarchy():
    acts = build_tree(doc(GAZETTE_ACT))
    assert len(acts) == 1, "enacting formula must not start a second Act"
    act = acts[0]
    assert "COMPUTER CRIME ACT" in act.heading.upper()
    assert sections(act) == ["1", "2", "3"]

    s2 = find(act, "section", "2")
    assert s2.heading == "Application of this Act"
    part = next(a for n, anc in act.walk() if n is s2 for a in anc if a.level == "part")
    assert part.number == "I" and part.heading == "COMPUTER CRIME"

    sub1 = find(act, "subsection", "(1)")
    assert [c.number for c in sub1.children] == ["(a)", "(b)"], "label variants normalised"
    assert any(c.level == "explanation" for c in find(act, "subsection", "(2)").children
               + s2.children)

    s3 = find(act, "section", "3")
    terms = [c.term for c in s3.children if c.level == "definition"]
    assert terms == ["computer", "document"]
    assert "electronic record" in s3.full_text(), "definitions included in section text"


AMENDMENT_ACT = """\
# PARLIAMENT OF THE DEMOCRATIC SOCIALIST REPUBLIC OF SRI LANKA

# CODE OF CRIMINAL PROCEDURE (AMENDMENT) ACT, No. 18 OF 2022

[MARGINAL NOTE: Short title]

**1.** This Act may be cited as the Code of Criminal Procedure (Amendment) Act, No.18 of 2022.

[MARGINAL NOTE: Replacement of section 442 of Act, No. 15 of 1979]

**2.** Section 442 of the principal enactment is hereby repealed and the following section is substituted therefor: -

[MARGINAL NOTE: "Copies of a judgment or final order]

442. If any person affected by a judgment desires to have a copy, he shall be furnished therewith.

**3.** Section 443 of the principal enactment is hereby amended in paragraph (*b*).

**4.** In the event of any inconsistency, the Sinhala text shall prevail.
"""


def test_quoted_replacement_section_stays_inside_amending_section():
    act = build_tree(doc(AMENDMENT_ACT))[0]
    assert sections(act) == ["1", "2", "3", "4"]
    assert "442. If any person" in find(act, "section", "2").full_text()
    # the quoted section's marginal note must not become the heading of section 3
    assert find(act, "section", "3").heading is None
    assert "Copies of a judgment" in find(act, "section", "2").full_text()


def test_multiple_acts_in_one_pdf():
    acts = build_tree(doc(GAZETTE_ACT, AMENDMENT_ACT))
    assert len(acts) == 2
    assert "AMENDMENT" in acts[1].heading.upper()
    assert sections(acts[1]) == ["1", "2", "3", "4"]


LANKALAW_PAGE = """\
# CODE OF CRIMINAL PROCEDURE

Short title 678-14-1991 **1**. This Act (hereinafter referred to as "the Code") may be cited as the Code of Criminal Procedure Act.

# PART I

**Interpretation. 2**. In this Code unless the context otherwise requires -

"Attorney-General." "Attorney-General" means the Attorney-General of the Republic;

"Peace officer." "Peace officer" includes a police officer; [2,12 of 1988]

**Aid to other than peace officers executing warrant.** **3**. When a warrant is directed to a person other than a peace officer.

Registries of **4**. summons.

**Trial of offences under Penal Code.** 5. All offences shall be tried.
"""

LANKALAW_PAGE_2 = """\
# PART I

**6**. The repeated Part heading above must not create a second Part I.

Person arrested not to be detained more than twenty-four hours.

**7**. Any peace officer shall not detain in custody a person arrested without a warrant.

Provisions of sections 24,25 and 27 to apply to arrested under section 7. **8**. The sections 24, 25 and 27 shall apply to arrest under section 7.

Special provisions regarding persons arrested in respect of child abuse. **8A**

(1) The provisions of sections 6 and 7 shall not apply in relation to persons suspected of child abuse.
"""


def test_lankalaw_inline_marginal_notes_and_amendment_refs():
    act = build_tree(doc(LANKALAW_PAGE, LANKALAW_PAGE_2))[0]
    assert act.heading == "Code of Criminal Procedure Act"
    assert sections(act) == ["1", "2", "3", "4", "5", "6", "7", "8", "8A"]
    assert find(act, "section", "1").heading == "Short title"
    # plain heading line before the section number
    assert find(act, "section", "7").heading == ("Person arrested not to be detained more than "
                                                 "twenty-four hours")
    # heading containing numbers ("... under section 7. **8**.") must not be cut at "7."
    assert find(act, "section", "8").heading.endswith("arrested under section 7")
    # number at the end of the line with no dot; its text must not leak into section 8
    s8a = find(act, "section", "8A")
    assert s8a.heading == "Special provisions regarding persons arrested in respect of child abuse"
    assert "child abuse" not in find(act, "section", "8").full_text()
    assert find(act, "section", "3").heading == "Aid to other than peace officers executing warrant"
    assert find(act, "section", "4").heading == "Registries of summons"
    assert find(act, "section", "5").heading == "Trial of offences under Penal Code"

    s2 = find(act, "section", "2")
    assert [c.term for c in s2.children if c.level == "definition"] == ["Attorney-General",
                                                                        "Peace officer"]
    assert "Amended by s.2 of Act No. 12 of 1988" in s2.footnotes

    parts = [n for n, _ in act.walk() if n.level == "part"]
    assert len(parts) == 1


def test_constitution_footnotes_from_footer_and_article_labels():
    markdown = (
        "# THE CONSTITUTION OF THE\n\n# DEMOCRATIC SOCIALIST REPUBLIC OF SRI LANKA\n\n"
        "[MARGINAL NOTE: Interpretation]\n\n"
        "111M. (a) In this Chapter a Judge of the <sup>112</sup>[Court of Appeal] is excluded.\n"
    )
    page = (
        markdown,
        "The Constitution of the Democratic Socialist Republic of Sri Lanka\n127",
        "112 - Substituted by the Twenty First Amendment to the\nConstitution Sec. 16.",
    )
    act = build_tree(doc(page))[0]
    assert act.heading.startswith("THE CONSTITUTION OF THE DEMOCRATIC SOCIALIST REPUBLIC")
    art = find(act, "section", "111M")
    assert art.label() == "Art.111M"
    assert art.footnotes == ["Substituted by the Twenty First Amendment to the Constitution Sec. 16."]
    assert "<sup>" not in art.full_text()
    assert art.printed_page_start == "127"
