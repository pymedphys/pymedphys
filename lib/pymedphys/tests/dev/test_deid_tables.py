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

"""Parsing DICOM PS3.15 Annex E tables from NEMA's chtml pages.

The HTML below is hand-written. It follows the structure of the published
chtml pages (navigation tables, a ``p.title`` before each table, a header row
of ``th`` cells, and cell text inside ``p`` elements) but contains no rows
from the standard: every attribute in it is invented.
"""

import hashlib

from pymedphys._imports import pytest

from pymedphys._dev.deid_tables import annex_e, chtml, sources

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
    head = "".join(_cell(header_tag, text) for text in header)
    body = "".join(
        '<tr valign="top">' + "".join(_cell("td", text) for text in row) + "</tr>"
        for row in rows
    )
    return (
        '<div class="table"><a id="t" shape="rect"></a>'
        f'<p class="title"><strong>{title}</strong></p>'
        '<div class="table-contents"><table frame="box" rules="all">'
        f'<thead><tr valign="top">{head}</tr></thead><tbody>{body}</tbody>'
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


E1_1A = _table(
    "Table E.1-1a. Fixture Action Codes",
    ("Code", "Meaning"),
    (("X", "remove"), ("Z", "zero length")),
    header_tag="td",
)
E1_1 = _table(
    "Table E.1-1. Fixture Confidentiality Profile Attributes", E1_1_HEADER, E1_1_ROWS
)


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
    assert table.rows == (("Code", "Meaning"), ("X", "remove"), ("Z", "zero length"))


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


def test_select_table_rejects_rows_that_do_not_match_the_header():
    page = _page(_table("Table X-1. Fixture", ("A", "B"), (("1", "2"), ("3",))))

    with pytest.raises(chtml.TableFormatError, match="row 2 has 1 cells"):
        chtml.select_table(chtml.extract_tables(page), "Table X-1")


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


def test_duplicate_tags_fail():
    with pytest.raises(chtml.TableFormatError, match=r"\(0009,1002\) appears 2 times"):
        annex_e.parse_table_e1_1(_e1_1_table(rows=(E1_1_ROWS[1], E1_1_ROWS[1])))


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
