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

"""PS3.15 Table E.3.4-1 as generated from the pinned edition, and its loader."""

import collections
import json

from pymedphys._imports import pytest

from pymedphys._dev.deid_tables import generate
from pymedphys._dicom.deidentify import (
    codes,
    residual_exemptions,
    standard,
    structured_content,
)

E3_4_1 = standard.STANDARD_DIR / structured_content.FILE
E1_1 = standard.STANDARD_DIR / "e1_1.json"
VALUE_TYPE = "(0040,A040)"


def _loaded(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _redigested(document):
    document["content_sha256"] = standard.content_sha256(document["rows"])
    return document


def test_table_e3_4_1_has_the_kept_rows_of_the_2026d_table():
    # Counts measured from the published 2026d table, whose other 7 rows
    # are of the coding schemes the pin leaves out.
    table = structured_content.load_table_e3_4_1()

    assert table.edition == "2026d"
    assert table.acknowledgement == "DICOM PS3.15 2026d, © NEMA"
    assert len(table.concepts) == 207
    assert collections.Counter(c.scheme_designator for c in table.concepts) == {
        "DCM": 189,
        "SCT": 11,
        "LN": 7,
    }
    assert collections.Counter(c.basic_profile for c in table.concepts) == {
        "X": 131,
        "D": 58,
        "X/D": 18,
    }
    assert collections.Counter(
        option for c in table.concepts for option in c.options
    ) == {
        "retain_uids": 62,
        "retain_longitudinal_full_dates": 42,
        "retain_longitudinal_modified_dates": 42,
        "clean_descriptors": 43,
        "retain_device_identity": 14,
        "retain_institution_identity": 7,
        "retain_patient_characteristics": 2,
    }
    assert not any(c.retired for c in table.concepts)
    assert all(c.in_standard_template for c in table.concepts)
    assert not any(c.scheme_version for c in table.concepts)


def _concept(meaning, value, designator, value_type, basic, options=None):
    return structured_content.ContentItemConcept(
        code_meaning=meaning,
        code_value=value,
        scheme_designator=designator,
        scheme_version="",
        value_type=value_type,
        retired=False,
        in_standard_template=True,
        basic_profile=basic,
        options=options or {},
    )


@pytest.mark.parametrize(
    "concept",
    [
        _concept("Accession Number", "121022", "DCM", "TEXT", "X"),
        _concept("Person Observer Name", "121008", "DCM", "PNAME", "D"),
        _concept("Acquired Image", "113795", "DCM", "IMAGE", "D", {"retain_uids": "K"}),
        _concept(
            "Acquisition Date",
            "126201",
            "DCM",
            "DATE",
            "X",
            {
                "retain_longitudinal_full_dates": "K",
                "retain_longitudinal_modified_dates": "C",
            },
        ),
        _concept(
            "Acquisition Protocol",
            "125203",
            "DCM",
            "TEXT",
            "X",
            {"clean_descriptors": "C"},
        ),
        # One concept name with a row for each of two value types.
        _concept(
            "Clinical Report",
            "371524004",
            "SCT",
            "COMPOSITE",
            "X",
            {"retain_uids": "K"},
        ),
        _concept(
            "Clinical Report",
            "371524004",
            "SCT",
            "TEXT",
            "X",
            {"clean_descriptors": "C"},
        ),
        _concept(
            "Start DateTime",
            "398201009",
            "SCT",
            "DATETIME",
            "D",
            {
                "retain_longitudinal_full_dates": "K",
                "retain_longitudinal_modified_dates": "C",
            },
        ),
        # LOINC rows, with DICOM's Code Meanings.
        _concept(
            "EDD",
            "11778-8",
            "LN",
            "DATE",
            "X",
            {
                "retain_longitudinal_full_dates": "K",
                "retain_longitudinal_modified_dates": "C",
            },
        ),
        _concept("Fetus ID", "11951-1", "LN", "TEXT", "D"),
        _concept(
            "Unique Device Identifier",
            "74711-3",
            "LN",
            "TEXT",
            "X",
            {"retain_device_identity": "K"},
        ),
    ],
)
def test_table_e3_4_1_rows(concept):
    rows = {c.key: c for c in structured_content.load_table_e3_4_1().concepts}

    assert rows[concept.key] == concept


@pytest.mark.parametrize(
    "designator, value", [("NCDR", "15"), ("NCIt", "C54627"), ("UMLS", "C2348792")]
)
def test_rows_of_the_left_out_schemes_are_not_generated(designator, value):
    # Admission DateTime, Experience, and Time Point in the published table.
    concepts = structured_content.load_table_e3_4_1().concepts

    assert not [
        c
        for c in concepts
        if (c.scheme_designator, c.code_value) == (designator, value)
    ]


def test_every_scheme_of_the_pin_is_a_coding_scheme_of_ps3_16():
    designators = {row.designator for row in codes.load_coding_schemes().rows}

    assert set(generate.PIN.structured_content_schemes) <= designators
    assert set(generate.PIN.left_out_structured_content_schemes) <= designators


def test_the_value_types_are_those_of_ps3_3():
    # The Enumerated Values of Value Type (0040,A040) across PS3.3 also hold
    # NUMERIC, which the Content Item Macro (Table 10-2) gives where Section
    # C.17.3, and Table E.3.4-1, give NUM.
    terms = residual_exemptions.defined_terms()[VALUE_TYPE]

    assert terms - structured_content.VALUE_TYPES == {"NUMERIC"}
    assert structured_content.VALUE_TYPES <= terms


def test_the_options_are_those_of_table_e1_1_in_its_order():
    options = structured_content.STRUCTURED_CONTENT_OPTIONS

    assert [o for o in standard.OPTIONS if o in options] == list(options)
    assert set(standard.OPTIONS) - set(options) == {
        "retain_safe_private",
        "clean_structured_content",
        "clean_graphics",
    }


def test_the_table_is_hashable_and_its_options_read_only():
    table = structured_content.load_table_e3_4_1()
    hash(table)

    with pytest.raises(TypeError):
        table.concepts[0].options["retain_uids"] = "K"  # type: ignore[index]


@pytest.mark.parametrize(
    "designator, expected",
    [
        ("DCM", ("DCM", "")),
        ("NCDR [2.0b]", ("NCDR", "2.0b")),
        ("99SDM", ("99SDM", "")),
        ("NCDR [2.0b", None),
        ("NCDR []", None),
        ("NCDR  [2.0b]", None),
        ("NCDR [ 2.0b]", None),
        ("", None),
        ("D" * 17, None),
    ],
)
def test_split_designator(designator, expected):
    assert structured_content.split_designator(designator) == expected


def test_the_loader_rejects_another_table(tmp_path):
    with pytest.raises(standard.StandardTableError, match="is not a"):
        structured_content.load_table_e3_4_1(
            _write(tmp_path / E3_4_1.name, _loaded(E1_1))
        )


def test_a_table_altered_since_generation_is_rejected(tmp_path):
    document = _loaded(E3_4_1)
    document["rows"][0]["basic_profile"] = "K"

    with pytest.raises(standard.StandardTableError, match="recorded digest"):
        structured_content.load_table_e3_4_1(_write(tmp_path / E3_4_1.name, document))


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("code_meaning", "", "code meaning"),
        ("code_meaning", "M" * 65, "code meaning"),
        ("code_meaning", "Name ", "code meaning"),
        ("code_meaning", "A\\B", "code meaning"),
        ("code_value", "", "code value"),
        ("code_value", "1" * 17, "code value"),
        ("code_value", 121022, "code value"),
        ("scheme_designator", "NCDR [2.0b]", "coding scheme designator"),
        ("scheme_designator", "", "coding scheme designator"),
        ("scheme_version", None, "coding scheme version"),
        ("scheme_version", " 2.0b", "coding scheme version"),
        ("value_type", "NUMERIC", "value type"),
        ("value_type", ["TEXT"], "value type"),
        ("retired", "N", "retired or in_standard_template"),
        ("in_standard_template", 1, "retired or in_standard_template"),
        ("basic_profile", "U*", "Basic Profile action"),
        ("basic_profile", None, "Basic Profile action"),
        ("options", {"clean_structured_content": "C"}, "unknown option"),
        ("options", {"retain_uids": "k"}, "unknown option"),
        ("options", [], "unknown option"),
    ],
)
def test_a_malformed_row_is_rejected(tmp_path, field, value, message):
    document = _loaded(E3_4_1)
    document["rows"][0][field] = value

    with pytest.raises(standard.StandardTableError, match=f"row 1 has a.* {message}"):
        structured_content.load_table_e3_4_1(
            _write(tmp_path / E3_4_1.name, _redigested(document))
        )


def test_a_row_with_other_fields_is_rejected(tmp_path):
    document = _loaded(E3_4_1)
    document["rows"][0]["note"] = "extra"

    with pytest.raises(standard.StandardTableError, match="row 1 does not have"):
        structured_content.load_table_e3_4_1(
            _write(tmp_path / E3_4_1.name, _redigested(document))
        )


def test_a_repeated_code_and_value_type_is_rejected(tmp_path):
    document = _loaded(E3_4_1)
    document["rows"].append(dict(document["rows"][0], code_meaning="Other"))

    with pytest.raises(standard.StandardTableError, match="row 208 repeats"):
        structured_content.load_table_e3_4_1(
            _write(tmp_path / E3_4_1.name, _redigested(document))
        )
