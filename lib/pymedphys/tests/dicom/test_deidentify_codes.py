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

"""The DICOM PS3.16 code tables generated from the standard, and their loaders."""

import json
import re

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import codes, standard, uid_registry


def _loaded(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _redigested(document):
    """Record the digest of the rows as they now are, as a careful editor would."""
    document["content_sha256"] = standard.content_sha256(document["rows"])
    return document


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


# Each PS3.16 loader, called with the path of the file it loads.
CODE_LOADERS = {
    "Table 8-1": codes.load_coding_schemes,
    "Table 8-2": codes.load_hl7v3_coding_schemes,
    "Table CID 7050": lambda path=None: codes.load_context_group(7050, path),
    "Table CID 7005": lambda path=None: codes.load_context_group(7005, path),
}


def test_the_code_tables_have_every_row_of_the_2026d_tables():
    # Counts measured from the published 2026d PS3.16.
    schemes = codes.load_coding_schemes().rows

    assert {label: len(load().rows) for label, load in CODE_LOADERS.items()} == {
        "Table 8-1": 66,
        "Table 8-2": 8,
        "Table CID 7050": 13,
        "Table CID 7005": 11,
    }
    assert sum(not scheme.uid for scheme in schemes) == 10
    assert sum(not scheme.name for scheme in schemes) == 10


@pytest.mark.parametrize("label", list(CODE_LOADERS))
def test_the_code_tables_carry_their_edition_and_acknowledgement(label):
    table = CODE_LOADERS[label]()

    assert table.edition == "2026d"
    assert table.acknowledgement == "DICOM PS3.16 2026d, © NEMA"


@pytest.mark.parametrize(
    "label, row",
    [
        (
            "Table 8-1",
            codes.CodingScheme(
                designator="DCM",
                uid="1.2.840.10008.2.16.4",
                name="DICOM Controlled Terminology",
                responsible_organization="DICOM",
                resources="DOC: http://dicom.nema.org/medical/dicom/current/output/"
                "chtml/part16/chapter_D.html OWL: ftp://medical.nema.org/MEDICAL/"
                "Dicom/Resources/Ontology/DCM/dcm.owl.zip FHIR: "
                "http://dicom.nema.org/resources/ontology/DCM",
                description="PS3.16 Content Mapping Resource, Annex D (Note that HL7 "
                "also specifies an OID of 2.16.840.1.113883.6.31, but deprecates it "
                "in favor of 1.2.840.10008.2.16.4).",
            ),
        ),
        (
            "Table 8-1",
            codes.CodingScheme(
                designator="BARI",
                uid="",
                name="BARI",
                responsible_organization="",
                resources="",
                # Citations follow the text without a space, as published.
                description="Bypass Angioplasty Revascularization Investigation"
                "[Alderman 1992]; endorsed by ACC/AHA Guidelines for Coronary "
                "Angiography[Scanlon 1999].",
            ),
        ),
        (
            "Table 8-2",
            codes.HL7v3CodingScheme(
                designator="mediaType",
                uid="2.16.840.1.113883.5.79",
                description="RFC2046",
            ),
        ),
        (
            "Table CID 7050",
            codes.CodedConcept(
                scheme_designator="DCM",
                code_value="113100",
                code_meaning="Basic Application Confidentiality Profile",
            ),
        ),
        (
            "Table CID 7050",
            codes.CodedConcept(
                scheme_designator="DCM",
                code_value="113112",
                code_meaning="Retain Institution Identity Option",
            ),
        ),
        (
            "Table CID 7005",
            codes.CodedConcept(
                scheme_designator="DCM",
                code_value="109104",
                code_meaning="De-identifying Equipment",
            ),
        ),
        (
            "Table CID 7005",
            codes.CodedConcept(
                scheme_designator="DCM",
                code_value="FILMD",
                code_meaning="Film Digitizer",
            ),
        ),
    ],
)
def test_code_table_rows(label, row):
    assert row in CODE_LOADERS[label]().rows


def test_designators_can_share_a_coding_scheme_uid():
    # SRT is the retired designator for SNOMED CT, which is now SCT.
    schemes = {scheme.designator: scheme for scheme in codes.load_coding_schemes().rows}

    assert schemes["SCT"].uid == schemes["SRT"].uid == "2.16.840.1.113883.6.96"


def test_every_coding_scheme_uid_that_ps3_6_registers_is_in_table_8_1():
    registered = {
        uid.uid
        for uid in uid_registry.load_uid_values().rows
        if uid.uid_type in ("Coding Scheme", "DICOM UIDs as a Coding Scheme")
    }
    schemes = {scheme.uid for scheme in codes.load_coding_schemes().rows}

    assert len(registered) == 16
    assert registered <= schemes


def test_only_the_generated_context_groups_can_be_loaded():
    with pytest.raises(ValueError, match="7050 and 7005"):
        codes.load_context_group(7051)


@pytest.mark.parametrize(
    "label, field, value, message",
    [
        ("Table 8-1", "designator", "", "row 1 has a designator"),
        ("Table 8-1", "designator", "A" * 17, "row 1 has a designator"),
        ("Table 8-1", "uid", "1.02", "row 1 has a UID"),
        ("Table 8-1", "name", None, "row 1 has a name"),
        ("Table 8-1", "resources", 1, "row 1 has resources"),
        ("Table 8-2", "uid", "", "row 1 has a UID"),
        ("Table 8-2", "description", None, "row 1 has a description"),
        ("Table CID 7050", "scheme_designator", "", "row 1 has a coding scheme"),
        ("Table CID 7050", "code_value", "", "row 1 has a code value"),
        ("Table CID 7005", "code_meaning", "M" * 65, "row 1 has a code meaning"),
        # SH and LO exclude the backslash, which separates values, and control
        # characters other than ESC (PS3.5 Table 6.2-1).
        ("Table CID 7050", "code_value", "113100\\113101", "row 1 has a code value"),
        ("Table CID 7050", "code_value", "113\x00100", "row 1 has a code value"),
        ("Table CID 7050", "code_meaning", "First\\Second", "row 1 has a code meaning"),
        ("Table CID 7005", "code_meaning", "First\nSecond", "row 1 has a code meaning"),
        (
            "Table CID 7005",
            "code_meaning",
            "First\x7fSecond",
            "row 1 has a code meaning",
        ),
    ],
)
def test_a_malformed_code_table_row_is_rejected(tmp_path, label, field, value, message):
    spec = codes.CODE_TABLES[label]
    document = _loaded(standard.STANDARD_DIR / spec.file)
    document["rows"][0][field] = value

    with pytest.raises(standard.StandardTableError, match=re.escape(message)):
        CODE_LOADERS[label](_write(tmp_path / spec.file, _redigested(document)))


@pytest.mark.parametrize(
    "label, fields, message",
    [
        ("Table 8-1", ("designator",), "repeats the designator"),
        ("Table 8-2", ("designator",), "repeats the designator"),
        ("Table 8-2", ("uid",), "repeats the uid"),
        (
            "Table CID 7050",
            ("code_value",),
            "repeats the scheme designator and code value 'DCM 113100'",
        ),
    ],
)
def test_a_repeated_designator_uid_or_code_is_rejected(
    tmp_path, label, fields, message
):
    spec = codes.CODE_TABLES[label]
    document = _loaded(standard.STANDARD_DIR / spec.file)
    rows = document["rows"]
    for field in fields:
        rows[1][field] = rows[0][field]

    with pytest.raises(standard.StandardTableError, match=f"row 2 {message}"):
        CODE_LOADERS[label](_write(tmp_path / spec.file, _redigested(document)))


def test_a_code_meaning_can_contain_the_esc_that_switches_character_sets(tmp_path):
    spec = codes.CODE_TABLES["Table CID 7005"]
    document = _loaded(standard.STANDARD_DIR / spec.file)
    meaning = "\x1b$BFixture\x1b(B"
    document["rows"][0]["code_meaning"] = meaning

    table = codes.load_context_group(
        7005, _write(tmp_path / spec.file, _redigested(document))
    )

    assert table.rows[0].code_meaning == meaning


def test_a_code_value_can_repeat_in_another_coding_scheme(tmp_path):
    spec = codes.CODE_TABLES["Table CID 7050"]
    document = _loaded(standard.STANDARD_DIR / spec.file)
    rows = document["rows"]
    rows[1].update(scheme_designator="SCT", code_value=rows[0]["code_value"])

    table = codes.load_context_group(
        7050, _write(tmp_path / spec.file, _redigested(document))
    )

    assert table.rows[1].code_value == table.rows[0].code_value


@pytest.mark.pydicom
@pytest.mark.parametrize("cid", [7050, 7005])
def test_the_context_groups_agree_with_pydicom(cid):
    # pydicom bundles an earlier edition, but these context groups have not
    # changed since.
    from pydicom.sr import _cid_dict, _concepts_dict

    expected = {
        (scheme, code, meaning)
        for scheme, keywords in _cid_dict.cid_concepts[cid].items()
        for keyword in keywords
        for code, (meaning, _) in _concepts_dict.concepts[scheme][keyword].items()
    }
    ours = {
        (row.scheme_designator, row.code_value, row.code_meaning)
        for row in codes.load_context_group(cid).rows
    }

    assert ours == expected
