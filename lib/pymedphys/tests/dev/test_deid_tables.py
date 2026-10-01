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
import http.client
import json
import re
import urllib.error

from pymedphys._imports import pytest

from pymedphys._dev.deid_tables import (
    annex_e,
    chtml,
    edition_check,
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
# An IOD whose module includes the IOD's Functional Group Macros, which the
# fixture pin names, and the table that lists those macros.
PS3_3_ENHANCED_IOD = _spanning_table(
    "Table A.99-2. Fixture Enhanced Image IOD Modules",
    IOD_HEADER,
    (
        ("Patient", "Fixture Patient", "C.99.1", "M"),
        ("Image", "Fixture Functional Groups", "C.99.5", "M"),
    ),
)
PS3_3_FUNCTIONAL_GROUP_MACROS = _spanning_table(
    "Table A.99-3. Fixture Enhanced Image Functional Group Macros",
    ("Functional Group Macro", "Section", "Usage"),
    (("Fixture Measures", "C.99.5.1", "M"),),
)
PS3_3_FUNCTIONAL_GROUPS = _spanning_table(
    "Table C.99-5. Fixture Functional Groups Module Attributes",
    ATTRIBUTE_HEADER,
    (
        ("Fixture Code Sequence", "(0998,0040)", "1", "Invented."),
        (("&gt;Include one or more Functional Group Macros.", 1, 3), "Invented."),
    ),
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
    _section("B.99.1", PS3_3_NORMALIZED_IOD),
    _section("C.99.1", PS3_3_PATIENT, PS3_3_PATIENT_MACRO),
    _section("C.99.2", PS3_3_IMAGE),
    _section("C.99.3", PS3_3_OTHER),
    _section("C.99.4b", PS3_3_CONTRAST),
    _section("C.99.5", PS3_3_FUNCTIONAL_GROUPS),
    _section("10.96", PS3_3_REFERENCE_MACRO),
    _section("10.98", PS3_3_WILDCARD_MACRO),
    _section("10.99", PS3_3_CODE_MACRO),
)
PS3_3_DICTIONARY = {row[0]: row[3] for row in TABLE_6_1_ROWS}
PS3_3_CORRECTIONS = (
    ps3_3.Correction("Table C.99-4", "Contrast Module", "Contrast Module Attributes"),
)
PS3_3_FUNCTIONAL_GROUP_IODS = (("Table A.99-2", "Fixture Enhanced Image"),)


def _ps3_3_tables(*tables):
    """Return the fixture's tables, or the given ones, with the corrections."""
    extracted = chtml.extract_tables(
        _page(*(tables or PS3_3_TABLES)), expand_spans=True
    )
    return ps3_3.correct(extracted, PS3_3_CORRECTIONS)


def _collect(*tables, functional_group_iods=PS3_3_FUNCTIONAL_GROUP_IODS):
    return ps3_3.collect(
        _ps3_3_tables(*tables), PS3_3_DICTIONARY, functional_group_iods
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
]


def test_parse_an_iod_modules_table():
    table = _ps3_3_table("Table A.99-1")

    parsed = ps3_3.parse_iod_table("Table A.99-1", table)

    # The IE cell spans the rows of its entity; the table is found later.
    assert parsed == {
        **EXPECTED_IOD,
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
    # pin names for its Functional Group Macros, or their table.
    assert iod_tables == [EXPECTED_IOD]
    # Sorted by label, with numbers compared as numbers. Table C.99-5, which
    # only the IOD left out uses, is not collected.
    assert attribute_tables == EXPECTED_ATTRIBUTE_TABLES


def test_an_iod_whose_modules_include_functional_group_macros_must_be_named():
    with pytest.raises(
        chtml.TableFormatError,
        match="Table A.99-2 includes Functional Group Macros through Table C.99-5",
    ):
        _collect(functional_group_iods=())


@pytest.mark.parametrize(
    "named, message",
    [
        (
            (("Table A.99-2", "Fixture Image"),),
            "the pin names Table A.99-2 for another IOD",
        ),
        (
            (*PS3_3_FUNCTIONAL_GROUP_IODS, ("Table A.99-1", "Fixture Image")),
            "names Table A.99-1, whose modules include no Functional Group Macros",
        ),
        (
            (*PS3_3_FUNCTIONAL_GROUP_IODS, ("Table A.99-3", "Fixture Enhanced Image")),
            "not IOD Modules tables of Annex A: Table A.99-3",
        ),
        (
            (*PS3_3_FUNCTIONAL_GROUP_IODS, ("Table B.99-1", "Fixture Session")),
            "not IOD Modules tables of Annex A: Table B.99-1",
        ),
    ],
)
def test_the_pin_names_exactly_the_iods_with_functional_group_macros(named, message):
    with pytest.raises(chtml.TableFormatError, match=re.escape(message)):
        _collect(functional_group_iods=named)


def test_a_functional_group_macros_row_is_never_parsed_as_an_attribute():
    table = _ps3_3_table("Table C.99-5")

    with pytest.raises(
        chtml.TableFormatError,
        match="row 2 includes an IOD's Functional Group Macros, which are not generated",
    ):
        ps3_3.parse_attribute_table("Table C.99-5", table, PS3_3_DICTIONARY)


def test_collect_fails_when_no_iod_is_generated():
    tables = tuple(table for table in PS3_3_TABLES if "sect_A.99.3" not in table)

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
        match="no Fixture Image Module Attributes table in C.99.2",
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
    functional_group_iods=PS3_3_FUNCTIONAL_GROUP_IODS,
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
        ("iod_modules.json", "PS3.3 IOD Modules", [EXPECTED_IOD]),
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
        (
            {"functional_group_iods": ()},
            "Table A.99-2 includes Functional Group Macros",
        ),
        ({"corrections": ()}, "no Fixture Contrast Module Attributes table"),
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


def test_the_pin_names_the_iods_left_for_their_functional_group_macros():
    # Each of these 2026d IODs lists a module, such as the Multi-frame
    # Functional Groups Module, that includes the IOD's Functional Group
    # Macros. Generation fails if an edition adds or removes one, and so
    # does this test until it is updated with the pin.
    assert dict(generate.PIN.functional_group_iods) == {
        "Table A.8-3": "Multi-frame Grayscale Byte Secondary Capture Image",
        "Table A.8-4": "Multi-frame Grayscale Word Secondary Capture Image",
        "Table A.8-5": "Multi-frame True Color Secondary Capture Image",
        "Table A.32.8-1": "VL Whole Slide Microscopy Image",
        "Table A.32.9-1": "Real-Time Video Endoscopic Image",
        "Table A.32.10-1": "Real-Time Video Photographic Image",
        "Table A.34.11-1": "Real-Time Audio Waveform",
        "Table A.36-1": "Enhanced MR Image",
        "Table A.36-3": "MR Spectroscopy",
        "Table A.36-5": "Enhanced MR Color Image",
        "Table A.38-1": "Enhanced CT Image",
        "Table A.47-1": "Enhanced XA Image",
        "Table A.48-1": "Enhanced XRF Image",
        "Table A.51-1": "Segmentation",
        "Table A.52.3-1": "Ophthalmic Tomography Image",
        "Table A.53-1": "X-Ray 3D Angiographic Image",
        "Table A.54-1": "X-Ray 3D Craniofacial Image",
        "Table A.55-1": "Breast Tomosynthesis Image",
        "Table A.56-1": "Enhanced PET Image",
        "Table A.59-1": "Enhanced US Volume",
        "Table A.66.3-1": "Intravascular Optical Coherence Tomography Image",
        "Table A.70-1": "Legacy Converted Enhanced CT Image",
        "Table A.71-1": "Legacy Converted Enhanced MR Image",
        "Table A.72-1": "Legacy Converted Enhanced PET Image",
        "Table A.74-1": "Breast Projection X-Ray Image",
        "Table A.75-1": "Parametric Map",
        "Table A.84-1": (
            "Ophthalmic Optical Coherence Tomography B-scan Volume Analysis"
        ),
        "Table A.86.1.15-1": "Enhanced RT Image",
        "Table A.86.1.16-1": "Enhanced Continuous RT Image",
        "Table A.89.3-1": "Photoacoustic Image",
        "Table A.90.1.3-1": "Confocal Microscopy Image",
        "Table A.90.2.3-1": "Confocal Microscopy Tiled Pyramidal Image",
        "Table A.91-1": "Height Map Segmentation",
    }
    assert len(generate.PIN.functional_group_iods) == 33


def test_every_storage_sop_class_iod_is_generated_or_named_in_the_pin():
    generated = set(iods.load_iod_tables().iods)
    named = {name for _, name in generate.PIN.functional_group_iods}
    storage = {row.iod_name for row in sop_classes.load_storage_sop_classes().rows}

    assert not generated & named
    assert storage <= generated | named


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


def _fake_downloads(monkeypatch, responses, module=generate):
    """Serve ``responses[url]`` bytes, or a 404 for any other URL."""
    requested = []

    def download(url, filepath):
        requested.append(url)
        if url not in responses:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        with open(filepath, "wb") as file:
            file.write(responses[url])

    monkeypatch.setattr(module, "download_with_progress", download)
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


# The edition check, with the fixture pages, or altered copies of them, served
# as NEMA's current edition.
CHAPTER_E = "chtml/part15/chapter_E.html"
CHAPTER_6 = "chtml/part06/chapter_6.html"
SECTION_E3_10 = "chtml/part15/sect_E.3.10.html"
# A column heading no published table has, which the report must not quote.
SECRET = "Fixture Secret Column"


@pytest.fixture(name="tables_dir")
def _tables_dir(source_dir, tmp_path):
    """The tables generated from the fixture pages, standing for the committed ones."""
    directory = tmp_path / "tables"
    generate.generate(FIXTURE_PIN, directory, source_dir=source_dir)
    return directory


def _check_current(tables_dir, replaced=None, error=None, unfetched=()):
    """Check the fixture pages, with ``replaced`` pages and ``unfetched`` raising ``error``."""
    pages = {**FIXTURE_PAGES, **(replaced or {})}

    def fetch(path):
        if path in unfetched:
            raise error
        return pages[path]

    return edition_check.check_current(FIXTURE_PIN, tables_dir, fetch)


def _replace(page, old, new):
    assert page.count(old) == 1
    return page.replace(old, new)


def _e1_1_page(rows):
    """The fixture's chapter E page, with ``rows`` in Table E.1-1."""
    return _page(
        E1_1A,
        _table(
            "Table E.1-1. Fixture Confidentiality Profile Attributes",
            E1_1_HEADER,
            rows,
        ),
    ).encode("utf-8")


def _http_error(code):
    return urllib.error.HTTPError(SECTION_E3_10, code, "Fixture", None, None)


def _report(result):
    return "\n".join(edition_check.report_lines(result)) + json.dumps(
        dataclasses.asdict(result)
    )


def test_the_pinned_pages_change_no_table(tables_dir):
    result = _check_current(tables_dir)

    assert result.status == "unchanged"
    assert result.pinned_edition == "2099a"
    assert not result.changed_pages
    assert not result.changed_tables
    assert not result.unfetched_pages
    assert not result.failed_tables
    assert result.editions == dict.fromkeys(FIXTURE_PAGES)
    assert edition_check.report_lines(result)[-1] == "Result: unchanged"


def test_a_page_that_changes_no_table_changes_nothing(tables_dir):
    release = (
        '<span class="documentreleaseinformation">'
        "DICOM PS3.15 2099b - Fixture Profiles</span>"
    )
    page = _replace(FIXTURE_PAGE, b"<body>", b"<body>" + release.encode("utf-8"))

    result = _check_current(tables_dir, {CHAPTER_E: page})

    assert result.status == "unchanged"
    assert result.changed_pages == (CHAPTER_E,)
    assert result.editions[CHAPTER_E] == "2099b"
    assert result.editions["html/part03.html"] is None
    assert "Edition the current pages name: 2099b, none" in (
        edition_check.report_lines(result)
    )


def test_a_changed_cell_changes_exactly_its_table(tables_dir):
    assert _e1_1_page(E1_1_ROWS) == FIXTURE_PAGE
    rows = list(E1_1_ROWS)
    # The Basic Profile action of Fixture Label, from Z to X.
    assert rows[1][4] == "Z"
    rows[1] = rows[1][:4] + ("X",) + rows[1][5:]

    result = _check_current(tables_dir, {CHAPTER_E: _e1_1_page(rows)})

    assert result.status == "changed"
    assert result.changed_tables == ("e1_1.json",)
    assert not result.failed_tables
    assert edition_check.report_lines(result)[-3:] == [
        "Tables that would change:",
        "  e1_1.json",
        "Result: changed",
    ]


@pytest.mark.parametrize(
    "path, page, tables",
    [
        (
            CHAPTER_E,
            _replace(
                FIXTURE_PAGE,
                b"<p>Clean Graph. Opt.</p>",
                f"<p>{SECRET}</p>".encode("utf-8"),
            ),
            ["e1_1.json"],
        ),
        # The PS3.3 tables check each tag against the data dictionary, so they
        # fail with it.
        (
            CHAPTER_6,
            _replace(
                FIXTURE_CHAPTER_6_PAGE,
                b"<p>Keyword</p>",
                f"<p>{SECRET}</p>".encode("utf-8"),
            ),
            ["data_dictionary.json", "iod_modules.json", "module_attributes.json"],
        ),
    ],
)
def test_a_page_that_cannot_be_parsed_fails_the_tables_it_serves(
    tables_dir, path, page, tables
):
    result = _check_current(tables_dir, {path: page})

    assert result.status == "failed"
    assert result.failed_tables == {
        table: edition_check.TableFailure((path,), "TableFormatError")
        for table in tables
    }
    assert not result.changed_tables
    assert SECRET not in _report(result)


@pytest.mark.parametrize(
    "error, reported",
    [
        (_http_error(404), "HTTP 404"),
        (TimeoutError("timed out"), "TimeoutError"),
        (http.client.IncompleteRead(b""), "IncompleteRead"),
        (FileNotFoundError(SECTION_E3_10), "FileNotFoundError"),
    ],
)
def test_a_page_that_cannot_be_fetched_fails_the_tables_that_read_it(
    tables_dir, error, reported
):
    result = _check_current(tables_dir, error=error, unfetched={SECTION_E3_10})

    assert result.status == "failed"
    assert result.unfetched_pages == {SECTION_E3_10: reported}
    assert result.failed_tables == {
        "e3_10_1.json": edition_check.TableFailure((SECTION_E3_10,), "not fetched")
    }
    assert not result.changed_tables
    assert SECTION_E3_10 not in result.editions
    assert f"  {SECTION_E3_10} ({reported})" in edition_check.report_lines(result)


def test_a_failure_outranks_a_change(tables_dir):
    rows = [E1_1_ROWS[0], E1_1_ROWS[2]]
    error = _http_error(503)

    result = _check_current(
        tables_dir, {CHAPTER_E: _e1_1_page(rows)}, error, {SECTION_E3_10}
    )

    assert result.changed_tables == ("e1_1.json",)
    assert result.status == "failed"


def test_a_missing_committed_table_would_change(tables_dir):
    (tables_dir / "e1_1a.json").unlink()

    assert _check_current(tables_dir).changed_tables == ("e1_1a.json",)


def test_the_edition_check_downloads_each_page_from_current(monkeypatch, tables_dir):
    current = "https://dicom.nema.org/medical/dicom/current/output/{}"
    requested = _fake_downloads(
        monkeypatch,
        {current.format(path): page for path, page in FIXTURE_PAGES.items()},
        module=edition_check,
    )

    result = edition_check.check_current(
        FIXTURE_PIN, tables_dir, edition_check.download_current
    )

    assert requested == [current.format(path) for path in FIXTURE_PAGES]
    assert result.status == "unchanged"


def _files(directory):
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns) if path.is_file() else None
        for path in directory.rglob("*")
    }


@pytest.mark.parametrize(
    "replaced, status, exit_status",
    [
        ({}, "unchanged", None),
        ({CHAPTER_E: _e1_1_page(E1_1_ROWS[:2])}, "changed", 1),
        ({CHAPTER_6: b"<html></html>"}, "failed", 3),
    ],
)
def test_the_command_checks_the_current_pages_and_writes_only_its_report(
    monkeypatch, tmp_path, tables_dir, capsys, replaced, status, exit_status
):
    monkeypatch.setattr(generate, "PIN", FIXTURE_PIN)
    current_dir = tmp_path / "current"
    for path, page in {**FIXTURE_PAGES, **replaced}.items():
        (current_dir / path).parent.mkdir(parents=True, exist_ok=True)
        (current_dir / path).write_bytes(page)
    monkeypatch.chdir(tables_dir)
    before = _files(tmp_path)
    report = tmp_path / "report.json"
    args = define_parser().parse_args(
        [
            "dev",
            "deid-tables",
            "--check-current",
            "--source-dir",
            str(current_dir),
            "--output-dir",
            str(tables_dir),
            "--json",
            str(report),
        ]
    )

    if exit_status is None:
        args.func(args)
    else:
        with pytest.raises(SystemExit) as exit_info:
            args.func(args)
        assert exit_info.value.code == exit_status

    document = json.loads(report.read_text(encoding="utf-8"))
    assert document["status"] == status
    assert document["pinned_edition"] == "2099a"
    assert capsys.readouterr().out.endswith(f"Result: {status}\n")
    report.unlink()
    assert _files(tmp_path) == before


def test_the_check_options_exclude_each_other(tmp_path):
    parser = define_parser()
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args(["dev", "deid-tables", "--check", "--check-current"])
    assert exit_info.value.code == 2

    args = parser.parse_args(
        ["dev", "deid-tables", "--check", "--json", str(tmp_path / "report.json")]
    )
    with pytest.raises(SystemExit, match="--check-current"):
        args.func(args)
    assert not (tmp_path / "report.json").exists()
