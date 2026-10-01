# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parsing DICOM PS3.15 Annex E and PS3.6 tables from NEMA's chtml pages.

The HTML below is hand-written. It follows the structure of the published
chtml pages (navigation tables, a ``p.title`` before each table, a header row
of ``th`` cells, and cell text inside ``p`` elements) but contains no rows
from the standard: every attribute in it is invented.
"""

# The parser and generator tests share the fixture pages below, so they stay
# in one module.
# pylint: disable = too-many-lines

import dataclasses
import hashlib
import json
import re
import urllib.error

from pymedphys._imports import pytest

from pymedphys._dev.deid_tables import (
    annex_e,
    chtml,
    generate,
    ps3_3,
    ps3_4,
    ps3_6,
    ps3_16,
    sources,
)
from pymedphys._dicom.deidentify import (
    codes,
    iods,
    sop_classes,
    standard,
    uid_registry,
)
from pymedphys.cli import define_parser

E1_1_HEADER = (
    "Attribute Name",
    "Tag",
    "Retd. (from PS3.6)",
    "In Std. Comp. IOD (from PS3.3)",
    "Basic Prof.",
    "Rtn. Safe Priv. Opt.",
    "Rtn. UIDs Opt.",
    "Rtn. Dev. Id. Opt.",
    "Rtn. Inst. Id. Opt.",
    "Rtn. Pat. Chars. Opt.",
    "Rtn. Long. Full Dates Opt.",
    "Rtn. Long. Modif. Dates Opt.",
    "Clean Desc. Opt.",
    "Clean Struct. Cont. Opt.",
    "Clean Graph. Opt.",
)

E1_1_ROWS = (
    # An invented attribute whose name contains a zero-width space, as some
    # names in the published table do.
    (
        "Fixture&#8203; Date",
        "(0009,1001)",
        "N",
        "Y",
        "X/D",
        "",
        "",
        "",
        "",
        "",
        "K",
        "C",
        "",
        "",
        "",
    ),
    (
        "Fixture Label",
        "(0009,1002)",
        "Y",
        "N",
        "Z",
        "",
        "",
        "K",
        "",
        "",
        "",
        "",
        "C",
        "",
        "",
    ),
    (
        "Fixture Overlay Data",
        "(60xx,3000)",
        "N",
        "Y",
        "X",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "C",
    ),
    (
        "Private Attributes",
        "(gggg,eeee) where gggg is odd",
        "N",
        "N",
        "X",
        "C",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ),
    (
        "Fixture UID",
        "(0009,1003)",
        "N",
        "Y",
        "X/Z/U*",
        "",
        "K",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ),
)


def _cell(tag, text):
    return f'<{tag} align="left" rowspan="1" colspan="1"><p>{text}</p></{tag}>'


def _table(title, header, rows, header_tag="th"):
    # header is None for a table with no header row, as Table E.1-1a is published.
    head = (
        ""
        if header is None
        else '<thead><tr valign="top">'
        + "".join(_cell(header_tag, text) for text in header)
        + "</tr></thead>"
    )
    body = "".join(
        '<tr valign="top">' + "".join(_cell("td", text) for text in row) + "</tr>"
        for row in rows
    )
    return (
        '<div class="table"><a id="t" shape="rect"></a>'
        f'<p class="title"><strong>{title}</strong></p>'
        '<div class="table-contents"><table frame="box" rules="all">'
        f"{head}<tbody>{body}</tbody>"
        "</table></div></div>"
    )


NAVIGATION = (
    '<div class="navheader"><table width="100%" summary="Navigation header">'
    '<tr><th colspan="3" align="center">E Attribute Confidentiality Profiles</th></tr>'
    '<tr><td><a href="prev.html">Prev</a></td><td> </td>'
    '<td><a href="next.html">Next</a></td></tr></table></div>'
)


def _page(*tables):
    return (
        "<!DOCTYPE html><html><head><title>Fixture</title></head><body>"
        + NAVIGATION
        + "<p>Prose that mentions Table E.1-1 without being its title.</p>"
        + "".join(tables)
        + NAVIGATION.replace("navheader", "navfooter")
        + "</body></html>"
    )


E1_1A_ROWS = tuple(
    (code, f"fixture meaning of {code}")
    for code in ("D", "Z", "X", "K", "C", "U", "Z/D", "X/Z", "X/D", "X/Z/D", "X/Z/U*")
)
E1_1A = _table("Table E.1-1a. Fixture Action Codes", None, E1_1A_ROWS)
E3_10_1_HEADER = ("Data Element", "Private Creator", "VR", "VM", "Meaning")
# The published table leaves some VRs and meanings empty, gives compound VRs
# such as OW/OB, and writes some hexadecimal digits in lower case.
E3_10_1_ROWS = (
    ("(0009,xx01)", "FIXTURE CREATOR", "DS", "1", "Fixture factor"),
    ("(0009,xx0a)", "FIXTURE CREATOR", "OW/OB", "1-n", "Fixture payload"),
    ("(0011,xx02)", "OTHER FIXTURE CREATOR", "", "1", ""),
    (
        "(0009,xx01)",
        "OTHER FIXTURE CREATOR",
        "FL",
        "3-4",
        "Same element, other creator",
    ),
)
E3_10_1 = _table(
    "Table E.3.10-1. Fixture Safe Private Attributes", E3_10_1_HEADER, E3_10_1_ROWS
)
E1_1 = _table(
    "Table E.1-1. Fixture Confidentiality Profile Attributes", E1_1_HEADER, E1_1_ROWS
)


TABLE_6_1_HEADER = ("Tag", "Name", "Keyword", "VR", "VM", "")
# Invented elements in the forms the published table uses: repeating groups
# and masked elements, alternative VRs and VMs, notes in place of a VR or a
# status, a placeholder without a name, and the DICOS and DICONDE registries.
TABLE_6_1_ROWS = (
    ("(0998,0010)", "Fixture's Name", "FixtureName", "PN", "1", ""),
    (
        "(60xx,0998)",
        "Fixture Overlay Value",
        "FixtureOverlayValue",
        "OB or OW",
        "1",
        "",
    ),
    (
        "(0998,0020)",
        "Fixture Lookup Data",
        "FixtureLookupData",
        "US or SS or OW",
        "1-n or 1",
        "RET",
    ),
    (
        "(0998,00x1)",
        "Fixture Coefficient",
        "FixtureCoefficient",
        "US",
        "2-2n",
        "RET (2007)",
    ),
    ("(0998,0030)", "", "", "", "", "RET (2004) - See Note 3"),
    ("(FFFE,E0F0)", "Fixture Item", "FixtureItem", "See Note 2", "1", ""),
    (
        "(0998,0040)",
        "Fixture Code Sequence",
        "FixtureCodeSequence",
        "SQ",
        "1",
        "See Note 1",
    ),
    ("(0998,0050)", "Fixture Inspection", "FixtureInspection", "DS", "3", "DICONDE"),
    ("(0998,0060)", "Fixture Scan", "FixtureScan", "CS", "1-n", "DICOS"),
    (
        "(0998,0080)",
        "Fixture Shared Groups Sequence",
        "FixtureSharedGroupsSequence",
        "SQ",
        "1",
        "",
    ),
    (
        "(0998,0090)",
        "Fixture Frame Groups Sequence",
        "FixtureFrameGroupsSequence",
        "SQ",
        "1",
        "",
    ),
    (
        "(0998,00A0)",
        "Fixture Measures Sequence",
        "FixtureMeasuresSequence",
        "SQ",
        "1",
        "",
    ),
)
TABLE_6_1 = _table(
    "Table 6-1. Fixture Registry of DICOM Data Elements",
    TABLE_6_1_HEADER,
    TABLE_6_1_ROWS,
)


# Invented rows in the forms PS3.6 Annex A uses: retirement marked both in
# the name and by a year in the part, a retired row with neither name nor
# keyword, a keyword with an underscore, DICOS and DICONDE parts, a repeated
# context group name, and context group placeholders.
TABLE_A_1_HEADER = ("UID Value", "UID Name", "UID Keyword", "UID Type", "Part")
TABLE_A_1_ROWS = (
    ("1.2.3.9.1", "Fixture SOP Class", "FixtureSOPClass", "SOP Class", "PS3.4"),
    (
        "1.2.3.9.2",
        "Fixture Transfer Syntax: Default for Fixtures",
        "FixtureTransferSyntax",
        "Transfer Syntax",
        "PS3.5",
    ),
    ("1.2.3.9.3", "Fixture Scheme", "FIXTURE_SCHEME", "Coding Scheme", "PS3.16"),
    (
        "1.2.3.9.4",
        "Fixture Old SOP Class (Retired)",
        "FixtureOldSOPClass",
        "SOP Class",
        "PS3.4 (2001)",
    ),
    ("1.2.3.9.5", "(Retired)", "", "SOP Class", "(2015c)"),
    ("1.2.3.9.6", "Fixture Scan", "FixtureScan", "SOP Class", "DICOS"),
    ("1.2.3.9.7", "Fixture Weld", "FixtureWeld", "SOP Class", "DICONDE ASTM E9999"),
)
TABLE_A_2_HEADER = ("UID Value", "UID Name", "UID Keyword", "Normative Reference")
TABLE_A_2_ROWS = (
    (
        "1.2.3.9.10.1",
        "Fixture Frame of Reference",
        "FixtureFrame",
        "Fixture atlas, https://example.org/atlas",
    ),
)
TABLE_A_3_HEADER = (
    "Context Group UID",
    "Context Group Identifier",
    "Context Group Name",
    "Comment",
)
TABLE_A_3_ROWS = (
    ("1.2.3.9.11.1", "CID 9001", "Fixture Group", ""),
    ("1.2.3.9.11.2", "CID 9002", "Fixture Group", "RET (2013)"),
    ("1.2.3.9.11.3", "", "", "Retired"),
    ("1.2.3.9.11.4", "", "", ""),
)
TABLE_A_4_HEADER = ("UID Value", "UID Name", "UID Type", "Part")
TABLE_A_4_ROWS = (
    ("1.2.3.9.12.1", "Fixture Document", "Document TemplateID", "PS3.20"),
    ("1.2.3.9.12.2", "Fixture Section", "Section TemplateID", "PS3.20"),
)
# Each Annex A table: its header, its rows, and the type each row parses to.
ANNEX_A = {
    "Table A-1": (TABLE_A_1_HEADER, TABLE_A_1_ROWS, uid_registry.RegisteredUID),
    "Table A-2": (
        TABLE_A_2_HEADER,
        TABLE_A_2_ROWS,
        uid_registry.WellKnownFrameOfReference,
    ),
    "Table A-3": (TABLE_A_3_HEADER, TABLE_A_3_ROWS, uid_registry.ContextGroupUID),
    "Table A-4": (TABLE_A_4_HEADER, TABLE_A_4_ROWS, uid_registry.TemplateUID),
}
ANNEX_A_TABLES = tuple(
    _table(f"{label}. Fixture {label}", header, rows)
    for label, (header, rows, _) in ANNEX_A.items()
)


def _annex_a(label, header=None, rows=None):
    default_header, default_rows, _ = ANNEX_A[label]
    header = default_header if header is None else header
    rows = default_rows if rows is None else rows
    page = _page(_table(f"{label}. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), label)


# Invented rows in the forms PS3.16 uses: coding schemes without a UID or
# name, two designators that share a UID, a resources cell listing several
# links, and context group codes that are numbers or letters.
TABLE_8_1_HEADER = (
    "Coding Scheme Designator (0008,0102)",
    "Coding Scheme UID (0008,010C)",
    "Coding Scheme Name (0008,0115)",
    "Coding Scheme Responsible Organization (0008,0116)",
    "Coding Scheme Resources Sequence (0008,0109) Type: URL",
    "Description",
)
TABLE_8_1_ROWS = (
    (
        "FIX",
        "1.2.3.9.20",
        "Fixture Terms",
        "Fixture Body",
        "DOC: https://example.org/fix OWL: https://example.org/fix.owl",
        "Invented terms",
    ),
    (
        "FIX-OLD",
        "1.2.3.9.20",
        "Fixture Terms",
        "Fixture Body",
        "",
        "Retired designator",
    ),
    ("FIX_2", "", "", "", "", ""),
)
TABLE_8_2_HEADER = ("Coding Scheme Designator", "Coding Scheme UID", "Description")
TABLE_8_2_ROWS = (
    ("FixtureVocabularyName", "1.2.3.9.21", ""),
    ("fixtureType", "1.2.3.9.22", "RFC0000"),
)
CID_HEADER = ("Coding Scheme Designator", "Code Value", "Code Meaning")
CID_7050_ROWS = (
    ("FIX", "900001", "Fixture Profile"),
    ("FIX", "900002", "Fixture Option"),
)
CID_7005_ROWS = (
    ("FIX", "900003", "Fixture Equipment"),
    ("FIX", "FIXD", "Fixture Digitizer"),
)
# Each PS3.16 table: its header, its rows, the type each row parses to, and
# the page it is published on.
PS3_16 = {
    "Table 8-1": (TABLE_8_1_HEADER, TABLE_8_1_ROWS, codes.CodingScheme),
    "Table 8-2": (TABLE_8_2_HEADER, TABLE_8_2_ROWS, codes.HL7v3CodingScheme),
    "Table CID 7050": (CID_HEADER, CID_7050_ROWS, codes.CodedConcept),
    "Table CID 7005": (CID_HEADER, CID_7005_ROWS, codes.CodedConcept),
}
PS3_16_PAGES = {
    "chtml/part16/chapter_8.html": ("Table 8-1", "Table 8-2"),
    "chtml/part16/sect_CID_7050.html": ("Table CID 7050",),
    "chtml/part16/sect_CID_7005.html": ("Table CID 7005",),
}


def _ps3_16_page(labels):
    return _page(
        *(_table(f"{label}. Fixture {label}", *PS3_16[label][:2]) for label in labels)
    )


def _ps3_16(label, header=None, rows=None):
    default_header, default_rows, _ = PS3_16[label]
    header = default_header if header is None else header
    rows = default_rows if rows is None else rows
    page = _page(_table(f"{label}. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), label)


def _table_6_1(header=TABLE_6_1_HEADER, rows=TABLE_6_1_ROWS):
    page = _page(_table("Table 6-1. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), "Table 6-1")


def _e1_1_table(header=E1_1_HEADER, rows=E1_1_ROWS):
    page = _page(_table("Table E.1-1. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), "Table E.1-1")


# Invented rows in the forms PS3.4 Table B.5-1 uses: two SOP Classes that share
# an IOD, specializations that cite one section or several, and a name without
# "Storage".
TABLE_B_5_1_HEADER = (
    "SOP Class Name",
    "SOP Class UID",
    "IOD Specification (defined in PS3.3)",
    "Specialization",
)
TABLE_B_5_1_ROWS = (
    ("Fixture Image Storage", "1.2.3.9.30.1", "Fixture Image IOD", ""),
    (
        "Fixture Image Storage - For Processing",
        "1.2.3.9.30.1.1",
        "Fixture Image IOD",
        "B.5.1.99",
    ),
    (
        "Enhanced Fixture Image Storage",
        "1.2.3.9.30.2",
        "Enhanced Fixture Image IOD",
        "B.5.1.98 B.5.1.99",
    ),
    ("Fixture Report", "1.2.3.9.30.3", "Fixture Report IOD", ""),
)
TABLE_B_5_1 = _table(
    "Table B.5-1. Standard SOP Classes", TABLE_B_5_1_HEADER, TABLE_B_5_1_ROWS
)


def _table_b_5_1(header=TABLE_B_5_1_HEADER, rows=TABLE_B_5_1_ROWS):
    page = _page(_table("Table B.5-1. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), "Table B.5-1")


def test_titles_attach_only_to_the_following_table():
    tables = chtml.extract_tables(_page(E1_1A, E1_1))

    titles = [table.title for table in tables]
    assert titles == [
        "",
        "Table E.1-1a. Fixture Action Codes",
        "Table E.1-1. Fixture Confidentiality Profile Attributes",
        "",
    ]


def test_a_title_does_not_carry_past_an_intervening_paragraph():
    figure = '<div class="figure"><p class="title"><strong>Figure E-1. Fixture</strong></p></div>'
    untitled = _table("", ("A",), (("1",),)).replace(
        '<p class="title"><strong></strong></p>', ""
    )
    tables = chtml.extract_tables(_page(figure + "<p>Prose.</p>" + untitled))

    assert [table.title for table in tables] == ["", "", ""]


def test_cells_are_normalised_and_the_header_row_is_separated():
    tables = chtml.extract_tables(_page(E1_1))
    table = chtml.select_table(tables, "Table E.1-1")

    assert table.header == E1_1_HEADER
    assert len(table.rows) == len(E1_1_ROWS)
    # The zero-width space is removed and whitespace collapsed.
    assert table.rows[0][0] == "Fixture Date"


def test_line_breaks_and_entities_become_text():
    page = _page(
        _table("Table X-1. Fixture", ("A", "B"), (("one<br/>two", "&amp; &lt;x&gt;"),))
    )
    table = chtml.select_table(chtml.extract_tables(page), "Table X-1")

    assert table.rows == (("one two", "& <x>"),)


def test_a_table_without_a_header_row_keeps_every_row():
    table = chtml.select_table(chtml.extract_tables(_page(E1_1A)), "Table E.1-1a")

    assert table.header == ()
    assert table.rows == E1_1A_ROWS


def test_a_first_row_of_data_cells_is_not_a_header():
    page = _page(_table("Table X-1. Fixture", ("A", "B"), (("1", "2"),), "td"))
    table = chtml.select_table(chtml.extract_tables(page), "Table X-1")

    assert table.header == ()
    assert table.rows == (("A", "B"), ("1", "2"))


def test_select_table_matches_the_whole_label():
    tables = chtml.extract_tables(_page(E1_1A, E1_1))

    assert chtml.select_table(tables, "Table E.1-1").title.startswith("Table E.1-1.")
    assert chtml.select_table(tables, "Table E.1-1a").title.startswith("Table E.1-1a.")


def test_select_table_requires_exactly_one_match():
    with pytest.raises(chtml.TableFormatError, match="no table titled"):
        chtml.select_table(chtml.extract_tables(_page(E1_1A)), "Table E.1-1")

    with pytest.raises(chtml.TableFormatError, match="2 tables titled"):
        chtml.select_table(chtml.extract_tables(_page(E1_1, E1_1)), "Table E.1-1")


def test_select_table_rejects_merged_cells():
    page = _page(E1_1).replace('colspan="1"><p>Tag', 'colspan="2"><p>Tag', 1)

    with pytest.raises(chtml.TableFormatError, match="merged cells"):
        chtml.select_table(chtml.extract_tables(page), "Table E.1-1")


@pytest.mark.parametrize("row", [(), ("3",), ("3", "4", "5")])
def test_select_table_rejects_rows_that_do_not_match_the_header(row):
    page = _page(_table("Table X-1. Fixture", ("A", "B"), (("1", "2"), row)))

    with pytest.raises(chtml.TableFormatError, match=f"row 2 has {len(row)} cells"):
        chtml.select_table(chtml.extract_tables(page), "Table X-1")


def test_an_empty_first_row_is_preserved_without_becoming_a_header():
    page = _page(_table("Table X-1. Fixture", (), (("1", "2"),)))
    table = chtml.select_table(chtml.extract_tables(page), "Table X-1")

    assert table.header == ()
    assert table.rows == ((), ("1", "2"))


def _spanning_table(title, header, rows):
    """Return a table whose cells are text or (text, rowspan, colspan)."""

    def cell(value):
        text, rowspan, colspan = value if isinstance(value, tuple) else (value, 1, 1)
        return (
            f'<td align="left" rowspan="{rowspan}" colspan="{colspan}">'
            f"<p>{text}</p></td>"
        )

    return _table(title, header, ()).replace(
        "<tbody></tbody>",
        "<tbody>"
        + "".join(
            '<tr valign="top">' + "".join(cell(value) for value in row) + "</tr>"
            for row in rows
        )
        + "</tbody>",
    )


SPANNING = _spanning_table(
    "Table X-1. Fixture",
    ("A", "B", "C"),
    ((("x", 2, 1), "1", "2"), ("3", "4"), (("wide", 1, 3),), ("5", ("pair", 1, 2))),
)


def test_spans_are_expanded_on_request():
    tables = chtml.extract_tables(_page(SPANNING), expand_spans=True)
    table = chtml.select_table(tables, "Table X-1", allow_merged=True)

    assert table.has_merged_cells
    assert table.rows == (
        ("x", "1", "2"),
        ("x", "3", "4"),
        ("wide", "wide", "wide"),
        ("5", "pair", "pair"),
    )


def test_a_place_no_cell_covers_is_empty():
    page = _page(
        _spanning_table(
            "Table X-1. Fixture", ("A", "B", "C"), (("1", "2", ("x", 2, 1)), ("3",))
        )
    )
    table = chtml.extract_tables(page, expand_spans=True)[1]

    assert table.rows == (("1", "2", "x"), ("3", "", "x"))


def test_spans_are_left_as_published_by_default():
    table = chtml.extract_tables(_page(SPANNING))[1]

    assert table.has_merged_cells
    assert table.rows == (("x", "1", "2"), ("3", "4"), ("wide",), ("5", "pair"))


def test_allowing_merged_cells_still_checks_row_lengths():
    tables = chtml.extract_tables(_page(SPANNING))

    with pytest.raises(chtml.TableFormatError, match="row 2 has 2 cells"):
        chtml.select_table(tables, "Table X-1", allow_merged=True)


def test_each_table_records_the_section_it_follows():
    def heading(section):
        return (
            f'<h2 class="title"><a id="sect_{section}" shape="rect"></a>{section}</h2>'
        )

    page = _page(
        heading("X.1"),
        _table("Table X-1. First", ("A",), (("1",),)),
        heading("X.1.1"),
        # An anchor that is not a section's does not change the section.
        '<p><a id="para_1" shape="rect"></a>Prose.</p>',
        _table("Table X-2. Second", ("A",), (("1",),)),
    )

    tables = chtml.extract_tables(page)
    assert [(table.title, table.section) for table in tables] == [
        ("", ""),
        ("Table X-1. First", "X.1"),
        ("Table X-2. Second", "X.1.1"),
        ("", "X.1.1"),
    ]


def test_option_columns_map_to_the_loader_option_names():
    # The parser writes the option names the runtime loader accepts.
    assert tuple(annex_e.OPTION_COLUMNS.values()) == standard.OPTIONS
    assert annex_e.ACTION_CODES is standard.ACTION_CODES


def test_parse_table_e1_1():
    attributes = annex_e.parse_table_e1_1(_e1_1_table())

    assert [attribute.tag for attribute in attributes] == [
        "(0009,1001)",
        "(0009,1002)",
        "(60xx,3000)",
        "(gggg,eeee) where gggg is odd",
        "(0009,1003)",
    ]
    first = attributes[0]
    assert first.name == "Fixture Date"
    assert first.retired is False
    assert first.in_standard_iod is True
    assert first.basic_profile == "X/D"
    assert first.options == {
        "retain_longitudinal_full_dates": "K",
        "retain_longitudinal_modified_dates": "C",
    }
    assert attributes[3].options == {"retain_safe_private": "C"}
    assert attributes[4].basic_profile == "X/Z/U*"


def test_columns_are_mapped_by_header_text_not_position():
    order = list(reversed(range(len(E1_1_HEADER))))
    header = tuple(E1_1_HEADER[i] for i in order)
    rows = tuple(tuple(row[i] for i in order) for row in E1_1_ROWS)

    assert annex_e.parse_table_e1_1(
        _e1_1_table(header, rows)
    ) == annex_e.parse_table_e1_1(_e1_1_table())


def test_unknown_or_missing_columns_fail():
    renamed = ("Rtn. Everything Opt.",) + E1_1_HEADER[1:]
    with pytest.raises(
        chtml.TableFormatError, match="unknown column 'Rtn. Everything Opt.'"
    ):
        annex_e.parse_table_e1_1(_e1_1_table(renamed))

    header = E1_1_HEADER[:-1]
    rows = tuple(row[:-1] for row in E1_1_ROWS)
    with pytest.raises(
        chtml.TableFormatError, match="missing column 'Clean Graph. Opt.'"
    ):
        annex_e.parse_table_e1_1(_e1_1_table(header, rows))


@pytest.mark.parametrize(
    "column, value, message",
    [
        (1, "(0009,100G)", "tag"),
        (1, "0009,1001", "tag"),
        (2, "Yes", "Retd."),
        (4, "", "Basic Prof."),
        (4, "X/Q", "action"),
        (4, "X/X", "action"),
        (6, "K/", "action"),
    ],
)
def test_invalid_values_fail(column, value, message):
    row = list(E1_1_ROWS[1])
    row[column] = value

    with pytest.raises(chtml.TableFormatError, match=message):
        annex_e.parse_table_e1_1(_e1_1_table(rows=(tuple(row),)))


@pytest.mark.parametrize("column", [4, 6])
@pytest.mark.parametrize("action", ["X/K", "D/Z", "U/U*", "U*", "C/K", "X/Z/U"])
def test_undefined_action_combinations_fail(column, action):
    row = list(E1_1_ROWS[1])
    row[column] = action

    with pytest.raises(chtml.TableFormatError, match="action"):
        annex_e.parse_table_e1_1(_e1_1_table(rows=(tuple(row),)))


@pytest.mark.parametrize("action", ["Z/D", "X/Z", "X/D", "X/Z/D", "X/Z/U*"])
def test_defined_compound_actions_are_preserved(action):
    row = list(E1_1_ROWS[1])
    row[4] = action

    (attribute,) = annex_e.parse_table_e1_1(_e1_1_table(rows=(tuple(row),)))

    assert attribute.basic_profile == action


def test_a_table_without_rows_fails():
    with pytest.raises(chtml.TableFormatError, match="no rows"):
        annex_e.parse_table_e1_1(_e1_1_table(rows=()))


def test_parsed_attributes_are_hashable_and_read_only():
    attribute = annex_e.parse_table_e1_1(_e1_1_table())[0]

    assert hash(attribute) == hash(annex_e.parse_table_e1_1(_e1_1_table())[0])
    with pytest.raises(TypeError):
        attribute.options["clean_descriptors"] = "C"  # type: ignore[index]


def test_duplicate_tags_fail():
    with pytest.raises(chtml.TableFormatError, match=r"\(0009,1002\) appears 2 times"):
        annex_e.parse_table_e1_1(_e1_1_table(rows=(E1_1_ROWS[1], E1_1_ROWS[1])))


def _e1_1a_table(rows=E1_1A_ROWS):
    page = _page(_table("Table E.1-1a. Fixture", None, rows))
    return chtml.select_table(chtml.extract_tables(page), "Table E.1-1a")


def _e3_10_1_table(header=E3_10_1_HEADER, rows=E3_10_1_ROWS):
    page = _page(_table("Table E.3.10-1. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), "Table E.3.10-1")


def test_parse_table_e1_1a():
    actions = annex_e.parse_table_e1_1a(_e1_1a_table())

    assert [(a.code, a.description) for a in actions] == list(E1_1A_ROWS)


@pytest.mark.parametrize(
    "rows, message",
    [
        (E1_1A_ROWS[1:], "does not define D"),
        (E1_1A_ROWS + (("U*", "fixture"),), "'U\\*' is not an action code"),
        (E1_1A_ROWS + (E1_1A_ROWS[0],), "D appears 2 times"),
        ((("D", ""),) + E1_1A_ROWS[1:], "row 1: the description is empty"),
        ((("D", "a", "b"),) + E1_1A_ROWS[1:], "row 1 has 3 cells"),
        ((), "has no rows"),
    ],
)
def test_table_e1_1a_defines_exactly_the_implemented_codes(rows, message):
    with pytest.raises(chtml.TableFormatError, match=message):
        annex_e.parse_table_e1_1a(_e1_1a_table(rows))


def test_table_e1_1a_has_no_header_row():
    page = _page(_table("Table E.1-1a. Fixture", ("Code", "Meaning"), E1_1A_ROWS))
    table = chtml.select_table(chtml.extract_tables(page), "Table E.1-1a")

    with pytest.raises(chtml.TableFormatError, match="header row"):
        annex_e.parse_table_e1_1a(table)


def test_parse_table_e3_10_1():
    attributes = annex_e.parse_table_e3_10_1(_e3_10_1_table())

    assert [
        (a.tag, a.private_creator, a.vr, a.vm, a.meaning) for a in attributes
    ] == list(E3_10_1_ROWS)


def test_table_e3_10_1_columns_are_mapped_by_header_text():
    order = (4, 2, 0, 3, 1)
    header = tuple(E3_10_1_HEADER[i] for i in order)
    rows = tuple(tuple(row[i] for i in order) for row in E3_10_1_ROWS)

    assert annex_e.parse_table_e3_10_1(
        _e3_10_1_table(header, rows)
    ) == annex_e.parse_table_e3_10_1(_e3_10_1_table())


@pytest.mark.parametrize(
    "header, message",
    [
        (E3_10_1_HEADER[:-1] + ("Description",), "unknown column 'Description'"),
        (E3_10_1_HEADER[:-1], "missing column 'Meaning'"),
    ],
)
def test_table_e3_10_1_unknown_or_missing_columns_fail(header, message):
    rows = tuple(row[: len(header)] for row in E3_10_1_ROWS)

    with pytest.raises(chtml.TableFormatError, match=message):
        annex_e.parse_table_e3_10_1(_e3_10_1_table(header, rows))


@pytest.mark.parametrize(
    "column, value, message",
    [
        (0, "(0008,xx01)", "not a private"),
        (0, "(0001,xx01)", "not a private"),
        (0, "(FFFF,xx01)", "not a private"),
        (0, "(0009,1001)", "not a private"),
        (0, "0009,xx01", "not a private"),
        (1, "", "private creator is empty"),
        (2, "ds", "VR 'ds'"),
        (2, "D", "VR 'D'"),
        (2, "OW/", "VR 'OW/'"),
        (2, "ZZ", "VR 'ZZ'"),
        (2, "OW/ZZ", "VR 'OW/ZZ'"),
        (3, "n", "VM 'n'"),
        (3, "", "VM ''"),
        (3, "4-3", "VM '4-3'"),
        (3, "3-0", "VM '3-0'"),
    ],
)
def test_table_e3_10_1_invalid_values_fail(column, value, message):
    row = list(E3_10_1_ROWS[0])
    row[column] = value

    with pytest.raises(chtml.TableFormatError, match=f"row 1.*{message}"):
        annex_e.parse_table_e3_10_1(_e3_10_1_table(rows=(tuple(row),)))


@pytest.mark.parametrize("vm", ["0-1", "0-n", "1-1", "2-n"])
def test_table_e3_10_1_accepts_ascending_or_open_multiplicities(vm):
    row = E3_10_1_ROWS[0][:3] + (vm,) + E3_10_1_ROWS[0][4:]

    (attribute,) = annex_e.parse_table_e3_10_1(_e3_10_1_table(rows=(row,)))
    assert attribute.vm == vm


def test_table_e3_10_1_repeated_creator_and_element_fail():
    # The comparison ignores the case of the hexadecimal digits.
    repeated = ("(0009,xx0A)",) + E3_10_1_ROWS[1][1:]

    with pytest.raises(chtml.TableFormatError, match="appears 2 times"):
        annex_e.parse_table_e3_10_1(_e3_10_1_table(rows=E3_10_1_ROWS + (repeated,)))


def test_table_e3_10_1_without_rows_fails():
    with pytest.raises(chtml.TableFormatError, match="has no rows"):
        annex_e.parse_table_e3_10_1(_e3_10_1_table(rows=()))


def test_parse_table_6_1():
    attributes = ps3_6.parse_table_6_1(_table_6_1())

    assert attributes == tuple(
        standard.DictionaryAttribute(*row) for row in TABLE_6_1_ROWS
    )


def test_table_6_1_columns_are_mapped_by_header_text():
    order = (5, 3, 0, 4, 2, 1)
    header = tuple(TABLE_6_1_HEADER[i] for i in order)
    rows = tuple(tuple(row[i] for i in order) for row in TABLE_6_1_ROWS)

    assert ps3_6.parse_table_6_1(_table_6_1(header, rows)) == ps3_6.parse_table_6_1(
        _table_6_1()
    )


@pytest.mark.parametrize(
    "header, message",
    [
        (TABLE_6_1_HEADER[:-1] + ("Status",), "unknown column 'Status'"),
        (TABLE_6_1_HEADER[:-1], "missing column ''"),
    ],
)
def test_table_6_1_unknown_or_missing_columns_fail(header, message):
    rows = tuple(row[: len(header)] for row in TABLE_6_1_ROWS)

    with pytest.raises(chtml.TableFormatError, match=message):
        ps3_6.parse_table_6_1(_table_6_1(header, rows))


@pytest.mark.parametrize(
    "column, value, message",
    [
        (0, "(0999,0010)", "tag '(0999,0010)'"),
        (0, "(0998,010)", "tag '(0998,010)'"),
        (0, "(0998,00aa)", "tag '(0998,00aa)'"),
        (1, "", "a name without a keyword"),
        (2, "", "a name without a keyword"),
        (2, "Fixture Name", "keyword 'Fixture Name'"),
        (3, "XX", "VR 'XX'"),
        (3, "US/SS", "VR 'US/SS'"),
        (3, "US or", "VR 'US or'"),
        (4, "2-3n", "VM '2-3n'"),
        (4, "1 or", "VM '1 or'"),
        (5, "RETIRED", "status 'RETIRED'"),
        (5, "RET (07)", "status 'RET (07)'"),
    ],
)
def test_table_6_1_invalid_values_fail(column, value, message):
    row = list(TABLE_6_1_ROWS[0])
    row[column] = value

    with pytest.raises(chtml.TableFormatError, match=f"row 1.*{re.escape(message)}"):
        ps3_6.parse_table_6_1(_table_6_1(rows=(tuple(row),)))


def test_table_6_1_placeholders_must_be_retired():
    placeholder = ("(0998,0030)", "", "", "", "", "")

    with pytest.raises(chtml.TableFormatError, match="row 1.*not retired"):
        ps3_6.parse_table_6_1(_table_6_1(rows=(placeholder,)))


@pytest.mark.parametrize(
    "repeated, message",
    [
        (("(0998,0010)", "Other Name", "OtherName", "PN", "1", ""), "(0998,0010)"),
        (
            ("(0998,0070)", "Fixture's Name", "FixtureName", "PN", "1", ""),
            "FixtureName",
        ),
    ],
)
def test_table_6_1_repeated_tags_or_keywords_fail(repeated, message):
    with pytest.raises(
        chtml.TableFormatError, match=re.escape(f"{message} appears 2 times")
    ):
        ps3_6.parse_table_6_1(_table_6_1(rows=TABLE_6_1_ROWS + (repeated,)))


def test_table_6_1_without_rows_fails():
    with pytest.raises(chtml.TableFormatError, match="has no rows"):
        ps3_6.parse_table_6_1(_table_6_1(rows=()))


@pytest.mark.parametrize("label", list(ANNEX_A))
def test_parse_annex_a_tables(label):
    _, rows, row_type = ANNEX_A[label]

    assert ps3_6.parse_uid_table(label, _annex_a(label)) == tuple(
        row_type(*row) for row in rows
    )


@pytest.mark.parametrize("label", list(ANNEX_A))
def test_annex_a_columns_are_mapped_by_header_text(label):
    header, rows, _ = ANNEX_A[label]
    reordered = _annex_a(label, header[::-1], tuple(row[::-1] for row in rows))

    assert ps3_6.parse_uid_table(label, reordered) == ps3_6.parse_uid_table(
        label, _annex_a(label)
    )


@pytest.mark.parametrize("label", list(ANNEX_A))
def test_annex_a_unknown_or_missing_columns_fail(label):
    header, rows, _ = ANNEX_A[label]
    renamed = header[:-1] + ("Notes",)

    with pytest.raises(chtml.TableFormatError, match="unknown column 'Notes'"):
        ps3_6.parse_uid_table(label, _annex_a(label, renamed))
    with pytest.raises(chtml.TableFormatError, match=f"missing column {header[-1]!r}"):
        ps3_6.parse_uid_table(
            label, _annex_a(label, header[:-1], tuple(row[:-1] for row in rows))
        )


@pytest.mark.parametrize("label", list(ANNEX_A))
def test_annex_a_tables_without_rows_fail(label):
    with pytest.raises(chtml.TableFormatError, match="has no rows"):
        ps3_6.parse_uid_table(label, _annex_a(label, rows=()))


@pytest.mark.parametrize(
    "label, column, value, message",
    [
        ("Table A-1", 0, "1.02.3", "has a UID"),
        ("Table A-1", 0, "1.2.a", "has a UID"),
        ("Table A-1", 0, "1." + "2" * 63, "has a UID"),
        ("Table A-1", 1, "", "has a name"),
        ("Table A-1", 2, "Fixture Keyword", "has a keyword"),
        ("Table A-1", 3, "SOP class", "has a UID type"),
        ("Table A-1", 4, "Part 4", "has a part"),
        ("Table A-1", 4, "PS3.4 (01)", "has a part"),
        ("Table A-1", 4, "PS3.4 (2001)", "is marked retired in its name or its part"),
        (
            "Table A-1",
            1,
            "Fixture (Retired)",
            "is marked retired in its name or its part",
        ),
        ("Table A-1", 2, "", "has no keyword but is not retired"),
        ("Table A-2", 2, "", "has a keyword"),
        ("Table A-2", 3, "", "has a normative reference"),
        ("Table A-3", 1, "9001", "has an identifier"),
        ("Table A-3", 1, "", "has an identifier without a name"),
        ("Table A-3", 3, "Obsolete", "has a comment"),
        ("Table A-4", 2, "Document Template", "has a UID type"),
        ("Table A-4", 3, "", "has a part"),
    ],
)
def test_annex_a_invalid_values_fail(label, column, value, message):
    _, rows, _ = ANNEX_A[label]
    row = list(rows[0])
    row[column] = value

    with pytest.raises(chtml.TableFormatError, match=re.escape(f"row 1 {message}")):
        ps3_6.parse_uid_table(label, _annex_a(label, rows=(tuple(row),)))


@pytest.mark.parametrize(
    "label, column",
    [("Table A-1", 0), ("Table A-1", 2), ("Table A-3", 0), ("Table A-3", 1)],
)
def test_annex_a_repeated_uids_keywords_or_identifiers_fail(label, column):
    _, rows, _ = ANNEX_A[label]
    repeated = list(rows[1])
    repeated[column] = rows[0][column]

    with pytest.raises(
        chtml.TableFormatError, match=re.escape(f"{rows[0][column]} appears 2 times")
    ):
        ps3_6.parse_uid_table(label, _annex_a(label, rows=(rows[0], tuple(repeated))))


@pytest.mark.parametrize("label", list(PS3_16))
def test_parse_ps3_16_tables(label):
    _, rows, row_type = PS3_16[label]

    assert ps3_16.parse_code_table(label, _ps3_16(label)) == tuple(
        row_type(*row) for row in rows
    )


@pytest.mark.parametrize("label", list(PS3_16))
def test_ps3_16_columns_are_mapped_by_header_text(label):
    header, rows, _ = PS3_16[label]
    reordered = _ps3_16(label, header[::-1], tuple(row[::-1] for row in rows))

    assert ps3_16.parse_code_table(label, reordered) == ps3_16.parse_code_table(
        label, _ps3_16(label)
    )


@pytest.mark.parametrize("label", list(PS3_16))
def test_ps3_16_unknown_or_missing_columns_fail(label):
    header, rows, _ = PS3_16[label]

    with pytest.raises(chtml.TableFormatError, match="unknown column 'Notes'"):
        ps3_16.parse_code_table(label, _ps3_16(label, header[:-1] + ("Notes",)))
    with pytest.raises(chtml.TableFormatError, match=f"missing column {header[-1]!r}"):
        ps3_16.parse_code_table(
            label, _ps3_16(label, header[:-1], tuple(row[:-1] for row in rows))
        )


@pytest.mark.parametrize("label", list(PS3_16))
def test_ps3_16_tables_without_rows_fail(label):
    with pytest.raises(chtml.TableFormatError, match="has no rows"):
        ps3_16.parse_code_table(label, _ps3_16(label, rows=()))


@pytest.mark.parametrize(
    "label, column, value, message",
    [
        ("Table 8-1", 0, "", "has a designator"),
        ("Table 8-1", 0, "FIX TERMS", "has a designator"),
        ("Table 8-1", 0, "F" * 17, "has a designator"),
        ("Table 8-1", 1, "1.02", "has a UID"),
        ("Table 8-2", 0, "", "has a designator"),
        ("Table 8-2", 1, "", "has a UID"),
        ("Table CID 7050", 0, "", "has a coding scheme designator"),
        ("Table CID 7050", 1, "", "has a code value"),
        ("Table CID 7050", 1, "9" * 17, "has a code value"),
        ("Table CID 7005", 2, "", "has a code meaning"),
        ("Table CID 7005", 2, "M" * 65, "has a code meaning"),
        ("Table CID 7050", 1, "900001\\900002", "has a code value"),
        ("Table CID 7005", 2, "First\\Second", "has a code meaning"),
    ],
)
def test_ps3_16_invalid_values_fail(label, column, value, message):
    _, rows, _ = PS3_16[label]
    row = list(rows[0])
    row[column] = value

    with pytest.raises(chtml.TableFormatError, match=re.escape(f"row 1 {message}")):
        ps3_16.parse_code_table(label, _ps3_16(label, rows=(tuple(row),)))


@pytest.mark.parametrize(
    "label, column",
    [("Table 8-1", 0), ("Table 8-2", 0), ("Table 8-2", 1), ("Table CID 7050", 1)],
)
def test_ps3_16_repeated_designators_uids_or_codes_fail(label, column):
    _, rows, _ = PS3_16[label]
    repeated = list(rows[1])
    repeated[column] = rows[0][column]

    with pytest.raises(
        chtml.TableFormatError, match=re.escape(f"{rows[0][column]} appears 2 times")
    ):
        ps3_16.parse_code_table(label, _ps3_16(label, rows=(rows[0], tuple(repeated))))


def test_table_8_1_designators_may_share_a_uid():
    schemes = ps3_16.parse_code_table("Table 8-1", _ps3_16("Table 8-1"))

    assert schemes[0].uid == schemes[1].uid


def test_parse_table_b_5_1():
    rows = ps3_4.parse_table_b_5_1(_table_b_5_1())

    assert rows == tuple(sop_classes.StorageSOPClass(*row) for row in TABLE_B_5_1_ROWS)
    assert rows[1].iod_name == rows[0].iod_name == "Fixture Image"


def test_table_b_5_1_columns_are_mapped_by_header_text():
    reordered = _table_b_5_1(
        header=TABLE_B_5_1_HEADER[::-1],
        rows=tuple(row[::-1] for row in TABLE_B_5_1_ROWS),
    )

    assert ps3_4.parse_table_b_5_1(reordered) == ps3_4.parse_table_b_5_1(_table_b_5_1())


@pytest.mark.parametrize(
    "header, message",
    [
        (
            TABLE_B_5_1_HEADER[:3] + ("Specialisation",),
            "unknown column 'Specialisation'",
        ),
        (TABLE_B_5_1_HEADER[:3], "missing column 'Specialization'"),
    ],
)
def test_table_b_5_1_unknown_or_missing_columns_fail(header, message):
    table = _table_b_5_1(
        header=header, rows=tuple(row[: len(header)] for row in TABLE_B_5_1_ROWS)
    )

    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        ps3_4.parse_table_b_5_1(table)


def test_table_b_5_1_without_rows_fails():
    with pytest.raises(chtml.TableFormatError, match="has no rows"):
        ps3_4.parse_table_b_5_1(_table_b_5_1(rows=()))


@pytest.mark.parametrize(
    "column, value, message",
    [
        (0, "", "row 1 has a name"),
        (1, "1.02", "row 1 has a UID"),
        (2, "Fixture Image", "row 1 has an IOD"),
        (2, "IOD", "row 1 has an IOD"),
        (3, "5.1.99", "row 1 has a specialization"),
        (3, "B.5.1.98, B.5.1.99", "row 1 has a specialization"),
    ],
)
def test_table_b_5_1_invalid_values_fail(column, value, message):
    row = list(TABLE_B_5_1_ROWS[0])
    row[column] = value

    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        ps3_4.parse_table_b_5_1(_table_b_5_1(rows=(tuple(row),) + TABLE_B_5_1_ROWS[1:]))


@pytest.mark.parametrize("column", [0, 1])
def test_table_b_5_1_repeated_names_or_uids_fail(column):
    repeated = list(TABLE_B_5_1_ROWS[1])
    repeated[column] = TABLE_B_5_1_ROWS[0][column]

    with pytest.raises(
        chtml.TableFormatError,
        match=re.escape(f"{TABLE_B_5_1_ROWS[0][column]} appears 2 times"),
    ):
        ps3_4.parse_table_b_5_1(
            _table_b_5_1(rows=(TABLE_B_5_1_ROWS[0], tuple(repeated)))
        )


# PS3.3: IOD modules tables and the attribute tables they reach. As in the
# published tables, an Include row's text spans the name, tag, and Type
# columns, or all four, a heading spans the whole table, and the IE column
# spans the rows of each information entity.
ATTRIBUTE_HEADER = ("Attribute Name", "Tag", "Type", "Attribute Description")


def _section(number, *tables):
    return (
        f'<div class="section"><h3 class="title"><a id="sect_{number}" shape="rect">'
        f"</a>{number} Fixture Section</h3></div>" + "".join(tables)
    )


def _include(depth, label, title, description=None):
    text = f"{'&gt;' * depth}Include {label} “{title}”"
    return ((text, 1, 3), description) if description else ((text, 1, 4),)


IOD_HEADER = ("IE", "Module", "Reference", "Usage")
PS3_3_IOD = _spanning_table(
    "Table A.99-1. Fixture Image IOD Modules",
    IOD_HEADER,
    (
        ("Patient", "Fixture Patient", "C.99.1", "M"),
        (("Image", 3, 1), "Fixture Image", "C.99.2", "C - Required if invented."),
        ("Fixture Other", "C.99.3", "U"),
        # A section inserted after C.99.4, as C.7.6.4b follows C.7.6.4.
        ("Fixture Contrast", "C.99.4b", "U"),
    ),
)
PS3_3_PATIENT = _spanning_table(
    "Table C.99-1. Fixture Patient Module Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture's Name", "(0998,0010)", "2", "Invented."),
        ("Fixture Code Sequence", "(0998,0040)", "3", "Invented."),
        _include(1, "Table 10-99", "Fixture Code Macro Attributes", "Invented CID."),
        ("Fixture Scan", "(0998,0060)", "1C", "Invented."),
    ),
)
# In the patient module's section, but not the module's own table.
PS3_3_PATIENT_MACRO = _spanning_table(
    "Table C.99-1b. Fixture Patient Macro Attributes",
    ATTRIBUTE_HEADER,
    (("Fixture Scan", "(0998,0060)", "3", "Invented."),),
)
PS3_3_IMAGE = _spanning_table(
    "Table C.99-2. Fixture Image Module Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture Overlay Value", "(60xx,0998)", "1", "Invented."),
        ("Fixture Scan", "(0998,0060)", "3", "Invented."),
        _include(0, "Table 10-98", "Fixture Wildcard Macro Attributes"),
    ),
)
PS3_3_OTHER = _spanning_table(
    "Table C.99-3. Fixture Other Module Attributes",
    ("Attribute Name", "Tag", "Type", "Description"),
    (("Fixture Inspection", "(0998,0050)", "2C", "Invented."),),
)
PS3_3_CODE_MACRO = _spanning_table(
    "Table 10-99. Fixture Code Macro Attributes",
    ATTRIBUTE_HEADER,
    (
        (("FIXTURE HEADING", 1, 4),),
        ("Fixture Inspection", "(0998,0050)", "1", "Invented."),
        ("Fixture Code Sequence", "(0998,0040)", "3", "Invented."),
        ("&gt;Fixture Scan", "(0998,0060)", "2", "Invented."),
    ),
)
PS3_3_WILDCARD_MACRO = _spanning_table(
    "Table 10-98. Fixture Wildcard Macro Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture Code Sequence", "(0998,0040)", "3", "Invented."),
        (("&gt;Any Attribute from the fixture.", 1, 2), "2", "Invented."),
        _include(1, "Table 10-99", "Fixture Code Macro Attributes"),
        ("&gt;Fixture Scan", "(0998,0060)", "3", "Invented."),
    ),
)
# Published without "Attributes" in its title, which the fixture pin corrects.
PS3_3_CONTRAST = _spanning_table(
    "Table C.99-4. Fixture Contrast Module",
    ATTRIBUTE_HEADER,
    (
        _include(0, "Table 10-96", "Fixture Reference Macro Attributes"),
        # In the items of the included table's only top-level attribute.
        ("&gt;Fixture Scan", "(0998,0060)", "1C", "Invented."),
    ),
)
PS3_3_REFERENCE_MACRO = _spanning_table(
    "Table 10-96. Fixture Reference Macro Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture Code Sequence", "(0998,0040)", "1", "Invented."),
        ("&gt;Fixture Inspection", "(0998,0050)", "3", "Invented."),
        # A tree of references, as Table C.38.2-3 describes.
        _include(1, "Table 10-96", "Fixture Reference Macro Attributes", "Nested."),
    ),
)
# An IOD whose module includes the IOD's Functional Group Macros, in the
# items of two sequences, as the Multi-frame Functional Groups Module does,
# and the table that lists those macros. The second macro's table is titled
# "Functional Group Macro Attributes", as a few published ones are.
PS3_3_ENHANCED_IOD = _spanning_table(
    "Table A.99-2. Fixture Enhanced Image IOD Modules",
    IOD_HEADER,
    (
        ("Patient", "Fixture Patient", "C.99.1", "M"),
        ("Image", "Fixture Functional Groups", "C.99.5", "M"),
    ),
)
FUNCTIONAL_GROUP_HEADER = ("Functional Group Macro", "Section", "Usage")
PS3_3_FUNCTIONAL_GROUP_MACROS = _spanning_table(
    "Table A.99-3. Fixture Enhanced Image Functional Group Macros",
    FUNCTIONAL_GROUP_HEADER,
    (
        ("Fixture Measures", "C.99.5.1", "M"),
        (
            "Fixture Code",
            "C.99.5.2",
            "C - Required if invented. May not be used as a Shared Functional Group.",
        ),
    ),
)
PS3_3_FUNCTIONAL_GROUPS = _spanning_table(
    "Table C.99-5. Fixture Functional Groups Module Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture Shared Groups Sequence", "(0998,0080)", "1", "Invented."),
        (
            (
                "&gt;Include zero or more Functional Group Macros that are shared "
                "by all Frames.",
                1,
                3,
            ),
            "Invented.",
        ),
        ("Fixture Frame Groups Sequence", "(0998,0090)", "1C", "Invented."),
        (("&gt;Include one or more Functional Group Macros.", 1, 3), "Invented."),
        ("Fixture Inspection", "(0998,0050)", "3", "Invented."),
    ),
)
PS3_3_MEASURES_MACRO = _spanning_table(
    "Table C.99-6. Fixture Measures Macro Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture Measures Sequence", "(0998,00A0)", "1", "Invented."),
        ("&gt;Fixture Inspection", "(0998,0050)", "1C", "Invented."),
    ),
)
PS3_3_CODE_GROUP_MACRO = _spanning_table(
    "Table C.99-7. Fixture Code Functional Group Macro Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture Code Sequence", "(0998,0040)", "2", "Invented."),
        _include(1, "Table 10-99", "Fixture Code Macro Attributes", "Invented."),
    ),
)
# An IOD whose Functional Group Macros the text gives as another IOD's, as
# PS3.3 gives the Enhanced MR Color Image IOD those of the Enhanced MR Image
# IOD.
PS3_3_ENHANCED_COLOR_IOD = _spanning_table(
    "Table A.99-4. Fixture Enhanced Color Image IOD Modules",
    IOD_HEADER,
    (
        ("Patient", "Fixture Patient", "C.99.1", "M"),
        ("Image", "Fixture Functional Groups", "C.99.5", "M"),
    ),
)
# An IOD whose module gives an attribute that the data dictionary lacks, as
# the real-time IODs' Current Frame Functional Groups Module does, after one
# that only it has, whose table is not generated either.
PS3_3_REAL_TIME_IOD = _spanning_table(
    "Table A.99-5. Fixture Real-Time Image IOD Modules",
    IOD_HEADER,
    (
        ("Patient", "Fixture Patient", "C.99.1", "M"),
        (("Image", 2, 1), "Fixture Stream", "C.99.7", "M"),
        ("Fixture Real-Time", "C.99.6", "M"),
    ),
)
PS3_3_STREAM = _spanning_table(
    "Table C.99-10. Fixture Stream Module Attributes",
    ATTRIBUTE_HEADER,
    (("Fixture Inspection", "(0998,0050)", "1", "Invented."),),
)
PS3_3_REAL_TIME = _spanning_table(
    "Table C.99-8. Fixture Real-Time Module Attributes",
    ATTRIBUTE_HEADER,
    (("Fixture Stream Sequence", "(0998,00B0)", "1", "Invented."),),
)
# A Normalized IOD, as Annex B defines them, in their layout.
PS3_3_NORMALIZED_IOD = _spanning_table(
    "Table B.99-1. Fixture Session IOD Modules",
    ("Module", "Reference", "Module Description"),
    (("Fixture Patient", "C.99.1", "Invented."),),
)
PS3_3_TABLES = (
    _section("A.99.3", PS3_3_IOD),
    _section("A.99.4", PS3_3_ENHANCED_IOD, PS3_3_FUNCTIONAL_GROUP_MACROS),
    _section("A.99.5", PS3_3_ENHANCED_COLOR_IOD),
    _section("A.99.6", PS3_3_REAL_TIME_IOD),
    _section("B.99.1", PS3_3_NORMALIZED_IOD),
    _section("C.99.1", PS3_3_PATIENT, PS3_3_PATIENT_MACRO),
    _section("C.99.2", PS3_3_IMAGE),
    _section("C.99.3", PS3_3_OTHER),
    _section("C.99.4b", PS3_3_CONTRAST),
    _section("C.99.5", PS3_3_FUNCTIONAL_GROUPS),
    _section("C.99.5.1", PS3_3_MEASURES_MACRO),
    _section("C.99.5.2", PS3_3_CODE_GROUP_MACRO),
    _section("C.99.6", PS3_3_REAL_TIME),
    _section("C.99.7", PS3_3_STREAM),
    _section("10.96", PS3_3_REFERENCE_MACRO),
    _section("10.98", PS3_3_WILDCARD_MACRO),
    _section("10.99", PS3_3_CODE_MACRO),
)
PS3_3_DICTIONARY = {row[0]: row[3] for row in TABLE_6_1_ROWS}
PS3_3_CORRECTIONS = (
    ps3_3.Correction("Table C.99-4", "Contrast Module", "Contrast Module Attributes"),
)
PS3_3_LEFT_OUT_IODS = (("Table A.99-5", "Fixture Real-Time Image"),)
PS3_3_SHARED_FUNCTIONAL_GROUPS = (
    ("Fixture Enhanced Color Image", "Fixture Enhanced Image"),
)


def _ps3_3_tables(*tables):
    """Return the fixture's tables, or the given ones, with the corrections."""
    extracted = chtml.extract_tables(
        _page(*(tables or PS3_3_TABLES)), expand_spans=True
    )
    return ps3_3.correct(extracted, PS3_3_CORRECTIONS)


def _collect(
    *tables,
    left_out_iods=PS3_3_LEFT_OUT_IODS,
    shared_functional_groups=PS3_3_SHARED_FUNCTIONAL_GROUPS,
):
    return ps3_3.collect(
        _ps3_3_tables(*tables),
        PS3_3_DICTIONARY,
        left_out_iods=left_out_iods,
        shared_functional_groups=shared_functional_groups,
    )


def _replace_section(number, *tables):
    """Return the fixture's sections, with the given tables in section ``number``."""
    return tuple(
        _section(number, *tables) if f'id="sect_{number}"' in section else section
        for section in PS3_3_TABLES
    )


def _ps3_3_table(label, *tables):
    return chtml.select_table(_ps3_3_tables(*tables), label, allow_merged=True)


def _attribute(depth, name, tag, attribute_type):
    return {
        "depth": depth,
        "name": name,
        "tag": tag,
        "type": attribute_type,
        "include": "",
    }


def _include_row(depth, label):
    return {"depth": depth, "name": "", "tag": "", "type": "", "include": label}


EXPECTED_IOD = {
    "label": "Table A.99-1",
    "iod": "Fixture Image",
    "modules": [
        {
            "information_entity": "Patient",
            "module": "Fixture Patient",
            "section": "C.99.1",
            "usage": "M",
            "condition": "",
            "table": "Table C.99-1",
        },
        {
            "information_entity": "Image",
            "module": "Fixture Image",
            "section": "C.99.2",
            "usage": "C",
            "condition": "Required if invented.",
            "table": "Table C.99-2",
        },
        {
            "information_entity": "Image",
            "module": "Fixture Other",
            "section": "C.99.3",
            "usage": "U",
            "condition": "",
            "table": "Table C.99-3",
        },
        {
            "information_entity": "Image",
            "module": "Fixture Contrast",
            "section": "C.99.4b",
            "usage": "U",
            "condition": "",
            "table": "Table C.99-4",
        },
    ],
}
EXPECTED_FUNCTIONAL_GROUP_MACROS = [
    {
        "macro": "Fixture Measures",
        "section": "C.99.5.1",
        "usage": "M",
        "condition": "",
        "table": "Table C.99-6",
    },
    {
        "macro": "Fixture Code",
        "section": "C.99.5.2",
        "usage": "C",
        "condition": (
            "Required if invented. May not be used as a Shared Functional Group."
        ),
        "table": "Table C.99-7",
    },
]
EXPECTED_ENHANCED_IODS = [
    {
        "label": label,
        "iod": iod,
        "modules": [
            EXPECTED_IOD["modules"][0],
            {
                "information_entity": "Image",
                "module": "Fixture Functional Groups",
                "section": "C.99.5",
                "usage": "M",
                "condition": "",
                "table": "Table C.99-5",
            },
        ],
        # The second IOD has the first one's macros, as the pin gives.
        "functional_group_macros": EXPECTED_FUNCTIONAL_GROUP_MACROS,
    }
    for label, iod in [
        ("Table A.99-2", "Fixture Enhanced Image"),
        ("Table A.99-4", "Fixture Enhanced Color Image"),
    ]
]
EXPECTED_ATTRIBUTE_TABLES = [
    {
        "label": "Table 10-96",
        "title": "Fixture Reference Macro Attributes",
        "rows": [
            _attribute(0, "Fixture Code Sequence", "(0998,0040)", "1"),
            _attribute(1, "Fixture Inspection", "(0998,0050)", "3"),
            _include_row(1, "Table 10-96"),
        ],
    },
    {
        "label": "Table 10-98",
        "title": "Fixture Wildcard Macro Attributes",
        "rows": [
            _attribute(0, "Fixture Code Sequence", "(0998,0040)", "3"),
            _attribute(1, "Any Attribute from the fixture.", "", "2"),
            _include_row(1, "Table 10-99"),
            _attribute(1, "Fixture Scan", "(0998,0060)", "3"),
        ],
    },
    {
        "label": "Table 10-99",
        "title": "Fixture Code Macro Attributes",
        "rows": [
            _attribute(0, "Fixture Inspection", "(0998,0050)", "1"),
            _attribute(0, "Fixture Code Sequence", "(0998,0040)", "3"),
            _attribute(1, "Fixture Scan", "(0998,0060)", "2"),
        ],
    },
    {
        "label": "Table C.99-1",
        "title": "Fixture Patient Module Attributes",
        "rows": [
            _attribute(0, "Fixture's Name", "(0998,0010)", "2"),
            _attribute(0, "Fixture Code Sequence", "(0998,0040)", "3"),
            _include_row(1, "Table 10-99"),
            _attribute(0, "Fixture Scan", "(0998,0060)", "1C"),
        ],
    },
    {
        "label": "Table C.99-2",
        "title": "Fixture Image Module Attributes",
        "rows": [
            _attribute(0, "Fixture Overlay Value", "(60xx,0998)", "1"),
            _attribute(0, "Fixture Scan", "(0998,0060)", "3"),
            _include_row(0, "Table 10-98"),
        ],
    },
    {
        "label": "Table C.99-3",
        "title": "Fixture Other Module Attributes",
        "rows": [_attribute(0, "Fixture Inspection", "(0998,0050)", "2C")],
    },
    {
        "label": "Table C.99-4",
        "title": "Fixture Contrast Module Attributes",
        "rows": [
            _include_row(0, "Table 10-96"),
            _attribute(1, "Fixture Scan", "(0998,0060)", "1C"),
        ],
    },
    {
        "label": "Table C.99-5",
        "title": "Fixture Functional Groups Module Attributes",
        "rows": [
            _attribute(0, "Fixture Shared Groups Sequence", "(0998,0080)", "1"),
            # Each IOD's Functional Group Macros, in the items above.
            _include_row(1, "Functional Group Macros"),
            _attribute(0, "Fixture Frame Groups Sequence", "(0998,0090)", "1C"),
            _include_row(1, "Functional Group Macros"),
            _attribute(0, "Fixture Inspection", "(0998,0050)", "3"),
        ],
    },
    {
        "label": "Table C.99-6",
        "title": "Fixture Measures Macro Attributes",
        "rows": [
            _attribute(0, "Fixture Measures Sequence", "(0998,00A0)", "1"),
            _attribute(1, "Fixture Inspection", "(0998,0050)", "1C"),
        ],
    },
    {
        "label": "Table C.99-7",
        "title": "Fixture Code Functional Group Macro Attributes",
        "rows": [
            _attribute(0, "Fixture Code Sequence", "(0998,0040)", "2"),
            _include_row(1, "Table 10-99"),
        ],
    },
]


def test_parse_an_iod_modules_table():
    table = _ps3_3_table("Table A.99-1")

    parsed = ps3_3.parse_iod_table("Table A.99-1", table)

    # The IE cell spans the rows of its entity; the table and the Functional
    # Group Macros are found later.
    assert parsed == {
        "label": EXPECTED_IOD["label"],
        "iod": EXPECTED_IOD["iod"],
        "modules": [
            {key: value for key, value in module.items() if key != "table"}
            for module in EXPECTED_IOD["modules"]
        ],
    }


@pytest.mark.parametrize(
    "replace, replacement, message",
    [
        ("Fixture Image IOD Modules", "Fixture Image Modules", "not an IOD Modules"),
        (">C.99.1<", ">Section C.99.1<", "row 1 has no section reference"),
        # A section number ends in at most one lower-case letter.
        (">C.99.4b<", ">C.99.4B<", "row 4 has no section reference"),
        (">C.99.4b<", ">C.99.4bb<", "row 4 has no section reference"),
        (">C.99.4b<", ">C.99b.4<", "row 4 has no section reference"),
        (">M<", ">R<", "unknown usage"),
        (">C - Required if invented.<", ">C Required if invented.<", "unknown usage"),
        (">C - Required if invented.<", ">C – Required if invented.<", "unknown usage"),
        (">Fixture Other<", ">Fixture Patient<", "Fixture Patient appears 2 times"),
        (">Usage<", ">Use<", "unknown column"),
        (">Patient<", "><", "empty cell"),
    ],
)
def test_malformed_iod_modules_tables_fail(replace, replacement, message):
    page = _page(PS3_3_IOD.replace(replace, replacement, 1))
    table = chtml.select_table(
        chtml.extract_tables(page, expand_spans=True), "Table A.99-1", allow_merged=True
    )

    with pytest.raises(chtml.TableFormatError, match=message):
        ps3_3.parse_iod_table("Table A.99-1", table)


@pytest.mark.parametrize("expected", EXPECTED_ATTRIBUTE_TABLES)
def test_parse_attribute_tables(expected):
    table = _ps3_3_table(expected["label"])

    parsed = ps3_3.parse_attribute_table(expected["label"], table, PS3_3_DICTIONARY)

    assert parsed == expected


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("(0998,0060)", "(0998,0070)", "(0998,0070), which PS3.6 does not define"),
        (">1C<", ">4<", "row 4 is not an attribute, an Include, or a heading"),
        (">1C<", "><", "row 4 is not an attribute, an Include, or a heading"),
        # Two levels below the Include row above it.
        (">Fixture Scan<", ">&gt;&gt;&gt;Fixture Scan<", "row 4 is nested more deeply"),
        (">Fixture's Name<", ">&gt;Fixture's Name<", "row 1 is nested more deeply"),
        (">Tag<", ">Tags<", "unknown column"),
    ],
)
def test_malformed_attribute_tables_fail(old, new, message):
    page = _page(PS3_3_PATIENT.replace(old, new, 1))
    table = chtml.select_table(
        chtml.extract_tables(page, expand_spans=True), "Table C.99-1", allow_merged=True
    )

    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        ps3_3.parse_attribute_table("Table C.99-1", table, PS3_3_DICTIONARY)


def test_rows_nest_only_below_a_sequence():
    # Fixture's Name is PN, so nothing can be nested below it.
    page = _page(
        PS3_3_PATIENT.replace(
            ">Fixture Code Sequence<", ">Fixture Other Name<"
        ).replace("(0998,0040)", "(0998,0010)", 1)
    )
    table = chtml.select_table(
        chtml.extract_tables(page, expand_spans=True), "Table C.99-1", allow_merged=True
    )

    with pytest.raises(chtml.TableFormatError, match="row 3 is nested more deeply"):
        ps3_3.parse_attribute_table("Table C.99-1", table, PS3_3_DICTIONARY)


def test_collect_finds_each_module_table_and_every_table_it_includes():
    iod_tables, attribute_tables = _collect()

    # Only the IOD Modules tables of Annex A are composite IODs: the fixture's
    # Normalized IOD, Table B.99-1, is not collected, nor is the IOD that the
    # pin leaves out. The Functional Group Macros of each IOD are listed with
    # it.
    assert iod_tables == [EXPECTED_IOD, *EXPECTED_ENHANCED_IODS]
    # Sorted by label, with numbers compared as numbers, and including the
    # tables of the Functional Group Macros. Tables C.99-8 and C.99-10, which
    # only the IOD left out uses, are not collected.
    assert attribute_tables == EXPECTED_ATTRIBUTE_TABLES


def test_parse_a_functional_group_macros_table():
    table = _ps3_3_table("Table A.99-3")

    parsed = ps3_3.parse_functional_group_table("Table A.99-3", table)

    # Each macro's table is found later, in its section.
    assert parsed == {
        "label": "Table A.99-3",
        "iod": "Fixture Enhanced Image",
        "macros": [
            {key: value for key, value in macro.items() if key != "table"}
            for macro in EXPECTED_FUNCTIONAL_GROUP_MACROS
        ],
    }


@pytest.mark.parametrize(
    "replace, replacement, message",
    [
        (
            "Image Functional Group Macros",
            "Image Functional Groups",
            "not a Functional Group Macros table",
        ),
        (">Usage<", ">Use<", "unknown column 'Use'"),
        (">C.99.5.1<", ">Section C.99.5.1<", "row 1 has no section reference"),
        (">M<", ">R<", "row 1 has an unknown usage"),
        (">C - Required", ">C – Required", "row 2 has an unknown usage"),
        (">Fixture Code<", ">Fixture Measures<", "Fixture Measures appears 2 times"),
        (">Fixture Measures<", "><", "row 1 has an empty cell"),
    ],
)
def test_malformed_functional_group_macros_tables_fail(replace, replacement, message):
    page = _page(PS3_3_FUNCTIONAL_GROUP_MACROS.replace(replace, replacement, 1))
    table = chtml.select_table(
        chtml.extract_tables(page, expand_spans=True), "Table A.99-3", allow_merged=True
    )

    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        ps3_3.parse_functional_group_table("Table A.99-3", table)


def test_a_functional_group_macros_row_includes_the_iods_macros():
    table = _ps3_3_table("Table C.99-5")

    parsed = ps3_3.parse_attribute_table("Table C.99-5", table, PS3_3_DICTIONARY)

    # Never an attribute: an Include, at its depth, of what each IOD lists.
    assert parsed["rows"][1] == _include_row(1, iods.FUNCTIONAL_GROUP_MACROS)
    assert parsed["rows"][3] == _include_row(1, iods.FUNCTIONAL_GROUP_MACROS)


@pytest.mark.parametrize(
    "text",
    [
        # Without its ">", or in other words than the published ones.
        "Include one or more Functional Group Macros.",
        "&gt;Include some Functional Group Macros.",
    ],
)
def test_an_unknown_functional_group_macros_row_fails(text):
    page = _page(
        PS3_3_FUNCTIONAL_GROUPS.replace(
            "&gt;Include one or more Functional Group Macros.", text
        )
    )
    table = chtml.select_table(
        chtml.extract_tables(page, expand_spans=True), "Table C.99-5", allow_merged=True
    )

    with pytest.raises(chtml.TableFormatError, match="row 4 is not an attribute"):
        ps3_3.parse_attribute_table("Table C.99-5", table, PS3_3_DICTIONARY)


def test_rows_cannot_nest_below_an_include_of_functional_group_macros():
    # Fixture Inspection, two levels down, is one below the Include row.
    tables = _replace_section(
        "C.99.5",
        PS3_3_FUNCTIONAL_GROUPS.replace(
            ">Fixture Inspection<", ">&gt;&gt;Fixture Inspection<"
        ),
    )

    with pytest.raises(
        chtml.TableFormatError,
        match="Table C.99-5 nests rows below its Include of Functional Group Macros",
    ):
        _collect(*tables)


@pytest.mark.parametrize(
    "rows",
    [
        # Two attributes at the top level.
        (
            ("Fixture Measures Sequence", "(0998,00A0)", "1", "Invented."),
            ("Fixture Inspection", "(0998,0050)", "3", "Invented."),
        ),
        # One, which is not a sequence.
        (("Fixture Inspection", "(0998,0050)", "3", "Invented."),),
        # A macro's attributes, without a sequence of their own.
        (_include(0, "Table 10-99", "Fixture Code Macro Attributes"),),
    ],
)
def test_a_functional_group_macro_defines_exactly_one_sequence(rows):
    # Each Functional Group is a sequence of its own (PS3.3 C.7.6.16.1.1), so
    # a macro of any other layout fails.
    macro = _spanning_table(
        "Table C.99-6. Fixture Measures Macro Attributes", ATTRIBUTE_HEADER, rows
    )

    with pytest.raises(
        chtml.TableFormatError,
        match=re.escape(
            "Table C.99-6, the Fixture Measures Functional Group Macro of Table "
            "A.99-3, does not define exactly one top-level attribute, a sequence"
        ),
    ):
        _collect(*_replace_section("C.99.5.1", macro))


def test_a_functional_group_macro_cannot_include_functional_group_macros():
    macro = _spanning_table(
        "Table C.99-6. Fixture Measures Macro Attributes",
        ATTRIBUTE_HEADER,
        (
            ("Fixture Measures Sequence", "(0998,00A0)", "1", "Invented."),
            (("&gt;Include one or more Functional Group Macros.", 1, 3), "Invented."),
        ),
    )

    with pytest.raises(
        chtml.TableFormatError,
        match="Table C.99-6, the Fixture Measures Functional Group Macro of Table "
        "A.99-3, includes Functional Group Macros",
    ):
        _collect(*_replace_section("C.99.5.1", macro))


@pytest.mark.parametrize(
    "text",
    [
        _include(1, "Table 10-99", "Fixture Code Macro Attributes")[0][0],
        "&gt;Include one or more Functional Group Macros.",
    ],
)
def test_an_include_row_spans_the_tag_column(text):
    # A row with a tag of its own is an attribute, whatever its name says.
    page = _page(
        _spanning_table(
            "Table C.99-9. Fixture Include Macro Attributes",
            ATTRIBUTE_HEADER,
            (
                ("Fixture Code Sequence", "(0998,0040)", "1", "Invented."),
                (text, "(0998,0050)", "3", "Invented."),
            ),
        )
    )
    table = chtml.select_table(
        chtml.extract_tables(page, expand_spans=True), "Table C.99-9", allow_merged=True
    )

    rows = ps3_3.parse_attribute_table("Table C.99-9", table, PS3_3_DICTIONARY)["rows"]

    assert (rows[1]["tag"], rows[1]["type"], rows[1]["include"]) == (
        "(0998,0050)",
        "3",
        "",
    )


def test_a_module_or_macro_with_two_tables_in_its_section_fails():
    twice = PS3_3_MEASURES_MACRO.replace("Table C.99-6.", "Table C.99-6b.")

    with pytest.raises(
        chtml.TableFormatError,
        match=re.escape(
            "Table A.99-3 lists Fixture Measures, but C.99.5.1 has 2 tables "
            "titled Fixture Measures Macro Attributes or Fixture Measures "
            "Functional Group Macro Attributes"
        ),
    ):
        _collect(*_replace_section("C.99.5.1", PS3_3_MEASURES_MACRO, twice))


def test_functional_group_macros_included_through_another_table_count():
    # The Fixture Other Module includes the Functional Groups Module's table,
    # so the Fixture Image IOD reaches Functional Group Macros, and has no
    # table of them.
    other = _spanning_table(
        "Table C.99-3. Fixture Other Module Attributes",
        ("Attribute Name", "Tag", "Type", "Description"),
        (
            ("Fixture Inspection", "(0998,0050)", "2C", "Invented."),
            _include(0, "Table C.99-5", "Fixture Functional Groups Module Attributes"),
        ),
    )

    with pytest.raises(
        chtml.TableFormatError,
        match=re.escape(
            "Table A.99-1 includes Functional Group Macros, but no table lists them"
        ),
    ):
        _collect(*_replace_section("C.99.3", other))


def test_a_functional_group_macro_needs_exactly_one_table_in_its_section():
    measures = PS3_3_MEASURES_MACRO.replace(
        "Fixture Measures Macro", "Fixture Measure Macro"
    )

    with pytest.raises(
        chtml.TableFormatError,
        match=re.escape(
            "Table A.99-3 lists Fixture Measures, but C.99.5.1 has no tables "
            "titled Fixture Measures Macro Attributes or Fixture Measures "
            "Functional Group Macro Attributes"
        ),
    ):
        _collect(*_replace_section("C.99.5.1", measures))


def _without_functional_group_macros(*sections):
    """Return the fixture's sections, without Table A.99-3 or the given ones."""
    return tuple(
        _section("A.99.4", PS3_3_ENHANCED_IOD)
        if 'id="sect_A.99.4"' in section
        else section
        for section in PS3_3_TABLES
        if not any(f'id="sect_{number}"' in section for number in sections)
    )


@pytest.mark.parametrize(
    "tables, shared, message",
    [
        # An IOD whose modules include Functional Group Macros needs a table
        # of its own, or one that the pin gives it.
        (
            PS3_3_TABLES,
            (),
            "Table A.99-4 includes Functional Group Macros, but no table lists them",
        ),
        (
            _without_functional_group_macros(),
            (),
            "Table A.99-2 includes Functional Group Macros, but no table lists them",
        ),
        # The pin gives an IOD another's macros only where the IOD has none.
        (
            PS3_3_TABLES,
            (
                *PS3_3_SHARED_FUNCTIONAL_GROUPS,
                ("Fixture Enhanced Image", "Fixture Enhanced Color Image"),
            ),
            "the pin gives Fixture Enhanced Image the Functional Group Macros of "
            "Fixture Enhanced Color Image, but it has its own, in Table A.99-3",
        ),
        (
            _without_functional_group_macros(),
            PS3_3_SHARED_FUNCTIONAL_GROUPS,
            "the pin gives Fixture Enhanced Color Image the Functional Group Macros "
            "of Fixture Enhanced Image, which has no Functional Group Macros table",
        ),
        (
            PS3_3_TABLES,
            (
                *PS3_3_SHARED_FUNCTIONAL_GROUPS,
                ("Fixture Image", "Fixture Enhanced Image"),
            ),
            "Table A.99-1 has Functional Group Macros, but no module includes them",
        ),
        (
            PS3_3_TABLES,
            (
                *PS3_3_SHARED_FUNCTIONAL_GROUPS,
                ("Fixture Absent Image", "Fixture Enhanced Image"),
            ),
            "the pin gives Functional Group Macros to IODs of no IOD Modules table "
            "of Annex A: Fixture Absent Image",
        ),
    ],
)
def test_each_iod_with_functional_group_macros_has_exactly_one_table_of_them(
    tables, shared, message
):
    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        _collect(*tables, shared_functional_groups=shared)


@pytest.mark.parametrize(
    "title, message",
    [
        # Macros for an IOD whose modules include none.
        (
            "Table A.99-9. Fixture Image Functional Group Macros",
            "Table A.99-1 has Functional Group Macros, but no module includes them",
        ),
        # Macros for an IOD that Annex A does not define.
        (
            "Table A.99-9. Fixture Absent Image Functional Group Macros",
            "Table A.99-9 lists the Functional Group Macros of Fixture Absent Image, "
            "which no IOD Modules table of Annex A defines",
        ),
        # A second table for an IOD.
        (
            "Table A.99-9. Fixture Enhanced Image Functional Group Macros",
            "Fixture Enhanced Image appears 2 times",
        ),
    ],
)
def test_every_functional_group_macros_table_belongs_to_one_iod(title, message):
    extra = _spanning_table(
        title, FUNCTIONAL_GROUP_HEADER, (("Fixture Measures", "C.99.5.1", "M"),)
    )

    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        _collect(*PS3_3_TABLES, _section("A.99.9", extra))


def test_an_iod_the_pin_does_not_leave_out_must_be_generated():
    # The real-time fixture gives an attribute that the dictionary lacks.
    with pytest.raises(
        chtml.TableFormatError,
        match=re.escape("row 1 has (0998,00B0), which PS3.6 does not define"),
    ):
        _collect(left_out_iods=())


@pytest.mark.parametrize(
    "named, message",
    [
        (
            (("Table A.99-5", "Fixture Image"),),
            "the pin names Table A.99-5 for another IOD",
        ),
        # The pin leaves out only IODs that cannot be generated.
        (
            (*PS3_3_LEFT_OUT_IODS, ("Table A.99-1", "Fixture Image")),
            "the pin leaves out Table A.99-1, whose Types can be generated",
        ),
        (
            (*PS3_3_LEFT_OUT_IODS, ("Table A.99-3", "Fixture Enhanced Image")),
            "not IOD Modules tables of Annex A: Table A.99-3",
        ),
        (
            (*PS3_3_LEFT_OUT_IODS, ("Table B.99-1", "Fixture Session")),
            "not IOD Modules tables of Annex A: Table B.99-1",
        ),
    ],
)
def test_the_pin_leaves_out_exactly_the_iods_that_cannot_be_generated(named, message):
    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        _collect(left_out_iods=named)


def test_an_iod_left_out_must_fail_only_for_an_undefined_attribute():
    # Any other problem in its tables fails generation.
    real_time = PS3_3_REAL_TIME.replace(">1<", ">4<")

    with pytest.raises(chtml.TableFormatError, match="row 1 is not an attribute"):
        _collect(*_replace_section("C.99.6", real_time))


def test_collect_fails_when_no_iod_is_generated():
    tables = tuple(
        table
        for table in PS3_3_TABLES
        if not any(f"sect_A.99.{number}" in table for number in (3, 4, 5))
    )

    with pytest.raises(
        chtml.TableFormatError, match="no IOD Modules table of Annex A is generated"
    ):
        _collect(*tables)


@pytest.mark.parametrize(
    "rows",
    [
        # Two attributes at the top level.
        (
            ("Fixture Code Sequence", "(0998,0040)", "1", "Invented."),
            ("Fixture Inspection", "(0998,0050)", "3", "Invented."),
        ),
        # One, which is not a sequence.
        (("Fixture Inspection", "(0998,0050)", "3", "Invented."),),
    ],
)
def test_rows_nest_below_an_include_only_of_a_single_sequence(rows):
    macro = _spanning_table(
        "Table 10-96. Fixture Reference Macro Attributes", ATTRIBUTE_HEADER, rows
    )
    tables = tuple(
        _section("10.96", macro) if "sect_10.96" in table else table
        for table in PS3_3_TABLES
    )

    with pytest.raises(
        chtml.TableFormatError,
        match="Table C.99-4 nests rows below its Include of Table 10-96, which "
        "does not define exactly one top-level attribute, a sequence",
    ):
        _collect(*tables)


def test_rows_nest_at_most_one_level_below_an_include():
    page = _page(PS3_3_CONTRAST.replace("&gt;Fixture Scan", "&gt;&gt;Fixture Scan"))
    table = chtml.select_table(
        chtml.extract_tables(page, expand_spans=True), "Table C.99-4", allow_merged=True
    )

    with pytest.raises(chtml.TableFormatError, match="row 2 is nested more deeply"):
        ps3_3.parse_attribute_table("Table C.99-4", table, PS3_3_DICTIONARY)


@pytest.mark.parametrize(
    "rows, reference, message",
    [
        # Each of Tables 10-96 and 10-99 includes the other below a sequence.
        (
            (
                ("Fixture Code Sequence", "(0998,0040)", "3", "Invented."),
                _include(1, "Table 10-96", "Fixture Reference Macro Attributes"),
            ),
            "Table 10-99",
            "Table 10-99 includes itself: Table 10-99 > Table 10-96 > Table 10-99",
        ),
        # Table 10-99 includes itself below the sequence of a macro it
        # includes, not one of its own.
        (
            (
                ("Fixture Inspection", "(0998,0050)", "1", "Invented."),
                _include(0, "Table 10-96", "Fixture Reference Macro Attributes"),
                ("&gt;Fixture Scan", "(0998,0060)", "3", "Invented."),
                _include(1, "Table 10-99", "Fixture Code Macro Attributes"),
            ),
            "Table 10-96",
            "Table 10-99 includes itself: Table 10-99 > Table 10-99",
        ),
    ],
)
def test_a_table_includes_itself_only_below_its_own_sequence(rows, reference, message):
    code_macro = _spanning_table(
        "Table 10-99. Fixture Code Macro Attributes", ATTRIBUTE_HEADER, rows
    )
    # Table 10-96 includes the reference below its own sequence.
    tables = tuple(
        _section("10.99", code_macro)
        if "sect_10.99" in table
        else table.replace("Include Table 10-96", f"Include {reference}")
        if "sect_10.96" in table
        else table
        for table in PS3_3_TABLES
    )

    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        _collect(*tables)


def test_labels_sort_by_their_numbers():
    labels = [
        "Table C.8-10",
        "Table 10-11",
        "Table C.8-9",
        "Table 8.8-1a",
        "Table 8.8-1",
    ]

    assert sorted(labels, key=ps3_3.natural_key) == [
        "Table 8.8-1",
        "Table 8.8-1a",
        "Table 10-11",
        "Table C.8-9",
        "Table C.8-10",
    ]


def test_a_module_needs_exactly_one_table_in_its_section():
    moved = tuple(
        table.replace("C.99.2", "C.99.4") if "sect_C.99.2" in table else table
        for table in PS3_3_TABLES
    )

    with pytest.raises(
        chtml.TableFormatError,
        match="C.99.2 has no tables titled Fixture Image Module Attributes",
    ):
        _collect(*moved)


def test_an_include_of_a_missing_table_fails():
    tables = tuple(table for table in PS3_3_TABLES if "sect_10.99" not in table)

    with pytest.raises(chtml.TableFormatError, match="no table titled 'Table 10-99'"):
        _collect(*tables)


@pytest.mark.parametrize(
    "rows, message",
    [
        (
            (_include(0, "Table 10-97", "Fixture Cycle Macro Attributes"),),
            "Table 10-97 includes itself: Table 10-97 > Table 10-97",
        ),
        # Through another table.
        (
            (_include(0, "Table 10-98", "Fixture Wildcard Macro Attributes"),),
            "Table 10-97 includes itself: Table 10-97 > Table 10-98 > Table 10-97",
        ),
    ],
)
def test_a_cycle_of_includes_fails(rows, message):
    cycle = _section(
        "10.97",
        _spanning_table(
            "Table 10-97. Fixture Cycle Macro Attributes", ATTRIBUTE_HEADER, rows
        ),
    )
    wildcard = PS3_3_WILDCARD_MACRO.replace(
        "</tbody>",
        '<tr valign="top"><td align="left" rowspan="1" colspan="4"><p>Include '
        "Table 10-97 “Fixture Cycle Macro Attributes”</p></td></tr></tbody>",
    )
    tables = tuple(
        table.replace("Table 10-98", "Table 10-97", 1)
        if "sect_C.99.2" in table
        else _section("10.98", wildcard)
        if "sect_10.98" in table
        else table
        for table in PS3_3_TABLES
    ) + (cycle,)

    # Such a cycle would repeat forever.
    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        _collect(*tables)


def test_a_correction_replaces_text_in_one_row_of_its_table():
    tables = chtml.extract_tables(_page(*PS3_3_TABLES), expand_spans=True)

    corrected = ps3_3.correct(
        tables,
        (
            # In a title, a header, and a row.
            ps3_3.Correction("Table C.99-4", "Contrast Module", "Contrast Module X"),
            ps3_3.Correction("Table C.99-3", "Description", "Attribute Description"),
            ps3_3.Correction("Table A.99-1", "C.99.4b", "C.99.4c"),
        ),
    )

    def select(label):
        return chtml.select_table(corrected, label, allow_merged=True)

    assert select("Table C.99-4").title == "Table C.99-4. Fixture Contrast Module X"
    assert select("Table C.99-3").header == ATTRIBUTE_HEADER
    assert select("Table A.99-1").rows[3] == (
        "Image",
        "Fixture Contrast",
        "C.99.4c",
        "U",
    )
    assert (
        select("Table A.99-1").rows[:3]
        == chtml.select_table(tables, "Table A.99-1", allow_merged=True).rows[:3]
    )
    unchanged = ("Table C.99-4.", "Table C.99-3.", "Table A.99-1.")
    assert [table for table in corrected if not table.title.startswith(unchanged)] == [
        table for table in tables if not table.title.startswith(unchanged)
    ]


@pytest.mark.parametrize(
    "correction, message",
    [
        (
            ps3_3.Correction("Table C.99-4", "Absent text", "Text"),
            "Table C.99-4 has 'Absent text' in 0 rows, so its correction no longer",
        ),
        (
            ps3_3.Correction("Table C.99-1", "Invented.", "Text"),
            "Table C.99-1 has 'Invented.' in 3 rows",
        ),
        (
            ps3_3.Correction("Table C.99-9", "Fixture", "Text"),
            "no table titled 'Table C.99-9'",
        ),
    ],
)
def test_a_correction_that_does_not_apply_to_exactly_one_row_fails(correction, message):
    tables = chtml.extract_tables(_page(*PS3_3_TABLES), expand_spans=True)

    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        ps3_3.correct(tables, (correction,))


def test_a_correction_can_replace_text_in_a_stated_number_of_rows():
    # Text in identical cells, such as a usage two macros share, is corrected
    # in each of them, and only if it occurs in exactly that many rows.
    tables = chtml.extract_tables(_page(*PS3_3_TABLES), expand_spans=True)
    twice = ps3_3.Correction("Table C.99-6", "Invented.", "Corrected.", rows=2)

    corrected = ps3_3.correct(tables, (twice,))

    measures = chtml.select_table(corrected, "Table C.99-6", allow_merged=True)
    assert [row[3] for row in measures.rows] == ["Corrected.", "Corrected."]
    with pytest.raises(
        chtml.TableFormatError, match=re.escape("has 'Invented.' in 1 rows")
    ):
        ps3_3.correct(
            tables, (dataclasses.replace(twice, table="Table C.99-3", rows=2),)
        )


def test_a_correction_that_an_edition_has_made_no_longer_applies():
    # The fixture's correction adds "Attributes" to a title, so its published
    # text is still found once an edition fixes the title itself.
    fixed = tuple(
        table.replace("Contrast Module</strong>", "Contrast Module Attributes</strong>")
        for table in PS3_3_TABLES
    )
    tables = chtml.extract_tables(_page(*fixed), expand_spans=True)

    with pytest.raises(
        chtml.TableFormatError,
        match=re.escape(
            "Table C.99-4 already has 'Contrast Module Attributes', so its "
            "correction no longer applies"
        ),
    ):
        ps3_3.correct(tables, PS3_3_CORRECTIONS)


def test_a_source_is_read_only_when_its_digest_matches(tmp_path):
    source = tmp_path / "chapter_E.html"
    source.write_bytes(b"<html></html>")
    digest = hashlib.sha256(b"<html></html>").hexdigest()

    assert sources.read_verified_source(source, digest) == b"<html></html>"
    assert sources.read_verified_source(source, digest.upper()) == b"<html></html>"

    with pytest.raises(sources.SourceDigestError, match="chapter_E.html"):
        sources.read_verified_source(source, "0" * 64)


def test_a_malformed_expected_digest_is_rejected(tmp_path):
    source = tmp_path / "chapter_E.html"
    source.write_bytes(b"")

    with pytest.raises(ValueError, match="64 hexadecimal"):
        sources.read_verified_source(source, "abc")


# The generator, with a pin for the hand-written page instead of NEMA's.
FIXTURE_PAGE = _page(E1_1A, E1_1).encode("utf-8")
FIXTURE_E3_10_PAGE = _page(E3_10_1).encode("utf-8")
FIXTURE_CHAPTER_6_PAGE = _page(TABLE_6_1).encode("utf-8")
FIXTURE_CHAPTER_A_PAGE = _page(*ANNEX_A_TABLES).encode("utf-8")
FIXTURE_PS3_16_PAGES = {
    path: _ps3_16_page(labels).encode("utf-8") for path, labels in PS3_16_PAGES.items()
}
FIXTURE_B_5_PAGE = _page(TABLE_B_5_1).encode("utf-8")
FIXTURE_PS3_3_PAGE = _page(*PS3_3_TABLES).encode("utf-8")
# Each page at its path below output/, as NEMA publishes it.
FIXTURE_PAGES = {
    "chtml/part15/chapter_E.html": FIXTURE_PAGE,
    "chtml/part15/sect_E.3.10.html": FIXTURE_E3_10_PAGE,
    "chtml/part06/chapter_6.html": FIXTURE_CHAPTER_6_PAGE,
    "chtml/part06/chapter_A.html": FIXTURE_CHAPTER_A_PAGE,
    **FIXTURE_PS3_16_PAGES,
    "chtml/part04/sect_B.5.html": FIXTURE_B_5_PAGE,
    "html/part03.html": FIXTURE_PS3_3_PAGE,
}
FIXTURE_PIN = generate.Pin(
    edition="2099a",
    sources=tuple(
        generate.PinnedSource(path, hashlib.sha256(page).hexdigest())
        for path, page in FIXTURE_PAGES.items()
    ),
    left_out_iods=PS3_3_LEFT_OUT_IODS,
    shared_functional_groups=PS3_3_SHARED_FUNCTIONAL_GROUPS,
    corrections=PS3_3_CORRECTIONS,
)


@pytest.fixture(name="source_dir")
def _source_dir(tmp_path):
    directory = tmp_path / "sources"
    for path, page in FIXTURE_PAGES.items():
        (directory / path).parent.mkdir(parents=True, exist_ok=True)
        (directory / path).write_bytes(page)
    return directory


def test_the_pinned_edition_lists_valid_digests():
    assert generate.PIN.edition
    for source in generate.PIN.sources:
        assert len(source.sha256) == 64
        int(source.sha256, 16)


def test_generate_writes_table_e1_1_with_its_provenance(source_dir, tmp_path):
    output_dir = tmp_path / "tables"

    assert generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir) == 0

    document = json.loads((output_dir / "e1_1.json").read_text(encoding="utf-8"))
    assert document["schema"] == generate.SCHEMA
    assert document["table"] == "PS3.15 Table E.1-1"
    assert document["edition"] == "2099a"
    assert document["acknowledgement"] == "DICOM PS3.15 2099a, \u00a9 NEMA"
    assert document["sources"] == [
        {
            "path": "chtml/part15/chapter_E.html",
            "sha256": FIXTURE_PIN.sources[0].sha256,
        }
    ]
    assert [row["tag"] for row in document["rows"]] == [row[1] for row in E1_1_ROWS]
    assert document["rows"][0] == {
        "name": "Fixture Date",
        "tag": "(0009,1001)",
        "retired": False,
        "in_standard_iod": True,
        "basic_profile": "X/D",
        "options": {
            "retain_longitudinal_full_dates": "K",
            "retain_longitudinal_modified_dates": "C",
        },
    }
    canonical = json.dumps(
        document["rows"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert document["content_sha256"] == hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize(
    "name, table, source, rows",
    [
        (
            "e1_1a.json",
            "PS3.15 Table E.1-1a",
            "chtml/part15/chapter_E.html",
            [{"code": code, "description": text} for code, text in E1_1A_ROWS],
        ),
        (
            "e3_10_1.json",
            "PS3.15 Table E.3.10-1",
            "chtml/part15/sect_E.3.10.html",
            [
                dict(zip(("tag", "private_creator", "vr", "vm", "meaning"), row))
                for row in E3_10_1_ROWS
            ],
        ),
    ],
)
def test_generate_writes_the_other_annex_e_tables(
    source_dir, tmp_path, name, table, source, rows
):
    output_dir = tmp_path / "tables"

    assert generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir) == 0

    document = json.loads((output_dir / name).read_text(encoding="utf-8"))
    digests = {pinned.path: pinned.sha256 for pinned in FIXTURE_PIN.sources}
    assert document["table"] == table
    assert document["edition"] == "2099a"
    assert document["acknowledgement"] == "DICOM PS3.15 2099a, \u00a9 NEMA"
    # Each table records only the page it was generated from.
    assert document["sources"] == [{"path": source, "sha256": digests[source]}]
    assert document["rows"] == rows
    assert document["content_sha256"] == standard.content_sha256(rows)


def test_generate_writes_the_data_dictionary(source_dir, tmp_path):
    output_dir = tmp_path / "tables"

    assert generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir) == 0

    document = json.loads(
        (output_dir / "data_dictionary.json").read_text(encoding="utf-8")
    )
    rows = [
        dict(zip(("tag", "name", "keyword", "vr", "vm", "status"), row))
        for row in TABLE_6_1_ROWS
    ]
    assert document["table"] == "PS3.6 Table 6-1"
    assert document["edition"] == "2099a"
    assert document["acknowledgement"] == "DICOM PS3.6 2099a, \u00a9 NEMA"
    assert document["sources"] == [
        {
            "path": "chtml/part06/chapter_6.html",
            "sha256": FIXTURE_PIN.sources[2].sha256,
        }
    ]
    assert document["rows"] == rows
    assert document["content_sha256"] == standard.content_sha256(rows)


@pytest.mark.parametrize("label", list(ANNEX_A))
def test_generate_writes_the_annex_a_tables(source_dir, tmp_path, label):
    output_dir = tmp_path / "tables"
    _, rows, row_type = ANNEX_A[label]

    assert generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir) == 0

    name = uid_registry.UID_TABLES[label].file
    document = json.loads((output_dir / name).read_text(encoding="utf-8"))
    expected = [dataclasses.asdict(row_type(*row)) for row in rows]
    assert document["table"] == f"PS3.6 {label}"
    assert document["acknowledgement"] == "DICOM PS3.6 2099a, \u00a9 NEMA"
    assert document["sources"] == [
        {
            "path": "chtml/part06/chapter_A.html",
            "sha256": FIXTURE_PIN.sources[3].sha256,
        }
    ]
    assert document["rows"] == expected
    assert document["content_sha256"] == standard.content_sha256(expected)


@pytest.mark.parametrize("label", list(PS3_16))
def test_generate_writes_the_ps3_16_tables(source_dir, tmp_path, label):
    output_dir = tmp_path / "tables"
    _, rows, row_type = PS3_16[label]
    page = next(path for path, labels in PS3_16_PAGES.items() if label in labels)
    digests = {pinned.path: pinned.sha256 for pinned in FIXTURE_PIN.sources}

    assert generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir) == 0

    name = codes.CODE_TABLES[label].file
    document = json.loads((output_dir / name).read_text(encoding="utf-8"))
    expected = [dataclasses.asdict(row_type(*row)) for row in rows]
    assert document["table"] == f"PS3.16 {label}"
    assert document["acknowledgement"] == "DICOM PS3.16 2099a, \u00a9 NEMA"
    assert document["sources"] == [{"path": page, "sha256": digests[page]}]
    assert document["rows"] == expected
    assert document["content_sha256"] == standard.content_sha256(expected)


def test_generate_writes_the_storage_sop_classes(source_dir, tmp_path):
    output_dir = tmp_path / "tables"
    digests = {pinned.path: pinned.sha256 for pinned in FIXTURE_PIN.sources}

    assert generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir) == 0

    document = json.loads((output_dir / "sop_classes.json").read_text(encoding="utf-8"))
    rows = [
        dict(zip(("name", "uid", "iod", "specialization"), row))
        for row in TABLE_B_5_1_ROWS
    ]
    assert document["table"] == "PS3.4 Table B.5-1"
    assert document["edition"] == "2099a"
    assert document["acknowledgement"] == "DICOM PS3.4 2099a, \u00a9 NEMA"
    assert document["sources"] == [
        {
            "path": "chtml/part04/sect_B.5.html",
            "sha256": digests["chtml/part04/sect_B.5.html"],
        }
    ]
    assert document["rows"] == rows
    assert document["content_sha256"] == standard.content_sha256(rows)
    assert sop_classes.STORAGE_SOP_CLASS_TABLE.table == document["table"]
    assert sop_classes.STORAGE_SOP_CLASS_TABLE.file == "sop_classes.json"


@pytest.mark.parametrize(
    "name, table, rows",
    [
        (
            "iod_modules.json",
            "PS3.3 IOD Modules",
            [EXPECTED_IOD, *EXPECTED_ENHANCED_IODS],
        ),
        (
            "module_attributes.json",
            "PS3.3 Module Attributes",
            EXPECTED_ATTRIBUTE_TABLES,
        ),
    ],
)
def test_generate_writes_the_ps3_3_tables(source_dir, tmp_path, name, table, rows):
    output_dir = tmp_path / "tables"

    assert generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir) == 0

    document = json.loads((output_dir / name).read_text(encoding="utf-8"))
    assert document["table"] == table
    assert document["acknowledgement"] == "DICOM PS3.3 2099a, \u00a9 NEMA"
    assert document["sources"] == [
        {"path": "html/part03.html", "sha256": FIXTURE_PIN.sources[-1].sha256}
    ]
    assert document["rows"] == rows
    assert document["content_sha256"] == standard.content_sha256(rows)


def test_the_ps3_3_tables_are_named_as_the_loader_expects():
    assert iods.IOD_MODULES_TABLE == "PS3.3 IOD Modules"
    assert iods.MODULE_ATTRIBUTES_TABLE == "PS3.3 Module Attributes"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"left_out_iods": ()}, "which PS3.6 does not define"),
        (
            {"shared_functional_groups": ()},
            "Table A.99-4 includes Functional Group Macros, but no table lists them",
        ),
        ({"corrections": ()}, "no tables titled Fixture Contrast Module Attributes"),
        (
            {"corrections": (ps3_3.Correction("Table C.99-3", "Absent", "Text"),)},
            "its correction no longer applies",
        ),
    ],
)
def test_a_pin_that_no_longer_matches_ps3_3_fails(
    source_dir, tmp_path, change, message
):
    pin = dataclasses.replace(FIXTURE_PIN, **change)

    with pytest.raises(chtml.TableFormatError, match=message):
        generate.generate(pin, tmp_path / "tables", source_dir=source_dir)
    assert not (tmp_path / "tables").exists()


def test_the_pin_leaves_out_the_real_time_iods():
    # Their Current Frame Functional Groups Module gives Current Frame
    # Functional Groups Sequence (0006,0001), which 2026d PS3.6 defines in
    # Table 9-1, not in the data dictionary of Table 6-1. Generation fails if
    # an edition adds an IOD that cannot be generated, or if one of these can
    # be, and so does this test until it is updated with the pin.
    assert dict(generate.PIN.left_out_iods) == {
        "Table A.32.9-1": "Real-Time Video Endoscopic Image",
        "Table A.32.10-1": "Real-Time Video Photographic Image",
        "Table A.34.11-1": "Real-Time Audio Waveform",
    }


def test_the_pin_gives_an_iod_the_functional_group_macros_its_text_names():
    # PS3.3 A.36.4.4: "Table A.36-2 specifies the use of the Functional Group
    # Macros used in the Multi-frame Functional Groups Module for the Enhanced
    # MR Color Image IOD", and Table A.36-2 is the Enhanced MR Image IOD's.
    assert dict(generate.PIN.shared_functional_groups) == {
        "Enhanced MR Color Image": "Enhanced MR Image"
    }


def test_every_storage_sop_class_iod_is_generated():
    generated = set(iods.load_iod_tables().iods)
    left_out = {name for _, name in generate.PIN.left_out_iods}
    storage = {row.iod_name for row in sop_classes.load_storage_sop_classes().rows}

    assert not generated & left_out
    assert storage <= generated


def test_generation_is_byte_for_byte_reproducible(source_dir, tmp_path):
    generate.generate(FIXTURE_PIN, tmp_path / "a", source_dir=source_dir)
    generate.generate(FIXTURE_PIN, tmp_path / "b", source_dir=source_dir)

    first = (tmp_path / "a" / "e1_1.json").read_bytes()
    assert first == (tmp_path / "b" / "e1_1.json").read_bytes()
    assert first.endswith(b"\n")


def test_check_passes_only_when_the_tables_are_current(source_dir, tmp_path, capsys):
    output_dir = tmp_path / "tables"

    assert (
        generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir, check=True)
        == 1
    )
    assert "e1_1.json is missing" in capsys.readouterr().err
    assert not output_dir.exists()

    generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir)
    assert (
        generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir, check=True)
        == 0
    )

    table = output_dir / "e1_1.json"
    table.write_text(
        table.read_text(encoding="utf-8").replace("X/D", "X"), encoding="utf-8"
    )
    before = table.read_bytes()
    assert (
        generate.generate(FIXTURE_PIN, output_dir, source_dir=source_dir, check=True)
        == 1
    )
    assert "e1_1.json differs" in capsys.readouterr().err
    assert table.read_bytes() == before


def test_a_source_with_another_digest_is_not_parsed(source_dir, tmp_path):
    (source_dir / "chtml" / "part15" / "chapter_E.html").write_bytes(
        FIXTURE_PAGE + b" "
    )

    with pytest.raises(sources.SourceDigestError, match="chapter_E.html"):
        generate.generate(FIXTURE_PIN, tmp_path / "tables", source_dir=source_dir)
    assert not (tmp_path / "tables").exists()


def _fake_downloads(monkeypatch, responses):
    """Serve ``responses[url]`` bytes, or a 404 for any other URL."""
    requested = []

    def download(url, filepath):
        requested.append(url)
        if url not in responses:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        with open(filepath, "wb") as file:
            file.write(responses[url])

    monkeypatch.setattr(generate, "download_with_progress", download)
    return requested


EDITION_URL = (
    "https://dicom.nema.org/medical/dicom/2099a/output/chtml/part15/chapter_E.html"
)
CURRENT_URL = (
    "https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html"
)


def test_download_prefers_the_edition_and_falls_back_to_current(monkeypatch, tmp_path):
    e3_10_current = CURRENT_URL.replace("chapter_E.html", "sect_E.3.10.html")
    chapter_6_current = CURRENT_URL.replace(
        "part15/chapter_E.html", "part06/chapter_6.html"
    )
    chapter_a_current = CURRENT_URL.replace(
        "part15/chapter_E.html", "part06/chapter_A.html"
    )
    ps3_16_current = {
        CURRENT_URL.replace("chtml/part15/chapter_E.html", path): page
        for path, page in FIXTURE_PS3_16_PAGES.items()
    }
    b_5_current = CURRENT_URL.replace("part15/chapter_E.html", "part04/sect_B.5.html")
    ps3_3_current = CURRENT_URL.replace(
        "chtml/part15/chapter_E.html", "html/part03.html"
    )
    requested = _fake_downloads(
        monkeypatch,
        {
            CURRENT_URL: FIXTURE_PAGE,
            e3_10_current: FIXTURE_E3_10_PAGE,
            chapter_6_current: FIXTURE_CHAPTER_6_PAGE,
            chapter_a_current: FIXTURE_CHAPTER_A_PAGE,
            **ps3_16_current,
            b_5_current: FIXTURE_B_5_PAGE,
            ps3_3_current: FIXTURE_PS3_3_PAGE,
        },
    )

    assert generate.generate(FIXTURE_PIN, tmp_path / "tables") == 0
    assert requested == [
        EDITION_URL,
        CURRENT_URL,
        EDITION_URL.replace("chapter_E.html", "sect_E.3.10.html"),
        e3_10_current,
        EDITION_URL.replace("part15/chapter_E.html", "part06/chapter_6.html"),
        chapter_6_current,
        EDITION_URL.replace("part15/chapter_E.html", "part06/chapter_A.html"),
        chapter_a_current,
    ] + [
        url
        for path in FIXTURE_PS3_16_PAGES
        for url in (
            EDITION_URL.replace("chtml/part15/chapter_E.html", path),
            CURRENT_URL.replace("chtml/part15/chapter_E.html", path),
        )
    ] + [
        EDITION_URL.replace("part15/chapter_E.html", "part04/sect_B.5.html"),
        b_5_current,
        EDITION_URL.replace("chtml/part15/chapter_E.html", "html/part03.html"),
        ps3_3_current,
    ]
    for name in (
        "e1_1.json",
        "e1_1a.json",
        "e3_10_1.json",
        "data_dictionary.json",
        "iod_modules.json",
        "module_attributes.json",
        "sop_classes.json",
    ) + (
        tuple(spec.file for spec in uid_registry.UID_TABLES.values())
        + tuple(spec.file for spec in codes.CODE_TABLES.values())
    ):
        assert (tmp_path / "tables" / name).exists()


def test_download_rejects_a_newer_current_edition(monkeypatch, tmp_path):
    _fake_downloads(monkeypatch, {CURRENT_URL: FIXTURE_PAGE + b"<!-- newer -->"})

    with pytest.raises(
        sources.SourceDigestError, match="no download of chtml/part15/chapter_E.html"
    ):
        generate.generate(FIXTURE_PIN, tmp_path / "tables")
    assert not (tmp_path / "tables").exists()


def test_the_command_generates_and_checks(monkeypatch, source_dir, tmp_path):
    monkeypatch.setattr(generate, "PIN", FIXTURE_PIN)
    output_dir = tmp_path / "tables"

    def run(*options):
        args = define_parser().parse_args(
            [
                "dev",
                "deid-tables",
                "--source-dir",
                str(source_dir),
                "--output-dir",
                str(output_dir),
                *options,
            ]
        )
        args.func(args)

    run()
    assert (output_dir / "e1_1.json").exists()
    run("--check")

    (output_dir / "e1_1.json").unlink()
    with pytest.raises(SystemExit) as exit_info:
        run("--check")
    assert exit_info.value.code == 1
