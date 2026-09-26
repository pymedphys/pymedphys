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
import json
import urllib.error

from pymedphys._imports import pytest

from pymedphys._dev.deid_tables import annex_e, chtml, generate, sources
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
FIXTURE_PIN = generate.Pin(
    edition="2099a",
    sources=(
        generate.PinnedSource(
            "part15/chapter_E.html", hashlib.sha256(FIXTURE_PAGE).hexdigest()
        ),
    ),
)


@pytest.fixture(name="source_dir")
def _source_dir(tmp_path):
    directory = tmp_path / "sources"
    (directory / "part15").mkdir(parents=True)
    (directory / "part15" / "chapter_E.html").write_bytes(FIXTURE_PAGE)
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
    requested = _fake_downloads(monkeypatch, {CURRENT_URL: FIXTURE_PAGE})

    assert generate.generate(FIXTURE_PIN, tmp_path / "tables") == 0
    assert requested == [EDITION_URL, CURRENT_URL]
    assert (tmp_path / "tables" / "e1_1.json").exists()


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
