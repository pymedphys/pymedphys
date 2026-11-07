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

"""Residual text in a kept technique descriptor made only of the reviewed vocabulary.

Clean Descriptors keeps a technique descriptor, such as Series Description,
whose every word is in the reviewed technique vocabulary (D-036), and a
scanner often writes the same text as a description that the profile
removes, such as Study Description. The residual search finds the
description there (D-027); where every word of the kept descriptor is in the
shipped vocabulary, the finding is not a reason for review (D-032).
"""

import dataclasses
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
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
from pymedphys._dicom.deidentify.release_report_markdown import to_markdown
from pymedphys._dicom.deidentify.residual_exemptions import (
    Exemption,
    KeptValues,
    source_values,
)
from pymedphys._dicom.deidentify.residual_vocabulary import (
    descriptor_values,
    vocabulary_descriptor,
    vocabulary_meaning,
)
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    ReviewedDescriptor,
    ReviewedDescriptors,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review, ReviewedNames
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT
from pymedphys._dicom.deidentify.technique_descriptors import (
    load_technique_vocabulary,
)

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
STUDY_DESCRIPTION = "(0008,1030)"
SERIES_DESCRIPTION = "(0008,103E)"
PERFORMED_DESCRIPTION = "(0040,0254)"
DERIVATION_DESCRIPTION = "(0008,2111)"
CODE_MEANING = "(0008,0104)"
# Request Attributes Sequence, whose items can hold a kept descriptor.
REQUEST_ATTRIBUTES = 0x00400275
# Invented: every word is in the reviewed vocabulary.
DESCRIPTION = "CT HEAD WO CONTRAST"
# Invented: a word that no vocabulary holds.
LOCAL_TEXT = "CT HEAD ZARQUON"
# Two values, each of vocabulary words, whose single-letter words would be
# next to each other, as initials are, if the value were read whole.
TWO_VALUES = "BRAIN W\\W CONTRAST"

# The technique descriptors, their VRs, and their tags as integers.
DESCRIPTORS = {
    SERIES_DESCRIPTION: ("LO", 0x0008103E),
    DERIVATION_DESCRIPTION: ("ST", 0x00082111),
    "(0018,0010)": ("LO", 0x00180010),  # Contrast/Bolus Agent
    "(0018,0024)": ("SH", 0x00180024),  # Sequence Name
    "(0018,1030)": ("LO", 0x00181030),  # Protocol Name
    "(0018,1040)": ("LO", 0x00181040),  # Contrast/Bolus Route
    "(0028,1055)": ("LO", 0x00281055),  # Window Center & Width Explanation
    PERFORMED_DESCRIPTION: ("LO", 0x00400254),
    "(0054,1101)": ("LO", 0x00541101),  # Attenuation Correction Method
    "(0054,1103)": ("LO", 0x00541103),  # Reconstruction Method
    "(0054,1105)": ("LO", 0x00541105),  # Scatter Correction Method
}


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


def _descriptor(value, tag=SERIES_DESCRIPTION):
    """A written file whose kept technique descriptor ``tag`` holds ``value``."""
    vr, number = DESCRIPTORS[tag]
    return _written(_element(number, vr, value))


def _removed(tag, vr, value, items=()):
    return SourceValue(ElementPath(items, tag), vr, value)


def _condition(written, *removed):
    """The release condition of ``written`` for the removed values given."""
    coverage = Coverage(
        planned=frozenset(value.source for value in removed), collected=removed
    )
    return release_condition(coverage, written)


def _exempted(condition):
    return [(f.location.element.tag, why) for f, why in condition.exempted]


def test_the_descriptors_are_the_shipped_vocabularys_attributes():
    assert load_technique_vocabulary().attributes == frozenset(DESCRIPTORS)


# The release gate.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize("tag", sorted(DESCRIPTORS))
def test_a_removed_description_in_a_vocabulary_descriptor_is_released(tag):
    written = _descriptor(DESCRIPTION, tag)
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", DESCRIPTION))

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(tag, Exemption.VOCABULARY_DESCRIPTOR)]
    # The finding stays in the search, for the QC pack.
    assert len(condition.search.findings) == 1


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source",
    [
        _removed("(0032,1060)", "LO", DESCRIPTION),  # Requested Procedure Desc.
        _removed("(0040,0007)", "LO", DESCRIPTION),  # Scheduled Step Description
        _removed("(0040,1400)", "LT", DESCRIPTION),  # Requested Procedure Comments
        _removed("(0020,4000)", "LT", DESCRIPTION),  # Image Comments
        # The meaning of a request's local code.
        _removed(CODE_MEANING, "LO", DESCRIPTION, (("(0032,1064)", 0),)),
        # A vendor's private copy.
        _removed("(0019,109C)", "LO", DESCRIPTION),
        # Part of the kept descriptor.
        _removed("(0018,0010)", "LO", "CONTRAST"),
    ],
)
def test_other_removed_text_in_a_vocabulary_descriptor_is_released(source):
    written = _descriptor(DESCRIPTION, PERFORMED_DESCRIPTION)
    condition = _condition(written, source)

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [
        (PERFORMED_DESCRIPTION, Exemption.VOCABULARY_DESCRIPTOR)
    ]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_vocabulary_descriptor_in_an_item_is_released():
    written = _written(
        _sequence(REQUEST_ATTRIBUTES, [_element(0x00400254, "LO", DESCRIPTION)])
    )
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", DESCRIPTION))

    assert condition.decision is Decision.RELEASE
    ((finding, why),) = condition.exempted
    assert finding.location.element == ElementPath(
        (("(0040,0275)", 0),), PERFORMED_DESCRIPTION
    )
    assert why is Exemption.VOCABULARY_DESCRIPTOR


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "value",
    [
        LOCAL_TEXT,  # a word outside the vocabulary
        "CT HEAD 2026-10-12",  # a date
        "CT HEAD 12345678",  # a long number
        "CT HEAD WO CONTRAST J K",  # initials
        "CT HEAD^CONTRAST",  # a person name's separator
        "CT HEAD WO CONTRAST\\ZARQUON",  # one value of two outside it
    ],
)
def test_a_descriptor_with_anything_else_goes_to_review(value):
    written = _descriptor(value)
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", "CT HEAD"))

    assert condition.decision is Decision.QC_REVIEW
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_TEXT]
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_descriptor_outside_iso_646_goes_to_review():
    written = _descriptor("CT HEAD WO CONTRASTÉ".encode("latin-1"))
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", "CT HEAD"))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_values_are_read_as_descriptor_cleaning_reads_them():
    # Split at backslashes where the VR holds several values, and whole
    # where it does not, as Derivation Description's ST does.
    several = _descriptor(TWO_VALUES)
    whole = _descriptor(TWO_VALUES, DERIVATION_DESCRIPTION)
    source = _removed(STUDY_DESCRIPTION, "LO", "CONTRAST")

    assert descriptor_values(
        ElementPath((), SERIES_DESCRIPTION), KeptValues(several)
    ) == ("BRAIN W", "W CONTRAST")
    assert descriptor_values(
        ElementPath((), DERIVATION_DESCRIPTION), KeptValues(whole)
    ) == (TWO_VALUES,)
    assert _condition(several, source).decision is Decision.RELEASE
    assert _condition(whole, source).decision is Decision.QC_REVIEW


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "identifier",
    [
        ("(0010,0020)", "LO", "HEAD-7731"),  # a word of the Patient ID
        ("(0010,1000)", "LO", "ZQ\\HEAD-7731"),  # of Other Patient IDs
        ("(0010,0021)", "LO", "CONTRAST HOSP"),  # of the Issuer of Patient ID
    ],
)
def test_a_descriptor_that_echoes_a_patient_identifier_goes_to_review(identifier):
    written = _descriptor(DESCRIPTION)
    condition = _condition(
        written,
        _removed(STUDY_DESCRIPTION, "LO", DESCRIPTION),
        _removed(*identifier),
    )

    assert condition.decision is Decision.QC_REVIEW
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_TEXT]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_person_name_found_in_a_vocabulary_descriptor_still_withholds():
    written = _descriptor(DESCRIPTION)
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
        _removed("(0040,0010)", "SH", "HEAD"),  # Scheduled Station Name
        _removed("(0018,1000)", "LO", "HEAD"),  # Device Serial Number
        _removed(CODE_MEANING, "LO", "HEAD", (("(0008,0082)", 0),)),
        _removed(CODE_MEANING, "LO", "HEAD", (("(0008,1041)", 0),)),
    ],
)
def test_a_place_organisation_or_device_source_goes_to_review(source):
    written = _descriptor(DESCRIPTION)
    condition = _condition(written, source)

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "written",
    [
        # Kept text that the technique tier never keeps.
        _written(_element(0x00081030, "LO", DESCRIPTION)),  # Study Description
        _written(_element(0x00204000, "LT", DESCRIPTION)),  # Image Comments
        # Kept text with a technique descriptor's element number in a
        # private group.
        _written(_element(0x0009103E, "LO", DESCRIPTION)),
    ],
)
def test_vocabulary_in_any_other_kept_text_goes_to_review(written):
    condition = _condition(written, _removed(STUDY_DESCRIPTION, "LO", "CT HEAD"))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


def _finding():
    """The finding of a removed Study Description in a kept Series Description."""
    written = _descriptor(DESCRIPTION)
    source = _removed(STUDY_DESCRIPTION, "LO", DESCRIPTION)
    (finding,) = _condition(written, source).search.findings
    return finding, KeptValues(written), source_values((source,))


def test_only_a_finding_inside_the_data_set_is_read():
    finding, kept, sources = _finding()
    outside = dataclasses.replace(finding, location=Location(Region.PREAMBLE))

    assert finding.location.element == ElementPath((), SERIES_DESCRIPTION)
    assert vocabulary_descriptor(finding, kept, sources) is (
        Exemption.VOCABULARY_DESCRIPTOR
    )
    assert vocabulary_descriptor(outside, kept, sources) is None
    # Each rule reads only its own elements.
    assert vocabulary_meaning(finding, kept, sources) is None


def test_the_release_report_counts_vocabulary_descriptors():
    finding, _, _ = _finding()

    counted = exempted_findings([[(finding, Exemption.VOCABULARY_DESCRIPTOR)]])

    assert [(c.exemption, c.attribute, c.found_in, c.count) for c in counted] == [
        ("vocabulary-descriptor", STUDY_DESCRIPTION, SERIES_DESCRIPTION, 1)
    ]


# A run under Clean Descriptors.


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _run(tmp_path, preset, series=DESCRIPTION, kept=()):
    """Run three CT slices whose descriptors repeat their Study Description.

    A reviewer keeps each of the ``kept`` Series Descriptions.
    """
    reviewed = ReviewedDescriptors.empty()
    for value in kept:
        reviewed.record(SERIES_DESCRIPTION, value, ReviewedDescriptor(Review.KEEP))
    transform = InstanceTransform(
        compose_policy(preset),
        KEY,
        cleaning=DescriptorCleaning(
            None, ReviewedNames.empty(), reviewed_descriptors=reviewed
        ),
        unvalidated_policy=True,
    )
    source = tmp_path / "source"
    source.mkdir()
    for number in range(3):
        dataset = synthetic.ct_slice(number)
        dataset.StudyDescription = DESCRIPTION
        dataset.SeriesDescription = series
        dataset.PerformedProcedureStepDescription = DESCRIPTION
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
    report = (result.release / RELEASE_REPORT).read_text(encoding="utf-8")
    return [outcome.status for outcome in result.outcomes], report


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize("preset", ["basic-clean-descriptors", "tps-import"])
def test_clean_descriptors_releases_slices_whose_descriptors_repeat_the_study(
    tmp_path, preset
):
    statuses, text = _run(tmp_path, preset)
    report = json.loads(text)

    assert statuses == [run.Status.RELEASED] * 3
    assert sorted(
        (entry["exemption"], entry["attribute"], entry["found_in"], entry["count"])
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.VOCABULARY_DESCRIPTOR.value
    ) == [
        ("vocabulary-descriptor", STUDY_DESCRIPTION, SERIES_DESCRIPTION, 3),
        ("vocabulary-descriptor", STUDY_DESCRIPTION, PERFORMED_DESCRIPTION, 3),
    ]
    assert "`vocabulary-descriptor`" in to_markdown(text)
    for path in sorted((tmp_path / "release").rglob("*.dcm")):
        dataset = pydicom.dcmread(path)
        assert "StudyDescription" not in dataset
        assert dataset.SeriesDescription == DESCRIPTION
        assert dataset.PerformedProcedureStepDescription == DESCRIPTION


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_clean_descriptors_holds_a_reviewer_kept_descriptor_with_another_word(
    tmp_path,
):
    # The reviewer judged the value, not the removed text found in it.
    value = f"{DESCRIPTION} ZARQUON"
    statuses, _ = _run(tmp_path, "basic-clean-descriptors", value, kept=[value])

    assert statuses == [run.Status.HELD_FOR_REVIEW] * 3
