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

"""Converting AAPM's TG-263 Structure Spreadsheet to JSON.

The spreadsheet in ``data/`` is invented. It copies the published layout,
including its irregularities: padded values, an unlabelled column holding a
note, and an "N Characters" value that disagrees with the name it counts.
"""

import dataclasses
import hashlib
import json
import pathlib
import re
import types

from pymedphys._imports import pytest

from pymedphys._nomenclature import tg263

SPREADSHEET = pathlib.Path(__file__).parent / "data" / "tg263_invented.xls"

HEADER = (
    "Target Type",
    "Major Category",
    "Minor Category",
    "Anatomic Group",
    "N Characters",
    "TG263-Primary Name",
    "TG-263-Reverse Order Name",
    "Description",
    "FMAID",
    "",
)
ROWS = (
    (
        "Anatomic",
        "Fixture Organ",
        "Fixture Lobe",
        "Thorax",
        12.0,
        "Fixture_Lobe",
        "Lobe_Fixture",
        "Fixture lobe",
        1001.0,
        "",
    ),
    (
        "Anatomic ",
        "Fixture Organ",
        "",
        "Abdomen",
        9.0,
        "Fixture_R ",
        "R_Fixture",
        "",
        "",
        "Fixture note in an unlabelled column",
    ),
    (
        "Non_Anatomic",
        "Fixture Device",
        "",
        "Pelvis",
        99.0,
        "FixtureDevice",
        "Device_Fixture",
        "Invented  device",
        "",
        "",
    ),
    (
        "Target",
        "Fixture Target",
        "",
        "",
        7.0,
        "PTV_Fix",
        "Fix_PTV",
        "Invented target",
        "",
        "",
    ),
)
STRUCTURES = (
    tg263.Structure(
        target_type="Anatomic",
        major_category="Fixture Organ",
        minor_category="Fixture Lobe",
        anatomic_group="Thorax",
        primary_name="Fixture_Lobe",
        reverse_order_name="Lobe_Fixture",
        description="Fixture lobe",
        fma_id=1001,
    ),
    tg263.Structure(
        target_type="Anatomic",
        major_category="Fixture Organ",
        minor_category="",
        anatomic_group="Abdomen",
        primary_name="Fixture_R",
        reverse_order_name="R_Fixture",
        description="",
        fma_id=None,
    ),
    tg263.Structure(
        target_type="Non_Anatomic",
        major_category="Fixture Device",
        minor_category="",
        anatomic_group="Pelvis",
        primary_name="FixtureDevice",
        reverse_order_name="Device_Fixture",
        description="Invented  device",
        fma_id=None,
    ),
    tg263.Structure(
        target_type="Target",
        major_category="Fixture Target",
        minor_category="",
        anatomic_group="",
        primary_name="PTV_Fix",
        reverse_order_name="Fix_PTV",
        description="Invented target",
        fma_id=None,
    ),
)


def _column(name):
    return HEADER.index(name)


def _with(row, name, value):
    row = list(row)
    row[_column(name)] = value
    return tuple(row)


def test_read_spreadsheet():
    nomenclature = tg263.read_spreadsheet(SPREADSHEET)

    assert nomenclature.structures == STRUCTURES
    assert nomenclature.source == tg263.Source(
        file="tg263_invented.xls",
        sha256=hashlib.sha256(SPREADSHEET.read_bytes()).hexdigest(),
        sheet="TG263 v20990101",
    )
    assert nomenclature.attribution == tg263.ATTRIBUTION


def test_parse_sheet():
    assert tg263.parse_sheet((HEADER,) + ROWS) == STRUCTURES


def test_columns_are_mapped_by_header_text():
    order = (9, 8, 7, 6, 5, 4, 3, 2, 1, 0)
    rows = tuple(tuple(row[i] for i in order) for row in (HEADER,) + ROWS)

    assert tg263.parse_sheet(rows) == STRUCTURES


def test_blank_rows_are_skipped():
    blank = ("",) * len(HEADER)

    assert tg263.parse_sheet((HEADER, blank) + ROWS + (blank,)) == STRUCTURES


@pytest.mark.parametrize(
    "header, message",
    [
        (HEADER[:-1] + ("Notes",), "unknown column 'Notes'"),
        (HEADER[:5] + ("",) + HEADER[6:], "missing column 'TG263-Primary Name'"),
        (HEADER[:-1] + ("FMAID",), "column 'FMAID' appears 2 times"),
    ],
)
def test_unknown_missing_or_repeated_columns_fail(header, message):
    with pytest.raises(tg263.TG263Error, match=re.escape(message)):
        tg263.parse_sheet((header,) + ROWS)


@pytest.mark.parametrize(
    "column, value, message",
    [
        ("TG263-Primary Name", "  ", "'TG263-Primary Name' is empty"),
        (
            "TG263-Primary Name",
            "Fixture Lobe",
            "'TG263-Primary Name' contains whitespace",
        ),
        ("TG-263-Reverse Order Name", "", "'TG-263-Reverse Order Name' is empty"),
        ("Target Type", "", "'Target Type' is empty"),
        ("Major Category", "", "'Major Category' is empty"),
        ("Major Category", 5.0, "'Major Category' is not text"),
        ("FMAID", 10.5, "'FMAID' is not a positive integer"),
        ("FMAID", 0.0, "'FMAID' is not a positive integer"),
        ("FMAID", "1001", "'FMAID' is not a positive integer"),
    ],
)
def test_invalid_values_fail(column, value, message):
    rows = (HEADER, ROWS[0], _with(ROWS[1], column, value))

    with pytest.raises(tg263.TG263Error, match=re.escape(f"row 3: {message}")):
        tg263.parse_sheet(rows)


@pytest.mark.parametrize("column", ["TG263-Primary Name", "TG-263-Reverse Order Name"])
def test_repeated_names_fail(column):
    repeated = _with(ROWS[1], column, ROWS[0][_column(column)])

    with pytest.raises(tg263.TG263Error, match=re.escape("appears 2 times")):
        tg263.parse_sheet((HEADER, ROWS[0], repeated))


def test_a_sheet_without_structures_fails():
    with pytest.raises(tg263.TG263Error, match="no structures"):
        tg263.parse_sheet((HEADER,))


def _sheet(name, rows):
    return types.SimpleNamespace(
        name=name,
        nrows=len(rows),
        row_values=lambda index: list(rows[index]),
    )


@pytest.mark.parametrize(
    "sheets, message",
    [
        ([_sheet("Notes", [("Readme",)])], "no sheet"),
        ([_sheet("A", [HEADER]), _sheet("B", [HEADER])], "2 sheets"),
    ],
)
def test_exactly_one_sheet_must_hold_the_nomenclature(sheets, message):
    book = types.SimpleNamespace(sheets=lambda: sheets)

    with pytest.raises(tg263.TG263Error, match=message):
        tg263._find_sheet(book)  # pylint: disable = protected-access


@pytest.mark.parametrize("ctype", ["XL_CELL_DATE", "XL_CELL_BOOLEAN", "XL_CELL_ERROR"])
def test_cells_other_than_text_numbers_or_blanks_fail(ctype):
    from pymedphys._imports import xlrd

    cell = types.SimpleNamespace(ctype=getattr(xlrd, ctype), value=1)

    with pytest.raises(tg263.TG263Error, match="row 4, column 2"):
        tg263._cell_value(cell, 3, 1)  # pylint: disable = protected-access


def test_a_file_that_is_not_a_workbook_fails(tmp_path):
    path = tmp_path / "tg263.xls"
    path.write_bytes(b"Not a workbook")

    with pytest.raises(tg263.TG263Error, match="not a readable .xls workbook"):
        tg263.read_spreadsheet(path)


def test_json_round_trip(tmp_path):
    nomenclature = tg263.read_spreadsheet(SPREADSHEET)
    path = tmp_path / "tg263.json"
    path.write_text(tg263.to_json(nomenclature), encoding="utf-8")

    assert tg263.load_json(path) == nomenclature


def test_json_is_deterministic_and_carries_its_provenance():
    nomenclature = tg263.read_spreadsheet(SPREADSHEET)
    text = tg263.to_json(nomenclature)
    document = json.loads(text)
    structures = [dataclasses.asdict(s) for s in STRUCTURES]

    assert text == tg263.to_json(nomenclature)
    assert text.endswith("}\n")
    assert document == {
        "format": tg263.FORMAT,
        "source": dataclasses.asdict(nomenclature.source),
        "attribution": tg263.ATTRIBUTION,
        "content_sha256": tg263.content_sha256(structures),
        "structures": structures,
    }


def _document():
    return json.loads(tg263.to_json(tg263.read_spreadsheet(SPREADSHEET)))


def _write(path, document, redigest=True):
    if redigest:
        document["content_sha256"] = tg263.content_sha256(document["structures"])
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.update(format="pymedphys-tg263/0"), "format"),
        (lambda d: d.pop("attribution"), "keys"),
        (lambda d: d.update(extra=1), "keys"),
        (lambda d: d["source"].update(sha256="abc"), "source"),
        (lambda d: d["source"].pop("sheet"), "source"),
        (lambda d: d["structures"][0].pop("fma_id"), "structure 1 has keys"),
        (
            lambda d: d["structures"][1].update(primary_name=""),
            "structure 2: 'primary_name' is empty",
        ),
        (
            lambda d: d["structures"][1].update(fma_id=1.0),
            "structure 2: 'fma_id' is not a positive integer",
        ),
        (
            lambda d: d["structures"][1].update(fma_id=True),
            "structure 2: 'fma_id' is not a positive integer",
        ),
        (
            lambda d: d["structures"][1].update(primary_name="Fixture_Lobe"),
            "appears 2 times",
        ),
        (lambda d: d.update(structures=[]), "no structures"),
    ],
)
def test_malformed_json_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(tg263.TG263Error, match=re.escape(message)):
        tg263.load_json(_write(tmp_path / "tg263.json", document))


def test_json_edited_without_its_digest_is_rejected(tmp_path):
    document = _document()
    document["structures"][0]["description"] = "Edited"

    with pytest.raises(tg263.TG263Error, match="content_sha256"):
        tg263.load_json(_write(tmp_path / "tg263.json", document, redigest=False))


def test_unreadable_json_is_rejected(tmp_path):
    path = tmp_path / "tg263.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(tg263.TG263Error, match="not valid JSON"):
        tg263.load_json(path)
