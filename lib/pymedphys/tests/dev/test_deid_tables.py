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

from pymedphys._dev.deid_tables import annex_e, chtml, generate, ps3_6, sources
from pymedphys._dicom.deidentify import standard, uid_registry
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


def _table_6_1(header=TABLE_6_1_HEADER, rows=TABLE_6_1_ROWS):
    page = _page(_table("Table 6-1. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), "Table 6-1")


def _e1_1_table(header=E1_1_HEADER, rows=E1_1_ROWS):
    page = _page(_table("Table E.1-1. Fixture", header, rows))
    return chtml.select_table(chtml.extract_tables(page), "Table E.1-1")


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
    codes = annex_e.parse_table_e1_1a(_e1_1a_table())

    assert [(c.code, c.description) for c in codes] == list(E1_1A_ROWS)


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
FIXTURE_PIN = generate.Pin(
    edition="2099a",
    sources=(
        generate.PinnedSource(
            "part15/chapter_E.html", hashlib.sha256(FIXTURE_PAGE).hexdigest()
        ),
        generate.PinnedSource(
            "part15/sect_E.3.10.html", hashlib.sha256(FIXTURE_E3_10_PAGE).hexdigest()
        ),
        generate.PinnedSource(
            "part06/chapter_6.html", hashlib.sha256(FIXTURE_CHAPTER_6_PAGE).hexdigest()
        ),
        generate.PinnedSource(
            "part06/chapter_A.html", hashlib.sha256(FIXTURE_CHAPTER_A_PAGE).hexdigest()
        ),
    ),
)


@pytest.fixture(name="source_dir")
def _source_dir(tmp_path):
    directory = tmp_path / "sources"
    (directory / "part15").mkdir(parents=True)
    (directory / "part15" / "chapter_E.html").write_bytes(FIXTURE_PAGE)
    (directory / "part15" / "sect_E.3.10.html").write_bytes(FIXTURE_E3_10_PAGE)
    (directory / "part06").mkdir()
    (directory / "part06" / "chapter_6.html").write_bytes(FIXTURE_CHAPTER_6_PAGE)
    (directory / "part06" / "chapter_A.html").write_bytes(FIXTURE_CHAPTER_A_PAGE)
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
        {"path": "part15/chapter_E.html", "sha256": FIXTURE_PIN.sources[0].sha256}
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
            "part15/chapter_E.html",
            [{"code": code, "description": text} for code, text in E1_1A_ROWS],
        ),
        (
            "e3_10_1.json",
            "PS3.15 Table E.3.10-1",
            "part15/sect_E.3.10.html",
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
        {"path": "part06/chapter_6.html", "sha256": FIXTURE_PIN.sources[2].sha256}
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
        {"path": "part06/chapter_A.html", "sha256": FIXTURE_PIN.sources[3].sha256}
    ]
    assert document["rows"] == expected
    assert document["content_sha256"] == standard.content_sha256(expected)


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
    (source_dir / "part15" / "chapter_E.html").write_bytes(FIXTURE_PAGE + b" ")

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
    requested = _fake_downloads(
        monkeypatch,
        {
            CURRENT_URL: FIXTURE_PAGE,
            e3_10_current: FIXTURE_E3_10_PAGE,
            chapter_6_current: FIXTURE_CHAPTER_6_PAGE,
            chapter_a_current: FIXTURE_CHAPTER_A_PAGE,
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
    ]
    for name in ("e1_1.json", "e1_1a.json", "e3_10_1.json", "data_dictionary.json") + (
        tuple(spec.file for spec in uid_registry.UID_TABLES.values())
    ):
        assert (tmp_path / "tables" / name).exists()


def test_download_rejects_a_newer_current_edition(monkeypatch, tmp_path):
    _fake_downloads(monkeypatch, {CURRENT_URL: FIXTURE_PAGE + b"<!-- newer -->"})

    with pytest.raises(
        sources.SourceDigestError, match="no download of part15/chapter_E.html"
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
