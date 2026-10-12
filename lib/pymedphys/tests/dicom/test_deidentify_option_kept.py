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

"""Residual findings that a value a selected option keeps explains (D-042).

Every file is synthetic, and every value invented.
"""

import io
import struct

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import ae_titles, run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.option_kept import kept_by
from pymedphys._dicom.deidentify.policy import (
    DEVICE_IDENTITY,
    FULL_DATES,
    MODIFIED_DATES,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import Exemption
from pymedphys._dicom.deidentify.residuals import SourceValue

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
INSTITUTION_IDENTITY = "retain_institution_identity"
# A station whose name holds its institution's, as station names often do.
INSTITUTION = "ZARQUONHOSP"
STATION = f"{INSTITUTION}_CT1"
STATION_NAME = 0x00081010
DEVICE_SERIAL_NUMBER = 0x00181000
TREATMENT_MACHINE_NAME = 0x300A00B2
STUDY_DATE = 0x00080020
BIRTH_DATE = "(0010,0030)"
DAY = "20200102"


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("latin-1") if isinstance(value, str) else value
    value += b" " * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _written(*elements):
    """A written file holding ``elements``, given in the order of their tags."""
    meta = _element(0x00020010, "UI", "1.2.840.10008.1.2.1\x00")
    return bytes(128) + b"DICM" + meta + b"".join(elements)


def _condition(written, options, *removed):
    """The release condition of ``written`` for the removed values given."""
    values = [
        SourceValue(ElementPath((), tag), vr, value) for tag, vr, value in removed
    ]
    coverage = Coverage(
        planned=frozenset(value.source for value in values),
        collected=tuple(values),
        options=tuple(options),
    )
    return release_condition(coverage, written)


def _why(condition):
    return [why for _, why in condition.exempted]


# What a set of options keeps.


def test_an_option_keeps_what_it_gives_k_and_the_basic_profile_does_not():
    kept = kept_by((DEVICE_IDENTITY,))

    # Table E.1-1's rows, and a reviewed supplementary rule's (D-022).
    for tag in ("(0008,1010)", "(0018,1000)", "(0018,1200)", "(300A,00D4)"):
        assert kept[tag] == {DEVICE_IDENTITY}
    # Not the AE titles that it cleans, nor what the Basic Profile keeps.
    assert not kept.keys() & ae_titles.TAGS
    assert "(0008,0070)" not in kept
    assert not kept_by(())


def test_tps_import_keeps_no_device_date_that_modified_dates_shifts():
    kept = kept_by(compose_policy("tps-import").options)

    assert kept["(0008,1010)"] == {DEVICE_IDENTITY}
    assert "(0010,1010)" in kept  # Patient's Age, Retain Patient Characteristics
    # Date of Last Calibration: K under Retain Device Identity, but C under
    # Modified Dates, which the preset applies (D-007).
    assert "(0018,1200)" not in kept
    assert "(0018,1200)" in kept_by((DEVICE_IDENTITY,))


def test_full_dates_keep_the_dates_that_modified_dates_shift():
    assert kept_by((FULL_DATES,))["(0008,0020)"] == {FULL_DATES}
    assert "(0008,0020)" not in kept_by((MODIFIED_DATES,))


def test_coverage_carries_the_options_through_a_merge():
    first = Coverage(planned=frozenset(), collected=(), options=(DEVICE_IDENTITY,))
    second = Coverage(planned=frozenset(), collected=(), options=(DEVICE_IDENTITY,))

    assert Coverage.merge(first, second).options == (DEVICE_IDENTITY,)
    with pytest.raises(TypeError, match="options"):
        Coverage(planned=frozenset(), collected=(), options=[DEVICE_IDENTITY])


# Text that an option keeps.


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source, source_vr",
    [
        ("(0008,0055)", "AE"),  # Station AE Title, which the option cleans
        ("(0040,0241)", "AE"),  # Performed Station AE Title
        ("(0009,1012)", "LO"),  # a private data element
        ("(0018,1000)", "LO"),  # Device Serial Number, as in a removed sequence
    ],
)
@pytest.mark.parametrize(
    "kept, vr",
    [
        (STATION_NAME, "SH"),
        (DEVICE_SERIAL_NUMBER, "LO"),
        (TREATMENT_MACHINE_NAME, "SH"),
    ],
)
def test_kept_device_identity_found_from_the_option_or_a_private_value_is_released(
    source, source_vr, kept, vr
):
    written = _written(_element(kept, vr, STATION))
    condition = _condition(written, [DEVICE_IDENTITY], (source, source_vr, STATION))

    assert condition.decision is Decision.RELEASE
    assert _why(condition) == [Exemption.RETAINED_TEXT]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_kept_institution_identity_found_from_a_private_value_is_released():
    written = _written(_element(0x00080080, "LO", f"{INSTITUTION} NORTH"))
    condition = _condition(
        written, [INSTITUTION_IDENTITY], ("(0009,1012)", "LO", INSTITUTION)
    )

    assert condition.decision is Decision.RELEASE
    assert _why(condition) == [Exemption.RETAINED_TEXT]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_text_that_no_selected_option_keeps_still_goes_to_review():
    # Without the option, a Station Name in a written file is the Basic
    # Profile's dummy value or none, so nothing explains a finding in it.
    written = _written(_element(STATION_NAME, "SH", STATION))
    condition = _condition(written, [], ("(0008,0055)", "AE", STATION))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "source",
    [
        "(0008,0080)",  # Institution Name, which the option does not keep
        "(0008,1040)",  # Institutional Department Name
        "(0009,0010)",  # a private creator, which can name the institution
    ],
)
def test_kept_text_holding_a_value_of_another_kind_goes_to_review(source):
    written = _written(_element(STATION_NAME, "SH", STATION))
    condition = _condition(written, [DEVICE_IDENTITY], (source, "LO", INSTITUTION))

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_person_name_found_in_kept_text_still_withholds_the_file():
    written = _written(_element(STATION_NAME, "SH", "ZARQUON^ARTHUR"))
    condition = _condition(
        written, [DEVICE_IDENTITY], ("(0008,1070)", "PN", "ZARQUON^ARTHUR")
    )

    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_other_kept_text_or_text_outside_iso_646_goes_to_review():
    # Series Description is kept by no option.
    written = _written(_element(0x0008103E, "LO", STATION))
    condition = _condition(written, [DEVICE_IDENTITY], ("(0008,0055)", "AE", STATION))
    assert condition.decision is Decision.QC_REVIEW

    written = _written(_element(STATION_NAME, "SH", f"{STATION}\xe9"))
    condition = _condition(written, [DEVICE_IDENTITY], ("(0008,0055)", "AE", STATION))
    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted


# Dates and times that an option keeps.


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_removed_date_equal_to_a_kept_date_is_released():
    written = _written(_element(STUDY_DATE, "DA", DAY))
    condition = _condition(written, [FULL_DATES], (BIRTH_DATE, "DA", DAY))

    assert condition.decision is Decision.RELEASE
    assert _why(condition) == [Exemption.RETAINED_VALUE]


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize("options", [[], [MODIFIED_DATES]])
def test_a_removed_date_in_a_date_that_no_option_keeps_still_withholds(options):
    # Under Modified Dates the Study Date is shifted, not kept, and a written
    # date equal to a source would mean that the shift failed.
    written = _written(_element(STUDY_DATE, "DA", DAY))
    condition = _condition(written, options, (BIRTH_DATE, "DA", DAY))

    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_removed_date_inside_a_longer_kept_value_still_withholds():
    # Acquisition DateTime, which Full Dates keeps, holds the date and a time.
    written = _written(_element(0x0008002A, "DT", f"{DAY}101500"))
    condition = _condition(written, [FULL_DATES], (BIRTH_DATE, "DA", DAY))

    assert condition.decision is Decision.WITHHOLD


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_kept_date_equal_to_its_own_source_still_withholds():
    written = _written(_element(STUDY_DATE, "DA", DAY))
    condition = _condition(written, [FULL_DATES], ("(0008,0020)", "DA", DAY))

    assert condition.decision is Decision.WITHHOLD


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_removed_uid_equal_to_a_kept_uid_still_withholds():
    # Retain UIDs keeps SOP Instance UID; a replaced reference to it whose
    # source is the same UID is not explained (UIDs are never exempt).
    uid = "2.25.123456789012345678901234567890"
    written = _written(_element(0x00080018, "UI", uid))
    condition = _condition(written, ["retain_uids"], ("(0008,1155)", "UI", uid))

    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted


# A run under Retain Device Identity.


def _plan(**attributes):
    plan = synthetic.rt_plan()
    for keyword, value in attributes.items():
        setattr(plan, keyword, value)
    plan.private_block(0x0009, "ZARQUON SCANNERS", create=True).add_new(
        0x12, "LO", STATION
    )
    return plan


def _transformed(plan):
    transform = InstanceTransform(
        compose_custom_policy([DEVICE_IDENTITY]), KEY, unvalidated_policy=True
    )
    data = synthetic.written(plan)
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    return result


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.deid_requirement("PS3.15-E.3.8-01")
def test_a_station_named_as_its_ae_title_and_in_private_values_is_released():
    plan = _plan(StationAETitle=STATION, StationName=STATION)

    result = _transformed(plan)

    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.StationName == STATION
    assert written.StationAETitle == ae_titles.ae_token(STATION, KEY)
    assert 0x00091012 not in written
    assert isinstance(result.evidence, Coverage)
    assert result.evidence.options == (DEVICE_IDENTITY,)  # pylint: disable=no-member
    condition = release_condition(result.evidence, result.data)
    assert condition.decision is Decision.RELEASE
    # The AE title and the private value are each found in the Station Name.
    assert {
        (finding.source.tag, finding.location.element.tag, why)
        for finding, why in condition.exempted
        if finding.location.element is not None
    } == {
        ("(0008,0055)", "(0008,1010)", Exemption.RETAINED_TEXT),
        ("(0009,1012)", "(0008,1010)", Exemption.RETAINED_TEXT),
    }
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert isinstance(decision, run.Release)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.deid_requirement("PS3.15-E.3.8-01")
def test_a_station_named_after_its_removed_institution_goes_to_review():
    plan = _plan(
        StationAETitle=STATION, StationName=STATION, InstitutionName=INSTITUTION
    )

    result = _transformed(plan)

    assert "InstitutionName" not in pydicom.dcmread(io.BytesIO(result.data))
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert isinstance(decision, run.HoldForReview)
