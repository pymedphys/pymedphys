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

"""Residual person names found in standard text that a selected option keeps.

A removed person name withholds the file wherever the residual search finds
it (D-027). Under an option that keeps a standard text attribute, such as
Institution Name (0008,0080) under Retain Institution Identity or Ethnic
Group (0010,2160) under Retain Patient Characteristics, a word of a person's
name can also be a word of the kept value, as in an institution named after
a person, or a surname that is also an ethnic group. Such a finding goes to
QC review instead, where a reviewer who sees the value tells an
institution's or group's own name from a person's name typed into it, and it
is never explained without review (D-042). A name found anywhere else, and
every other kind of finding, still withholds. The names, institutions, and
groups here are invented.
"""

import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.option_kept import kept_text
from pymedphys._dicom.deidentify.policy import (
    DEVICE_IDENTITY,
    INSTITUTION_IDENTITY,
    PATIENT_CHARACTERISTICS,
    SAFE_PRIVATE,
    compose_custom_policy,
)
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    Uncollected,
    release_condition,
)
from pymedphys._dicom.deidentify.release_report import FORMAT
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
PHYSICIAN = "QUILLONBY^ZAPHOD"
INSTITUTION = "QUILLONBY MEMORIAL HOSPITAL"
PATIENT = "VELTRANE^ORLA"
GROUP = "VELTRANE"
INSTITUTION_NAME = "(0008,0080)"
INSTITUTION_ADDRESS = "(0008,0081)"
ETHNIC_GROUP = "(0010,2160)"
# Performing Physician's Name, Referring Physician's Name, and Operators'
# Name, which MIDI-B's PET images hold in their kept Institution Name.
PHYSICIANS = ("(0008,1050)", "(0008,0090)", "(0008,1070)")
PATIENTS_NAME = ElementPath((), "(0010,0010)")
# Person Name (0040,A123) in an item of Content Sequence (0040,A730).
PERSON_NAME = ElementPath((("(0040,A730)", 0),), "(0040,A123)")
KEPT_TEXT_NAME = ReasonCode.RESIDUAL_PERSON_NAME_IN_KEPT_TEXT


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("ascii")
    value += (b"\x00" if vr == "UI" else b" ") * (len(value) % 2)
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


def _written(*elements, meta=b""):
    """A written file holding ``elements``, given in the order of their tags.

    ``meta`` follows Transfer Syntax UID (0002,0010) in the File Meta
    Information.
    """
    syntax = _element(0x00020010, "UI", "1.2.840.10008.1.2.1")
    return bytes(128) + b"DICM" + syntax + meta + b"".join(elements)


KEPT_INSTITUTION = _written(_element(0x00080080, "LO", INSTITUTION))
KEPT_GROUP = _written(_element(0x00102160, "SH", GROUP))


def _top(tag):
    return ElementPath((), tag)


def _coverage(*values, options=(INSTITUTION_IDENTITY,), uncollected=()):
    """The coverage of one written instance that collected ``values``."""
    return Coverage(
        planned=frozenset(value.source for value in values)
        | {gap.path for gap in uncollected},
        collected=tuple(values),
        uncollected=tuple(uncollected),
        options=options,
    )


def _physician(tag="(0008,1050)", name=PHYSICIAN):
    return SourceValue(_top(tag), "PN", name)


def _reasons(condition):
    return [
        (reason.decision, reason.code, reason.path, reason.location.element)
        for reason in condition.reasons
    ]


# Which attributes an option keeps as text.


def test_only_standard_text_that_a_selected_option_keeps_is_kept_text():
    assert kept_text(INSTITUTION_NAME, (INSTITUTION_IDENTITY,))
    assert kept_text(INSTITUTION_ADDRESS, (INSTITUTION_IDENTITY,))
    assert kept_text(ETHNIC_GROUP, (PATIENT_CHARACTERISTICS,))
    assert kept_text("(0008,1010)", (DEVICE_IDENTITY,))  # Station Name
    # No option, or another option, keeps it.
    assert not kept_text(INSTITUTION_NAME, ())
    assert not kept_text(ETHNIC_GROUP, (INSTITUTION_IDENTITY,))
    # The Basic Profile keeps Beam Name.
    assert not kept_text("(300A,00C2)", (INSTITUTION_IDENTITY,))
    # The dictionary gives a private tag no VR.
    assert not kept_text("(0009,1001)", (SAFE_PRIVATE,))
    # Patient's Sex is kept text, but Patient's Age is AS, not text.
    assert kept_text("(0010,0040)", (PATIENT_CHARACTERISTICS,))
    assert not kept_text("(0010,1010)", (PATIENT_CHARACTERISTICS,))


# A person name found in kept text goes to review.


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.11-01")
@pytest.mark.parametrize("tag", PHYSICIANS)
def test_a_physicians_name_in_a_kept_institution_name_goes_to_review(tag):
    condition = release_condition(_coverage(_physician(tag)), KEPT_INSTITUTION)

    assert condition.decision is Decision.QC_REVIEW
    assert _reasons(condition) == [
        (Decision.QC_REVIEW, KEPT_TEXT_NAME, _top(tag), _top(INSTITUTION_NAME))
    ]
    # Nothing explains it, and the search keeps it for the QC pack.
    assert not condition.exempted
    assert len(condition.search.findings) == 1


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.11-01")
def test_a_name_in_a_kept_institution_name_in_an_item_goes_to_review():
    # Institution Name in Contributing Equipment Sequence (0018,A001).
    kept = ElementPath((("(0018,A001)", 0),), INSTITUTION_NAME)
    written = _written(_sequence(0x0018A001, [_element(0x00080080, "LO", INSTITUTION)]))

    condition = release_condition(_coverage(_physician()), written)

    assert condition.decision is Decision.QC_REVIEW
    assert _reasons(condition) == [
        (Decision.QC_REVIEW, KEPT_TEXT_NAME, _top("(0008,1050)"), kept)
    ]


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.7-01")
@pytest.mark.parametrize("source", [PATIENTS_NAME, PERSON_NAME], ids=str)
def test_a_patients_name_equal_to_a_kept_ethnic_group_goes_to_review(source):
    coverage = _coverage(
        SourceValue(source, "PN", PATIENT), options=(PATIENT_CHARACTERISTICS,)
    )

    condition = release_condition(coverage, KEPT_GROUP)

    assert condition.decision is Decision.QC_REVIEW
    assert _reasons(condition) == [
        (Decision.QC_REVIEW, KEPT_TEXT_NAME, source, _top(ETHNIC_GROUP))
    ]
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_name_from_a_private_source_in_kept_text_goes_to_review():
    # A private element collected as PN, to which the dictionary gives no VR.
    private = SourceValue(_top("(0009,1030)"), "PN", PHYSICIAN)

    condition = release_condition(_coverage(private), KEPT_INSTITUTION)

    assert condition.decision is Decision.QC_REVIEW
    assert [reason.code for reason in condition.reasons] == [KEPT_TEXT_NAME]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_name_in_kept_text_with_options_pooled_across_the_subject_goes_to_review():
    # Each instance records the run's options, so a merge keeps them.
    coverage = Coverage.merge(_coverage(_physician()), _coverage(_physician()))

    condition = release_condition(coverage, KEPT_INSTITUTION)

    assert condition.decision is Decision.QC_REVIEW


# A person name found anywhere else still withholds.


def _withholds_for_the_name(condition):
    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted
    assert ReasonCode.RESIDUAL_PERSON_NAME in [r.code for r in condition.reasons]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "options",
    [(), (DEVICE_IDENTITY,), (PATIENT_CHARACTERISTICS,), (SAFE_PRIVATE,)],
    ids=["no-option", "device-identity", "patient-characteristics", "safe-private"],
)
def test_a_name_in_an_institution_name_that_no_option_keeps_still_withholds(
    options,
):
    condition = release_condition(
        _coverage(_physician(), options=options), KEPT_INSTITUTION
    )

    _withholds_for_the_name(condition)
    assert [r.code for r in condition.reasons] == [ReasonCode.RESIDUAL_PERSON_NAME]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "written",
    [
        # Beam Name in Beam Sequence, which the Basic Profile keeps (the
        # decision of 6 October 2026).
        _written(_sequence(0x300A00B0, [_element(0x300A00C2, "LO", INSTITUTION)])),
        # A private data element that Retain Safe Private keeps.
        _written(
            _element(0x00090010, "LO", "ZARQUON_PRIVATE"),
            _element(0x00091001, "LO", INSTITUTION),
        ),
        # Station Name, which only Retain Device Identity keeps.
        _written(_element(0x00081010, "SH", "QUILLONBY CT")),
    ],
    ids=["beam-name", "private", "station-name"],
)
def test_a_name_in_a_value_that_the_selected_option_does_not_keep_as_text_withholds(
    written,
):
    coverage = _coverage(_physician(), options=(INSTITUTION_IDENTITY, SAFE_PRIVATE))

    condition = release_condition(coverage, written)

    _withholds_for_the_name(condition)


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_name_also_found_outside_the_data_set_withholds():
    written = _written(
        _element(0x00080080, "LO", INSTITUTION),
        meta=_element(0x00020016, "AE", "QUILLONBY"),  # Source AE Title
    )

    condition = release_condition(_coverage(_physician()), written)

    _withholds_for_the_name(condition)
    assert {reason.code for reason in condition.reasons} == {
        KEPT_TEXT_NAME,
        ReasonCode.RESIDUAL_PERSON_NAME,
    }


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_name_also_found_in_text_that_no_option_keeps_withholds():
    written = _written(
        _element(0x00080080, "LO", INSTITUTION),
        _element(0x00081030, "LO", "QUILLONBY REVIEW"),  # Study Description
    )

    condition = release_condition(_coverage(_physician()), written)

    _withholds_for_the_name(condition)
    assert [(r.decision, r.code) for r in condition.reasons] == [
        (Decision.QC_REVIEW, KEPT_TEXT_NAME),
        (Decision.WITHHOLD, ReasonCode.RESIDUAL_PERSON_NAME),
    ]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_name_in_kept_text_with_a_person_name_not_collected_withholds():
    gap = Uncollected(_top("(0008,1060)"), "could not be decoded as VR PN")

    condition = release_condition(
        _coverage(_physician(), uncollected=(gap,)), KEPT_INSTITUTION
    )

    assert condition.decision is Decision.WITHHOLD
    assert [(r.decision, r.code) for r in condition.reasons] == [
        (Decision.WITHHOLD, ReasonCode.UNCOLLECTED),
        (Decision.QC_REVIEW, KEPT_TEXT_NAME),
    ]


# Other kinds of finding in kept text still withhold.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    ("value", "kept", "code"),
    [
        (
            SourceValue(_top("(0010,0020)"), "LO", "QUILLONBY7"),  # Patient ID
            "QUILLONBY7 HOSPITAL",
            ReasonCode.RESIDUAL_DIRECT_IDENTIFIER,
        ),
        (
            SourceValue(_top("(0020,000D)"), "UI", "2.25.4242"),
            "SITE 2.25.4242",
            ReasonCode.RESIDUAL_UID,
        ),
        (
            SourceValue(_top("(0010,0030)"), "DA", "19700412"),
            "BUILT 19700412",
            ReasonCode.RESIDUAL_DATE,
        ),
    ],
    ids=["patient-id", "uid", "date"],
)
def test_an_identifier_uid_or_date_in_kept_text_still_withholds(value, kept, code):
    written = _written(_element(0x00080080, "LO", kept))

    condition = release_condition(_coverage(value), written)

    assert condition.decision is Decision.WITHHOLD
    assert [(r.decision, r.code) for r in condition.reasons] == [
        (Decision.WITHHOLD, code)
    ]
    assert not condition.exempted


# Runs of a CT slice whose kept Institution Name holds a physician's name.


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _run(tmp_path, options):
    """Run a CT slice whose Institution Name is named after its physician."""
    source = tmp_path / "source"
    source.mkdir()
    dataset = synthetic.ct_slice(0)
    dataset.InstitutionName = INSTITUTION
    dataset.PerformingPhysicianName = PHYSICIAN
    (source / "0.dcm").write_bytes(synthetic.written(dataset))
    transform = InstanceTransform(
        compose_custom_policy(options), KEY, unvalidated_policy=True
    )
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


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.11-01")
def test_under_retain_institution_identity_the_slice_is_held_for_review(tmp_path):
    statuses, report = _run(tmp_path, (INSTITUTION_IDENTITY,))

    assert statuses == [run.Status.HELD_FOR_REVIEW]
    assert report["format"] == FORMAT == "pymedphys-deid-release-report/68"
    assert [
        (entry["stage"], entry["code"], entry["count"])
        for entry in report["held_for_review"]
    ] == [("release", KEPT_TEXT_NAME.value, 1)]
    assert not list((tmp_path / "release").rglob("*.dcm"))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_under_the_basic_profile_the_same_slice_is_released(tmp_path):
    # The Basic Profile removes both values, so nothing is found.
    statuses, _ = _run(tmp_path, ())

    assert statuses == [run.Status.RELEASED]
