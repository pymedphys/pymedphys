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

"""The tables of DICOM PS3.6 Annex A generated from the standard, and their loaders."""

import collections
import json
import re

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import standard, uid_registry


def _loaded(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _redigested(document):
    """Record the digest of the rows as they now are, as a careful editor would."""
    document["content_sha256"] = standard.content_sha256(document["rows"])
    return document


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


# Each Annex A loader and the file it loads by default.
UID_LOADERS = {
    "Table A-1": uid_registry.load_uid_values,
    "Table A-2": uid_registry.load_frames_of_reference,
    "Table A-3": uid_registry.load_context_group_uids,
    "Table A-4": uid_registry.load_template_uids,
}


def test_the_uid_tables_have_every_row_of_the_2026d_tables():
    # Counts measured from the published 2026d Annex A.
    uids = uid_registry.load_uid_values()
    context_groups = uid_registry.load_context_group_uids()

    assert {label: len(load().rows) for label, load in UID_LOADERS.items()} == {
        "Table A-1": 468,
        "Table A-2": 28,
        "Table A-3": 1470,
        "Table A-4": 24,
    }
    assert collections.Counter(uid.uid_type for uid in uids.rows) == {
        "SOP Class": 314,
        "Transfer Syntax": 63,
        "LDAP OID": 39,
        "Well-known SOP Instance": 19,
        "Coding Scheme": 15,
        "Meta SOP Class": 9,
        "Service Class": 3,
        "Application Hosting Model": 2,
        "DICOM UIDs as a Coding Scheme": 1,
        "Application Context Name": 1,
        "Mapping Resource": 1,
        "Synchronization Frame of Reference": 1,
    }
    assert sum(uid.retired for uid in uids.rows) == 75
    assert sum(group.retired for group in context_groups.rows) == 18


@pytest.mark.parametrize("label", list(UID_LOADERS))
def test_the_uid_tables_carry_their_edition_and_acknowledgement(label):
    table = UID_LOADERS[label]()

    assert table.edition == "2026d"
    assert table.acknowledgement == "DICOM PS3.6 2026d, \u00a9 NEMA"


@pytest.mark.parametrize(
    "label, row",
    [
        (
            "Table A-1",
            uid_registry.RegisteredUID(
                uid="1.2.840.10008.1.2",
                name="Implicit VR Little Endian: Default Transfer Syntax for DICOM",
                keyword="ImplicitVRLittleEndian",
                uid_type="Transfer Syntax",
                part="PS3.5",
            ),
        ),
        (
            "Table A-1",
            uid_registry.RegisteredUID(
                uid="1.2.840.10008.1.2.2",
                name="Explicit VR Big Endian (Retired)",
                keyword="ExplicitVRBigEndian",
                uid_type="Transfer Syntax",
                part="PS3.5 (2011)",
            ),
        ),
        (
            "Table A-1",
            uid_registry.RegisteredUID(
                uid="1.2.840.10008.5.1.4.1.1.40",
                name="(Retired)",
                keyword="",
                uid_type="SOP Class",
                part="(2015c)",
            ),
        ),
        (
            "Table A-1",
            uid_registry.RegisteredUID(
                uid="1.2.840.10008.2.16.7",
                name="Integrated Taxonomic Information System (ITIS) Taxonomic "
                "Serial Number (TSN)",
                keyword="ITIS_TSN",
                uid_type="Coding Scheme",
                part="PS3.16",
            ),
        ),
        (
            "Table A-2",
            uid_registry.WellKnownFrameOfReference(
                uid="1.2.840.10008.1.4.1.1",
                name="Talairach Brain Atlas Frame of Reference",
                keyword="TalairachBrainAtlas",
                normative_reference="Talairach J. and Tournoux P. Co-Planar "
                "stereotactic atlas of the human brain. Stuttgart: Georg Thieme "
                "Verlag, 1988.",
            ),
        ),
        (
            "Table A-3",
            uid_registry.ContextGroupUID(
                uid="1.2.840.10008.6.1.1",
                identifier="CID 2",
                name="Anatomic Modifier",
                comment="",
            ),
        ),
        (
            "Table A-3",
            uid_registry.ContextGroupUID(
                uid="1.2.840.10008.6.1.837", identifier="", name="", comment=""
            ),
        ),
        (
            "Table A-4",
            uid_registry.TemplateUID(
                uid="1.2.840.10008.9.1",
                name="Imaging Report",
                uid_type="Document TemplateID",
                part="PS3.20",
            ),
        ),
    ],
)
def test_uid_table_rows(label, row):
    assert row in UID_LOADERS[label]().rows


def test_retirement_follows_the_name_and_part_or_the_comment():
    uids = {uid.uid: uid for uid in uid_registry.load_uid_values().rows}
    groups = {group.uid: group for group in uid_registry.load_context_group_uids().rows}

    assert uids["1.2.840.10008.1.2.2"].retired
    assert not uids["1.2.840.10008.1.2"].retired
    assert groups["1.2.840.10008.6.1.50"].retired  # RET (2011)
    assert not groups["1.2.840.10008.6.1.1"].retired


@pytest.mark.parametrize(
    "label, field, value, message",
    [
        ("Table A-1", "uid", "1.02", "row 1 has a UID"),
        ("Table A-1", "uid", None, "row 1 has a UID"),
        ("Table A-1", "name", "", "row 1 has a name"),
        ("Table A-1", "keyword", "Verification SOP", "row 1 has a keyword"),
        ("Table A-1", "uid_type", "SOP class", "row 1 has a UID type"),
        ("Table A-1", "uid_type", [], "row 1 has a UID type"),
        ("Table A-1", "uid_type", {}, "row 1 has a UID type"),
        ("Table A-1", "part", None, "row 1 has a part"),
        ("Table A-1", "part", "PS3.4 (2001)", "row 1 is marked retired"),
        ("Table A-1", "keyword", "", "row 1 has no keyword but is not retired"),
        ("Table A-2", "keyword", "", "row 1 has a keyword"),
        ("Table A-2", "normative_reference", 1, "row 1 has a normative reference"),
        ("Table A-3", "identifier", "2", "row 1 has an identifier"),
        ("Table A-3", "name", "", "row 1 has an identifier without a name"),
        ("Table A-3", "comment", "RET", "row 1 has a comment"),
        ("Table A-4", "uid_type", "SOP Class", "row 1 has a UID type"),
        ("Table A-4", "uid_type", [], "row 1 has a UID type"),
        ("Table A-4", "uid_type", {}, "row 1 has a UID type"),
    ],
)
def test_a_malformed_uid_table_row_is_rejected(tmp_path, label, field, value, message):
    spec = uid_registry.UID_TABLES[label]
    document = _loaded(standard.STANDARD_DIR / spec.file)
    document["rows"][0][field] = value

    with pytest.raises(standard.StandardTableError, match=re.escape(message)):
        UID_LOADERS[label](_write(tmp_path / spec.file, _redigested(document)))


@pytest.mark.parametrize(
    "label, field, message",
    [
        ("Table A-1", "uid", "repeats the uid"),
        ("Table A-1", "keyword", "repeats the keyword"),
        ("Table A-2", "keyword", "repeats the keyword"),
        ("Table A-3", "identifier", "repeats the identifier"),
        ("Table A-4", "uid", "repeats the uid"),
    ],
)
def test_a_repeated_uid_keyword_or_identifier_is_rejected(
    tmp_path, label, field, message
):
    spec = uid_registry.UID_TABLES[label]
    document = _loaded(standard.STANDARD_DIR / spec.file)
    rows = document["rows"]
    rows[1][field] = rows[0][field]

    with pytest.raises(standard.StandardTableError, match=f"row 2 {message}"):
        UID_LOADERS[label](_write(tmp_path / spec.file, _redigested(document)))


@pytest.mark.parametrize(
    "uid, valid",
    [
        ("1.2.840.10008.1.2", True),
        ("0.0", True),
        ("1.20.3", True),
        ("1.02", False),
        ("1..2", False),
        ("1.2.", False),
        ("", False),
        ("1." + "2" * 62, True),
        ("1." + "2" * 63, False),
    ],
)
def test_uids_follow_ps3_5_section_9_1(uid, valid):
    assert uid_registry.is_uid(uid) is valid


@pytest.mark.pydicom
def test_the_uid_tables_agree_with_pydicom():
    # pydicom bundles an earlier edition, so it has fewer UIDs, but every one
    # it has must be in Table A-1 or A-2 with the same keyword and type, and
    # be retired where the table says so.
    uids = {uid.uid: uid for uid in uid_registry.load_uid_values().rows}
    frames = {f.uid: f for f in uid_registry.load_frames_of_reference().rows}
    differences = []
    for uid, (_, uid_type, _, retired, keyword) in pydicom.uid.UID_dictionary.items():
        if uid in frames:
            ours = ("Well-known frame of reference", frames[uid].keyword, False)
        elif uid in uids:
            ours = (uids[uid].uid_type, uids[uid].keyword, uids[uid].retired)
        else:
            ours = None
        if ours != (uid_type, keyword, retired == "Retired"):
            differences.append((uid, ours, (uid_type, keyword, retired)))

    assert not differences
    assert len(pydicom.uid.UID_dictionary) > 400
