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

"""Residual text in a kept Code Meaning made only of the reviewed vocabulary.

Under the Basic Profile a scanner's local procedure code is kept with its
meaning, which often repeats the Study Description that the profile
removes. The residual search finds the description there (D-027); where
every word of the meaning is in the reviewed technique vocabulary (D-036),
the finding is not a reason for review (D-032).
"""

import dataclasses
import json
import re
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import residual_vocabulary, run
from pymedphys._dicom.deidentify.file_layout import ElementPath, Location, Region
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.release_report import exempted_findings
from pymedphys._dicom.deidentify.residual_exemptions import (
    Exemption,
    KeptValues,
    source_values,
)
from pymedphys._dicom.deidentify.residual_vocabulary import vocabulary_meaning
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT
from pymedphys._dicom.deidentify.standard import dictionary_attribute, load_table_e1_1
from pymedphys._dicom.deidentify.technique_descriptors import (
    Rejection,
    load_technique_vocabulary,
)

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
STUDY_DESCRIPTION = "(0008,1030)"
PROCEDURE_CODES = 0x00081032
CODE_MEANING = "(0008,0104)"
# Invented: every word is in the reviewed vocabulary.
MEANING = "CT HEAD WO CONTRAST"
# Invented: a word that no vocabulary holds.
LOCAL_TEXT = "CT HEAD ZARQUON"


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("latin-1") if isinstance(value, str) else value
    value += b" " * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _sequence(tag, *items):
    """A sequence of undefined length, with items of undefined length."""
    group, element = divmod(tag, 0x10000)
    header = struct.pack("<HH2sHI", group, element, b"SQ", 0, 0xFFFFFFFF)
    body = b"".join(
        struct.pack("<HHI", 0xFFFE, 0xE000, 0xFFFFFFFF)
        + b"".join(item)
        + struct.pack("<HHI", 0xFFFE, 0xE00D, 0)
        for item in items
    )
    return header + body + struct.pack("<HHI", 0xFFFE, 0xE0DD, 0)


def _written(*elements):
    """A written file holding ``elements``, given in the order of their tags."""
    meta = _element(0x00020010, "UI", "1.2.840.10008.1.2.1\x00")
    return bytes(128) + b"DICM" + meta + b"".join(elements)


def _code(designator, meaning, value="ZQ0001"):
    """The elements of a code item, in the order of their tags."""
    item = [_element(0x00080100, "SH", value)]
    if designator is not None:
        item.append(_element(0x00080102, "SH", designator))
    return [*item, _element(0x00080104, "LO", meaning)]


def _procedure(meaning, designator="99ZQ"):
    """A written file whose kept Procedure Code Sequence holds ``meaning``."""
    return _written(_sequence(PROCEDURE_CODES, _code(designator, meaning)))


def _condition(written, *removed):
    """The release condition of ``written`` for the removed values given."""
    values = [
        value if isinstance(value, SourceValue) else SourceValue(*value)
        for value in removed
    ]
    coverage = Coverage(
        planned=frozenset(value.source for value in values), collected=tuple(values)
    )
    return release_condition(coverage, written)


def _removed(tag, vr, value, items=()):
    return SourceValue(ElementPath(items, tag), vr, value)


def _exempted(condition):
    return [(f.location.element.tag, why) for f, why in condition.exempted]


# The word test, whatever the attribute.


def test_the_word_test_reads_a_value_as_the_technique_tier_does():
    vocabulary = load_technique_vocabulary()

    assert vocabulary.word_rejection(MEANING) is None
    assert vocabulary.word_rejection(LOCAL_TEXT) is Rejection.UNKNOWN_WORD
    assert vocabulary.word_rejection("CT HEAD 2026-10-12") is Rejection.DATE_OR_TIME
    assert vocabulary.word_rejection("") is Rejection.NO_VOCABULARY_WORD
    # The technique tier still keeps only its own attributes' values.
    assert vocabulary.rejection(CODE_MEANING, MEANING) is Rejection.NOT_AUTOMATIC
    assert vocabulary.rejection("(0008,103E)", MEANING) is None


# The release gate.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize("designator", ["99ZQ", "L", "sct", None])
def test_a_removed_description_in_a_vocabulary_meaning_is_released(designator):
    # Any scheme: a local one, one in the wrong case, or none.
    written = _procedure(MEANING, designator)
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", MEANING))

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(CODE_MEANING, Exemption.VOCABULARY_MEANING)]
    # The finding stays in the search, for the QC pack.
    assert len(condition.search.findings) == 1


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_part_of_a_vocabulary_meaning_is_released_too():
    # Contrast/Bolus Agent found inside a longer kept meaning.
    written = _procedure(MEANING)
    condition = _condition(written, _removed("(0018,0010)", "LO", "CONTRAST"))

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(CODE_MEANING, Exemption.VOCABULARY_MEANING)]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_standard_codes_meaning_keeps_its_own_exemption():
    written = _procedure(MEANING, "SCT")
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", MEANING))

    assert _exempted(condition) == [(CODE_MEANING, Exemption.STANDARD_CODE)]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "meaning",
    [
        LOCAL_TEXT,  # a word outside the vocabulary
        "CT HEAD 2026-10-12",  # a date
        "CT HEAD 12345678",  # a long number
        "CT HEAD WO CONTRAST J K",  # initials
        "CT HEAD^CONTRAST",  # a person name's separator
        "CT HEAD WO CONTRAST\\ZARQUON",  # one value of two outside it
    ],
)
def test_a_meaning_with_anything_else_goes_to_review(meaning):
    written = _procedure(meaning)
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", "CT HEAD"))

    assert condition.decision is Decision.QC_REVIEW
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_TEXT]
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_meaning_outside_iso_646_goes_to_review():
    written = _procedure("CT HEAD WO CONTRASTÉ".encode("latin-1"))
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", "CT HEAD"))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "identifier",
    [
        ("(0010,0020)", "LO", "HEAD-7731"),  # a word of the Patient ID
        ("(0010,1000)", "LO", "ZQ\\HEAD-7731"),  # of Other Patient IDs
        ("(0010,0021)", "LO", "CONTRAST HOSP"),  # of the Issuer of Patient ID
    ],
)
def test_a_meaning_that_echoes_a_patient_identifier_goes_to_review(identifier):
    # The search does not find the whole identifier in the meaning, but a
    # word of it is a word of the meaning.
    written = _procedure(MEANING)
    condition = _condition(
        written, _removed(STUDY_DESCRIPTION, "LO", MEANING), _removed(*identifier)
    )

    assert condition.decision is Decision.QC_REVIEW
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_TEXT]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_meaning_that_echoes_a_person_name_is_not_exempt():
    # The search finds the name's component and withholds the file; the
    # echo check also leaves the description's finding under review.
    written = _procedure(MEANING)
    description = _removed(STUDY_DESCRIPTION, "LO", MEANING)
    echoed = _condition(written, description, _removed("(0008,0090)", "PN", "ZQ^HEAD"))
    other = _condition(
        written, description, _removed("(0008,0090)", "PN", "HEADLEY^ZQ")
    )

    assert echoed.decision is Decision.WITHHOLD
    assert ReasonCode.RESIDUAL_TEXT in [reason.code for reason in echoed.reasons]
    assert not echoed.exempted
    # A name none of whose words is a word of the meaning echoes nothing.
    assert other.decision is Decision.RELEASE


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_person_name_found_in_a_vocabulary_meaning_still_withholds():
    written = _procedure(MEANING)
    condition = _condition(written, _removed("(0010,0010)", "PN", "CONTRAST^WO"))

    assert condition.decision is Decision.WITHHOLD
    assert ReasonCode.RESIDUAL_PERSON_NAME in [r.code for r in condition.reasons]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source",
    [
        _removed("(0008,0080)", "LO", "HEAD"),  # Institution Name
        _removed("(0008,0081)", "ST", "HEAD"),  # Institution Address
        _removed("(0008,1040)", "LO", "HEAD"),  # Institutional Department Name
        _removed("(0008,1010)", "SH", "HEAD"),  # Station Name
        # The meaning of an Institution Code Sequence item, and of an
        # Institutional Department Type Code Sequence item.
        _removed(CODE_MEANING, "LO", "HEAD", (("(0008,0082)", 0),)),
        _removed(CODE_MEANING, "LO", "HEAD", (("(0008,1041)", 0),)),
        _removed("(0040,0010)", "SH", "HEAD"),  # Scheduled Station Name
        _removed("(0040,0242)", "SH", "HEAD"),  # Performed Station Name
        _removed("(0008,0055)", "AE", "HEAD"),  # Station AE Title
        _removed("(0040,0243)", "SH", "HEAD"),  # Performed Location
        _removed("(0018,1000)", "LO", "HEAD"),  # Device Serial Number
        # The meanings of Scheduled and Performed Station Name Code
        # Sequence items, nested in a step's item.
        _removed(
            CODE_MEANING,
            "LO",
            "HEAD",
            (("(0040,0100)", 0), ("(0040,4025)", 0)),
        ),
        _removed(
            CODE_MEANING,
            "LO",
            "HEAD",
            (("(0040,0260)", 1), ("(0040,4028)", 0)),
        ),
    ],
)
def test_an_institutions_or_stations_name_goes_to_review(source):
    written = _procedure(MEANING)
    condition = _condition(written, source)

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


# The words of Table E.1-1's names of attributes that name, code, or
# address a place, an organisation, or a device.
_IDENTIFYING_NAMES = re.compile(
    r"Institution|Station|AE Title|Location|Organization|Coordinating Center"
    r"|Site ID|Site Name|Address|Telephone|Device (?:Serial|ID|Alternate|Label)"
    r"|Hardcopy Creation Device ID"
)


def test_every_attribute_of_table_e1_1_that_names_a_place_is_excluded():
    # A later edition that adds such an attribute fails here until it is
    # placed. A UID, such as Dimension Organization UID, withholds wherever
    # it is found.
    named = {
        row.tag
        for row in load_table_e1_1().attributes
        if _IDENTIFYING_NAMES.search(row.name)
        and dictionary_attribute(row.tag).vrs != ("UI",)
    }
    excluded = residual_vocabulary.INSTITUTIONAL_SOURCES | (
        residual_vocabulary.INSTITUTIONAL_SEQUENCES
    )

    assert named == excluded


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "written",
    [
        # Other kept text.
        _written(_element(0x00204000, "LT", MEANING)),
        # A Code Meaning outside any item.
        _written(_element(0x00080104, "LO", MEANING)),
        # The Code Value of a local code.
        _written(_sequence(PROCEDURE_CODES, _code("99ZQ", "ZQ", value=MEANING))),
    ],
)
def test_vocabulary_in_any_other_kept_element_goes_to_review(written):
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", MEANING))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


def _finding():
    """The finding of a removed Study Description in a kept local meaning."""
    written = _procedure(MEANING)
    source = _removed(STUDY_DESCRIPTION, "LO", MEANING)
    (finding,) = _condition(written, source).search.findings
    return finding, KeptValues(written), source_values((source,))


def test_only_a_finding_inside_the_data_set_is_read():
    finding, kept, sources = _finding()
    outside = dataclasses.replace(finding, location=Location(Region.PREAMBLE))

    assert finding.location.element == ElementPath((("(0008,1032)", 0),), CODE_MEANING)
    assert vocabulary_meaning(finding, kept, sources) is (Exemption.VOCABULARY_MEANING)
    assert vocabulary_meaning(outside, kept, sources) is None


def test_the_release_report_counts_vocabulary_meanings():
    finding, _, _ = _finding()

    counted = exempted_findings([[(finding, Exemption.VOCABULARY_MEANING)]])

    assert [(c.exemption, c.attribute, c.found_in, c.count) for c in counted] == [
        ("vocabulary-meaning", STUDY_DESCRIPTION, "(0008,1032) > (0008,0104)", 1)
    ]


# A run under the Basic Profile.


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _run(tmp_path, meaning, **attributes):
    """Run three CT slices of a study whose local procedure code means ``meaning``.

    Each slice also has ``attributes``, by keyword.
    """
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    source = tmp_path / "source"
    source.mkdir()
    for number in range(3):
        dataset = synthetic.ct_slice(number)
        dataset.StudyDescription = MEANING
        code = pydicom.Dataset()
        code.CodeValue = "ZQ0001"
        code.CodingSchemeDesignator = "99ZQ"
        code.CodeMeaning = meaning
        dataset.ProcedureCodeSequence = [code]
        for keyword, value in attributes.items():
            setattr(dataset, keyword, value)
        (source / f"{number}.dcm").write_bytes(synthetic.written(dataset))
    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )
    report = json.loads((result.release / RELEASE_REPORT).read_text(encoding="utf-8"))
    return [outcome.status for outcome in result.outcomes], report


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_basic_releases_slices_whose_local_procedure_code_repeats_the_description(
    tmp_path,
):
    statuses, report = _run(tmp_path, MEANING)

    assert statuses == [run.Status.RELEASED] * 3
    assert [
        (entry["exemption"], entry["attribute"], entry["found_in"], entry["count"])
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.VOCABULARY_MEANING.value
    ] == [("vocabulary-meaning", STUDY_DESCRIPTION, "(0008,1032) > (0008,0104)", 3)]
    released = sorted((tmp_path / "release").rglob("*.dcm"))
    for path in released:
        dataset = pydicom.dcmread(path)
        assert "StudyDescription" not in dataset
        assert dataset.ProcedureCodeSequence[0].CodeMeaning == MEANING


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_basic_still_holds_slices_whose_local_meaning_has_another_word(tmp_path):
    statuses, report = _run(tmp_path, f"{MEANING} ZARQUON")

    assert statuses == [run.Status.HELD_FOR_REVIEW] * 3
    assert not [
        entry
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.VOCABULARY_MEANING.value
    ]


def _station_code():
    """A local code naming a station, unlike the procedure's in all but meaning."""
    code = pydicom.Dataset()
    code.CodeValue = "ZS0002"
    code.CodingSchemeDesignator = "99ZS"
    code.CodeMeaning = "HEAD"
    return code


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "keyword, value",
    [
        ("ScheduledStationName", "HEAD"),
        ("PerformedStationName", "HEAD"),
        ("ScheduledStationNameCodeSequence", [_station_code()]),
        ("PerformedStationNameCodeSequence", [_station_code()]),
    ],
)
def test_basic_holds_slices_whose_local_meaning_repeats_a_station_name(
    tmp_path, keyword, value
):
    # Table E.1-1 removes each under the Basic Profile; the removed name is
    # found in the kept meaning, whose words are all vocabulary.
    statuses, report = _run(tmp_path, MEANING, **{keyword: value})

    assert statuses == [run.Status.HELD_FOR_REVIEW] * 3
    assert not [
        entry
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.VOCABULARY_MEANING.value
        and entry["attribute"] != STUDY_DESCRIPTION
    ]
