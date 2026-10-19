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

"""Modify dates and times under Retain Longitudinal Temporal Information with Modified Dates.

Under the Modified Dates Option, Table E.1-1 and the supplementary rules give
C to every date, time, and datetime attribute but Patient's Birth Date,
Patient's Birth Time, and GPS Time Stamp, and to Timezone Offset From UTC
(0008,0201), Frame Origin Timestamp (0034,0007), and Certified Timestamp
(0400,0310). E.3.6 has their values modified so as to reduce the
possibility of matching while keeping the temporal relationships that the
application needs, and the conformance statement describe how. Each value is
modified by its attribute's temporal role
(:mod:`~pymedphys._dicom.deidentify.temporal_roles`, D-007), with the
subject's offset (:mod:`~pymedphys._dicom.deidentify.dates`, D-006):

- a subject-event or radiation-source DA value moves backwards by the
  subject's whole number of weeks; a DT value moves its date and keeps its
  time, once a value with its own UTC offset is in the instance's local
  time, labelled with the nominal offset; a TM value is kept, since whole
  weeks keep the time of day; and Frame Origin Timestamp moves its seconds;
- a device, vocabulary-version, or other value takes D's dummy value for its
  VR, or the second where the source equals the first
  (:func:`~pymedphys._dicom.deidentify.dummy_values.values_for_d`), since
  moving it would disclose the offset wherever its original is known;
- Timezone Offset From UTC becomes the nominal offset ``+0000``.

The subject's offset is derived from the run's key and the subject's identity
(:func:`~pymedphys._dicom.deidentify.dates.date_offset_weeks`), so every
instance of a subject in a run moves by the same offset, and runs, whose keys
differ, by unrelated ones (D-004). The instance's local time is its Timezone
Offset From UTC, where it has one, and otherwise the UTC offset of the
earliest of its DT values that has one
(:func:`~pymedphys._dicom.deidentify.dates.local_offset`). Each value of a multi-valued
attribute is modified on its own, an empty value stays empty, and an
attribute with no value is written with none.

A value that cannot be modified so is left pending, which sequesters its
instance, as an attribute given C that no cleaner settles does (D-034): a
date that is not valid, a DT value without a full date or at a leap second,
one whose precision cannot express its conversion to local time, a shifted
date before year 1, a valid Timezone Offset From UTC that differs from
another in the instance, a value read in a VR that the
pinned dictionary does not give its attribute or that its role does not
provide for, and every shifted value of an instance without a subject's
identity.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable

from . import dates
from .dummy_values import NoDummyValueError, values_for_d
from .file_layout import ElementPath
from .keys import DeidKey
from .pseudonyms import SubjectIdentity
from .residuals import SourceValue
from .standard import dictionary_attribute
from .temporal_roles import TemporalAction, TemporalRole, load_temporal_roles

# The attributes that Table E.1-1 and the supplementary rules give C under
# Retain Longitudinal Temporal Information with Modified Dates in PS3.15
# 2026d: every attribute with a temporal role but Patient's Birth Date
# (0010,0030), Patient's Birth Time (0010,0032), and GPS Time Stamp
# (0016,0077), which the option removes.
TAGS = frozenset(
    {
        "(0008,0012)",  # InstanceCreationDate
        "(0008,0013)",  # InstanceCreationTime
        "(0008,0015)",  # InstanceCoercionDateTime
        "(0008,0020)",  # StudyDate
        "(0008,0021)",  # SeriesDate
        "(0008,0022)",  # AcquisitionDate
        "(0008,0023)",  # ContentDate
        "(0008,0024)",  # OverlayDate
        "(0008,0025)",  # CurveDate
        "(0008,002A)",  # AcquisitionDateTime
        "(0008,0030)",  # StudyTime
        "(0008,0031)",  # SeriesTime
        "(0008,0032)",  # AcquisitionTime
        "(0008,0033)",  # ContentTime
        "(0008,0034)",  # OverlayTime
        "(0008,0035)",  # CurveTime
        "(0008,0106)",  # ContextGroupVersion
        "(0008,0107)",  # ContextGroupLocalVersion
        "(0008,0201)",  # TimezoneOffsetFromUTC
        "(0008,0404)",  # ItemInventoryDateTime
        "(0008,0416)",  # ExpirationDateTime
        "(0008,041F)",  # StudyUpdateDateTime
        "(0010,21D0)",  # LastMenstrualDate
        "(0012,0086)",  # EthicsCommitteeApprovalEffectivenessStartDate
        "(0012,0087)",  # EthicsCommitteeApprovalEffectivenessEndDate
        "(0014,0102)",  # SecondaryReviewDate
        "(0014,0103)",  # SecondaryReviewTime
        "(0014,1020)",  # ExpiryDate
        "(0014,3076)",  # DateOfGainCalibration
        "(0014,3077)",  # TimeOfGainCalibration
        "(0014,4076)",  # ProcedureCreationDate
        "(0014,4078)",  # ProcedureExpirationDate
        "(0014,407A)",  # ProcedureLastModifiedDate
        "(0014,407C)",  # CalibrationTime
        "(0014,407E)",  # CalibrationDate
        "(0016,008D)",  # GPSDateStamp
        "(0018,0027)",  # InterventionDrugStopTime
        "(0018,0035)",  # InterventionDrugStartTime
        "(0018,1012)",  # DateOfSecondaryCapture
        "(0018,1014)",  # TimeOfSecondaryCapture
        "(0018,1042)",  # ContrastBolusStartTime
        "(0018,1043)",  # ContrastBolusStopTime
        "(0018,1072)",  # RadiopharmaceuticalStartTime
        "(0018,1073)",  # RadiopharmaceuticalStopTime
        "(0018,1078)",  # RadiopharmaceuticalStartDateTime
        "(0018,1079)",  # RadiopharmaceuticalStopDateTime
        "(0018,1200)",  # DateOfLastCalibration
        "(0018,1201)",  # TimeOfLastCalibration
        "(0018,1202)",  # DateTimeOfLastCalibration
        "(0018,1203)",  # CalibrationDateTime
        "(0018,1204)",  # DateOfManufacture
        "(0018,1205)",  # DateOfInstallation
        "(0018,700C)",  # DateOfLastDetectorCalibration
        "(0018,700E)",  # TimeOfLastDetectorCalibration
        "(0018,9074)",  # FrameAcquisitionDateTime
        "(0018,9151)",  # FrameReferenceDateTime
        "(0018,9369)",  # SourceStartDateTime
        "(0018,936A)",  # SourceEndDateTime
        "(0018,9516)",  # StartAcquisitionDateTime
        "(0018,9517)",  # EndAcquisitionDateTime
        "(0018,9623)",  # FunctionalSyncPulse
        "(0018,9701)",  # DecayCorrectionDateTime
        "(0018,9804)",  # ExclusionStartDateTime
        "(0018,9919)",  # InstructionPerformedDateTime
        "(0018,A002)",  # ContributionDateTime
        "(0020,3403)",  # ModifiedImageDate
        "(0020,3405)",  # ModifiedImageTime
        "(0032,0032)",  # StudyVerifiedDate
        "(0032,0033)",  # StudyVerifiedTime
        "(0032,0034)",  # StudyReadDate
        "(0032,0035)",  # StudyReadTime
        "(0032,1000)",  # ScheduledStudyStartDate
        "(0032,1001)",  # ScheduledStudyStartTime
        "(0032,1010)",  # ScheduledStudyStopDate
        "(0032,1011)",  # ScheduledStudyStopTime
        "(0032,1040)",  # StudyArrivalDate
        "(0032,1041)",  # StudyArrivalTime
        "(0032,1050)",  # StudyCompletionDate
        "(0032,1051)",  # StudyCompletionTime
        "(0034,0007)",  # FrameOriginTimestamp
        "(0038,001A)",  # ScheduledAdmissionDate
        "(0038,001B)",  # ScheduledAdmissionTime
        "(0038,001C)",  # ScheduledDischargeDate
        "(0038,001D)",  # ScheduledDischargeTime
        "(0038,0020)",  # AdmittingDate
        "(0038,0021)",  # AdmittingTime
        "(0038,0030)",  # DischargeDate
        "(0038,0032)",  # DischargeTime
        "(003A,0314)",  # ImpedanceMeasurementDateTime
        "(0040,0002)",  # ScheduledProcedureStepStartDate
        "(0040,0003)",  # ScheduledProcedureStepStartTime
        "(0040,0004)",  # ScheduledProcedureStepEndDate
        "(0040,0005)",  # ScheduledProcedureStepEndTime
        "(0040,0244)",  # PerformedProcedureStepStartDate
        "(0040,0245)",  # PerformedProcedureStepStartTime
        "(0040,0250)",  # PerformedProcedureStepEndDate
        "(0040,0251)",  # PerformedProcedureStepEndTime
        "(0040,2004)",  # IssueDateOfImagingServiceRequest
        "(0040,2005)",  # IssueTimeOfImagingServiceRequest
        "(0040,4005)",  # ScheduledProcedureStepStartDateTime
        "(0040,4008)",  # ScheduledProcedureStepExpirationDateTime
        "(0040,4010)",  # ScheduledProcedureStepModificationDateTime
        "(0040,4011)",  # ExpectedCompletionDateTime
        "(0040,4050)",  # PerformedProcedureStepStartDateTime
        "(0040,4051)",  # PerformedProcedureStepEndDateTime
        "(0040,4052)",  # ProcedureStepCancellationDateTime
        "(0040,A023)",  # FindingsGroupRecordingDateTrial
        "(0040,A024)",  # FindingsGroupRecordingTimeTrial
        "(0040,A030)",  # VerificationDateTime
        "(0040,A032)",  # ObservationDateTime
        "(0040,A033)",  # ObservationStartDateTime
        "(0040,A034)",  # EffectiveStartDateTime
        "(0040,A035)",  # EffectiveStopDateTime
        "(0040,A082)",  # ParticipationDateTime
        "(0040,A110)",  # DateOfDocumentOrVerbalTransactionTrial
        "(0040,A112)",  # TimeOfDocumentCreationOrVerbalTransactionTrial
        "(0040,A120)",  # DateTime
        "(0040,A121)",  # Date
        "(0040,A122)",  # Time
        "(0040,A13A)",  # ReferencedDateTime
        "(0040,A192)",  # ObservationDateTrial
        "(0040,A193)",  # ObservationTimeTrial
        "(0040,B034)",  # AnnotationDateTime
        "(0040,B036)",  # SegmentDefinitionDateTime
        "(0040,DB06)",  # TemplateVersion
        "(0040,DB07)",  # TemplateLocalVersion
        "(0040,E004)",  # HL7DocumentEffectiveTime
        "(0044,0004)",  # ApprovalStatusDateTime
        "(0044,000B)",  # ProductExpirationDateTime
        "(0044,0010)",  # SubstanceAdministrationDateTime
        "(0044,0104)",  # AssertionDateTime
        "(0044,0105)",  # AssertionExpirationDateTime
        "(0068,6226)",  # EffectiveDateTime
        "(0068,6270)",  # InformationIssueDateTime
        "(0070,0082)",  # PresentationCreationDate
        "(0070,0083)",  # PresentationCreationTime
        "(0072,000A)",  # HangingProtocolCreationDateTime
        "(0072,0061)",  # SelectorDAValue
        "(0072,0063)",  # SelectorDTValue
        "(0072,006B)",  # SelectorTMValue
        "(0100,0420)",  # SOPAuthorizationDateTime
        "(0400,0105)",  # DigitalSignatureDateTime
        "(0400,0310)",  # CertifiedTimestamp
        "(0400,0562)",  # AttributeModificationDateTime
        "(2100,0040)",  # CreationDate
        "(2100,0050)",  # CreationTime
        "(3006,0008)",  # StructureSetDate
        "(3006,0009)",  # StructureSetTime
        "(3006,002D)",  # ROIDateTime
        "(3006,002E)",  # ROIObservationDateTime
        "(3008,0024)",  # TreatmentControlPointDate
        "(3008,0025)",  # TreatmentControlPointTime
        "(3008,0054)",  # FirstTreatmentDate
        "(3008,0056)",  # MostRecentTreatmentDate
        "(3008,0162)",  # SafePositionExitDate
        "(3008,0164)",  # SafePositionExitTime
        "(3008,0166)",  # SafePositionReturnDate
        "(3008,0168)",  # SafePositionReturnTime
        "(3008,0250)",  # TreatmentDate
        "(3008,0251)",  # TreatmentTime
        "(300A,0006)",  # RTPlanDate
        "(300A,0007)",  # RTPlanTime
        "(300A,022C)",  # SourceStrengthReferenceDate
        "(300A,022E)",  # SourceStrengthReferenceTime
        "(300A,0736)",  # TreatmentToleranceViolationDateTime
        "(300A,073A)",  # RecordedRTControlPointDateTime
        "(300A,0741)",  # InterlockDateTime
        "(300A,0760)",  # OverrideDateTime
        "(300C,0127)",  # BeamHoldTransitionDateTime
        "(300E,0004)",  # ReviewDate
        "(300E,0005)",  # ReviewTime
        "(3010,004C)",  # IntendedPhaseStartDate
        "(3010,004D)",  # IntendedPhaseEndDate
        "(3010,0085)",  # IntendedFractionStartTime
        "(4008,0100)",  # InterpretationRecordedDate
        "(4008,0101)",  # InterpretationRecordedTime
        "(4008,0108)",  # InterpretationTranscriptionDate
        "(4008,0109)",  # InterpretationTranscriptionTime
        "(4008,0112)",  # InterpretationApprovalDate
        "(4008,0113)",  # InterpretationApprovalTime
        "(4010,1025)",  # RouteSegmentStartTime
        "(4010,1026)",  # RouteSegmentEndTime
        "(4010,102B)",  # AlarmDecisionTime
        "(4010,1041)",  # OOIOwnerCreationTime
    }
)
# The VRs that the attributes are read in: those of the dates, times, and
# datetimes, of Timezone Offset From UTC (SH), and of the IEEE 1588
# timestamps (OB).
VRS = frozenset({"DA", "DT", "OB", "SH", "TM"})
TIMEZONE_OFFSET = "(0008,0201)"
FRAME_ORIGIN_TIMESTAMP = "(0034,0007)"
METHOD = (
    "Each value is modified by its attribute's temporal role, and "
    "each subject's dates move backwards by one whole number of weeks, from "
    f"{dates.MIN_OFFSET_WEEKS} to {dates.MAX_OFFSET_WEEKS} and never zero: "
    f"{dates.MIN_OFFSET_WEEKS} plus the first 64 bits of the HMAC-SHA256 of "
    "the subject's identity, its Patient ID with its issuer, in the "
    "`date-offset` domain of the run's key, modulo "
    f"{dates.MAX_OFFSET_WEEKS - dates.MIN_OFFSET_WEEKS + 1}. "
    "Within a run, every instance of a subject moves by the same offset, so "
    "intervals, weekdays, and times of day are kept; across runs, whose keys "
    "differ, offsets are unrelated. A subject-event or radiation-source DA "
    "value moves by the offset; a DT value moves its date and keeps its "
    "time, once a value with its own UTC offset is converted to the "
    f"instance's local time and given the offset `{dates.NOMINAL_UTC_OFFSET}`; "
    "a TM value is kept, since whole weeks keep the time of day; and Frame "
    "Origin Timestamp (0034,0007) moves its seconds by the offset, keeping "
    "the timing of frames exactly. A device, vocabulary-version, or other "
    "value takes D's dummy value for its VR, or the second where the source "
    "equals the first, since moving it would disclose the offset wherever "
    "its original is known. Timezone Offset From UTC (0008,0201) becomes "
    f"`{dates.NOMINAL_UTC_OFFSET}`. The instance's local time is its "
    "Timezone Offset From UTC where it has a valid one, and otherwise the UTC "
    "offset of the earliest of its DT values that has one; a Timezone Offset "
    "From UTC that is not a valid offset also becomes "
    f"`{dates.NOMINAL_UTC_OFFSET}`. Each value of a multi-valued attribute is "
    "modified on its own, "
    "and an empty value stays empty. An instance is sequestered where a value "
    "cannot be modified so: a date that is not valid, a DT value without a "
    "full date or at a leap second, one whose precision cannot express its "
    "conversion to local time, a shifted date before year 1, valid Timezone "
    "Offset From UTC values that differ within the instance, or an instance "
    "whose subject has no identity."
)

# What a value becomes: the values written in its place, and whether they are
# the source's own.
Written = tuple[tuple[str | bytes, ...], bool]
# The padding that a DA, DT, or TM value may carry.
_PADDING = " \x00"


class _Unmodified(Exception):
    """A value that cannot be modified, whose attribute stays pending."""


def modify_dates(
    values: Iterable[SourceValue], key: DeidKey, identity: SubjectIdentity | None
) -> dict[ElementPath, Written]:
    """Return how one instance's dates, times, and datetimes are modified.

    Parameters
    ----------
    values : iterable of SourceValue
        The source values of the instance's attributes that are given C
        under Modified Dates and are to be written, each read in one of
        :data:`VRS`.
    key : DeidKey
        The run's key.
    identity : SubjectIdentity or None
        The subject's identity, as the run resolves it, or None for an
        instance without one.

    Returns
    -------
    dict of ElementPath to tuple
        For each value that can be modified, the values written in its
        place, ``()`` for an attribute with no value, and whether they are
        the source's own, as a kept time's are. A value that cannot be
        modified is left out, so that its attribute stays pending.
    """
    given = tuple(values)
    weeks = None if identity is None else dates.date_offset_weeks(key, identity)
    roles = load_temporal_roles().rules
    local = _local_offset(given)
    written: dict[ElementPath, Written] = {}
    for value in given:
        rule = roles.get(value.source.tag)
        if rule is None:
            continue
        try:
            written[value.source] = _modified(value, rule.role, weeks, local, key)
        except (_Unmodified, NoDummyValueError, ValueError):
            continue
    return written


def _texts(value: SourceValue) -> list[str]:
    """Return a text value's values, or none for a value that is empty."""
    if not isinstance(value.value, str):
        raise _Unmodified
    return value.value.split("\\") if value.value else []


def _content(text: str) -> bool:
    return bool(text.strip(_PADDING))


def _local_offset(given: tuple[SourceValue, ...]) -> Callable[[], str | None]:
    """Return a call that gives the instance's local time, worked out once.

    It is the instance's Timezone Offset From UTC, every valid value of
    which must be the same, or otherwise the UTC offset of the earliest DT
    value that has one, or None. A Timezone Offset From UTC that is not a
    valid offset says nothing of the local time, so it counts as absent. The
    call raises :class:`ValueError` where the instance's valid offsets
    differ, or, without one, a DT value is not valid.
    """
    zones = {
        zone.strip(" ")
        for value in given
        if value.source.tag == TIMEZONE_OFFSET and isinstance(value.value, str)
        for zone in _texts(value)
        if _valid_offset(zone.strip(" "))
    }
    datetimes = [
        text
        for value in given
        if value.vr == "DT" and isinstance(value.value, str)
        for text in _texts(value)
        if _content(text)
    ]

    @functools.cache
    def local() -> str | None:
        if len(zones) > 1:
            raise ValueError("the instance's time zone offsets differ")
        return dates.local_offset(next(iter(zones), None), datetimes)

    return local


def _valid_offset(zone: str) -> bool:
    """Whether a Timezone Offset From UTC value is a valid UTC offset."""
    if not zone:
        return False
    try:
        dates.local_offset(zone, ())
    except ValueError:
        return False
    return True


def _modified(
    value: SourceValue,
    role: TemporalRole,
    weeks: int | None,
    local: Callable[[], str | None],
    key: DeidKey,
) -> Written:
    """Return what one value becomes under its role, or raise if it cannot."""
    attribute = dictionary_attribute(value.source.tag)
    if attribute is None or value.vr not in attribute.vrs:
        raise _Unmodified
    action = role.action
    if action is TemporalAction.NOMINAL_OFFSET:
        if value.vr != "SH":
            raise _Unmodified
        zones = _texts(value)
        if any(zone.strip(" ") for zone in zones):
            local()  # raises where valid offsets differ
        return tuple(
            dates.NOMINAL_UTC_OFFSET if z.strip(" ") else "" for z in zones
        ), False
    if action is TemporalAction.DUMMY:
        return _dummy(value, key), False
    if weeks is None:
        raise _Unmodified
    if value.vr == "OB" and value.source.tag == FRAME_ORIGIN_TIMESTAMP:
        if not isinstance(value.value, bytes):
            raise _Unmodified
        return (dates.shift_frame_origin_timestamp(value.value, weeks),), False
    texts = _texts(value)
    if value.vr == "TM":
        return tuple(texts), any(_content(text) for text in texts)
    if value.vr == "DA":
        moved = [dates.shift_date(t, weeks) if _content(t) else "" for t in texts]
    elif value.vr == "DT":
        moved = [_shift_datetime(t, weeks, local) if _content(t) else "" for t in texts]
    else:
        raise _Unmodified
    return tuple(moved), False


def _shift_datetime(text: str, weeks: int, local: Callable[[], str | None]) -> str:
    """Return a DT value in the instance's local time, moved by ``weeks``.

    A valid DT value has a sign only before its own UTC offset.
    """
    if "+" in text or "-" in text:
        offset = local()
        if offset is None:
            raise _Unmodified
        text = dates.to_local_datetime(text, offset)
    return dates.shift_datetime(text, weeks)


def _dummy(value: SourceValue, key: DeidKey) -> tuple[str, ...]:
    """Return D's dummy values in place of a value, or none for an empty one."""
    if value.vr not in ("DA", "DT", "TM"):
        raise _Unmodified
    texts = [text for text in _texts(value) if _content(text)]
    if not texts:
        return ()
    attribute = dictionary_attribute(value.source.tag)
    assert attribute is not None  # checked by _modified
    return tuple(str(each) for each in values_for_d(value.vr, attribute.vm, texts, key))
