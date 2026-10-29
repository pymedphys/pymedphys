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

"""The Clean Structured Content Option on six Structured Report IODs' root templates.

The Chest CAD SR, Colon CAD SR, Procedure Log, Spectacle Prescription
Report, Macular Grid Thickness and Volume Report, and Waveform Annotation SR
IODs are supported. As :mod:`.test_deidentify_structured_report_content`
does for four other SR IODs, these tests show what the option does with the
content trees of their root templates (D-047): which option sets keep a
report that holds only the rows that its templates require; which optional
rows take the whole tree out under each option set; the action that each
listed value of a kept tree takes; and what is written and released. The
reports are synthetic, built from the templates of PS3.16 2026d by
:mod:`._synthetic_specialised_reports`.

A preset with the option added is composed by adding it to every preset's
options for the test alone, since no preset selects it, so that the policy
that Clean Descriptors falls back to, another preset's, selects it too.
"""

import io
import types

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import content_items, policy, run, scope
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _corpus_run
from . import _synthetic_references as synthetic
from . import _synthetic_specialised_reports as reports

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
CSC_CODE = "113104"
CONTENT = "(0040,A730)"
VERIFYING_OBSERVER = "(0040,A073)"
CHEST = "chest CAD"
COLON = "colon CAD"
LOG = "procedure log"
SPECTACLES = "spectacle prescription"
MACULAR = "macular grid"
WAVEFORM = "waveform annotations"
# Each report's builder, IOD, optional rows, and root template, which PS3.3
# 2026d Section A.35 has the IOD constructed from: A.35.6, A.35.10, A.35.7
# ("may be"), A.35.9, A.35.11, and A.35.23.
REPORTS = {
    CHEST: (
        reports.chest_cad_report,
        reports.CHEST_CAD_SR_IOD,
        reports.CHEST_CAD_OPTIONAL_ROWS,
        "4100",
    ),
    COLON: (
        reports.colon_cad_report,
        reports.COLON_CAD_SR_IOD,
        reports.COLON_CAD_OPTIONAL_ROWS,
        "4120",
    ),
    LOG: (
        reports.procedure_log,
        reports.PROCEDURE_LOG_IOD,
        reports.LOG_OPTIONAL_ROWS,
        "3001",
    ),
    SPECTACLES: (
        reports.spectacle_prescription,
        reports.SPECTACLE_PRESCRIPTION_IOD,
        reports.SPECTACLE_OPTIONAL_ROWS,
        "2020",
    ),
    MACULAR: (reports.macular_grid_report, reports.MACULAR_GRID_IOD, (), "2100"),
    WAVEFORM: (
        reports.waveform_annotations,
        reports.WAVEFORM_ANNOTATION_IOD,
        reports.WAVEFORM_OPTIONAL_ROWS,
        "3750",
    ),
}
# The reports that the option keeps under some option set.
KEPT = (CHEST, COLON, LOG, SPECTACLES, WAVEFORM)
PRESETS = ("basic", "basic-clean-descriptors", "tps-import", "public-release")
# Every option of Table E.1-1 that can be selected with the others, with
# Full Dates, which Retain Device Identity does not conflict with.
EVERY_OPTION = (
    CSC,
    policy.SAFE_PRIVATE,
    policy.UIDS,
    policy.DEVICE_IDENTITY,
    policy.INSTITUTION_IDENTITY,
    policy.PATIENT_CHARACTERISTICS,
    policy.FULL_DATES,
    policy.CLEAN_DESCRIPTORS,
)
RETAIN_OPTIONS = (
    (),
    (policy.SAFE_PRIVATE,),
    (policy.UIDS,),
    (policy.DEVICE_IDENTITY,),
    (policy.INSTITUTION_IDENTITY,),
    (policy.PATIENT_CHARACTERISTICS,),
    (policy.FULL_DATES,),
    (policy.MODIFIED_DATES,),
    (policy.CLEAN_DESCRIPTORS,),
)
OPTION_SETS = [
    *((preset, None) for preset in PRESETS),
    *((None, (CSC, *options)) for options in RETAIN_OPTIONS),
    (None, EVERY_OPTION),
]
# The value attributes of content items (PS3.3 Table 10-2).
VALUE_TAGS = frozenset(content_items.VALUE_ATTRIBUTES.values())
SOURCE_VALUES = (
    reports.SENTINEL,
    reports.PATIENT_ID,
    *reports.NAMES,
    *reports.UIDS,
    *reports.DATES,
)


@pytest.fixture(name="with_option")
def _with_option(monkeypatch):
    """Return a function that composes a preset's policy with the option added."""
    monkeypatch.setattr(
        policy,
        "PRESETS",
        types.MappingProxyType(
            {preset: (*options, CSC) for preset, options in policy.PRESETS.items()}
        ),
    )
    return policy.compose_policy


def _report(name, optional=(), **kwargs):
    build, iod, _, _ = REPORTS[name]
    return build(optional, **kwargs), iod


def _planned(dataset, iod, composed):
    """Return the content items' actions and the instance's plan."""
    source = read_source(synthetic.written(dataset))
    iod_ = load_iod_tables().iods[iod]
    actions = content_items.content_item_actions(source, composed, iod_)
    return actions, plan_instance(source, ElementRules(composed), iod_, actions)


def _kept(dataset, iod, composed):
    """Return whether the option keeps the report's content tree."""
    actions, _ = _planned(dataset, iod, composed)
    return actions.get(ElementPath((), CONTENT)) == "K"


def _composed(with_option, preset, options):
    return (
        with_option(preset)
        if options is None
        else policy.compose_custom_policy(options)
    )


def _int(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _item(dataset, items):
    for tag, index in items:
        dataset = dataset[_int(tag)].value[index]
    return dataset


def _values_by_concept(dataset, actions):
    """Return the action of each content item's value, by its concept's meaning."""
    found = {}
    for path, action in actions.items():
        if path.tag in VALUE_TAGS:
            item = _item(dataset, path.items)
            meaning = item.ConceptNameCodeSequence[0].CodeMeaning
            found.setdefault(meaning, set()).add(action)
    return {meaning: "/".join(sorted(taken)) for meaning, taken in found.items()}


def _concepts(dataset):
    """Yield each named content item of a tree, the root first, with its key."""
    if "ConceptNameCodeSequence" in dataset:
        code = dataset.ConceptNameCodeSequence[0]
        yield (
            code.CodeMeaning,
            (code.CodingSchemeDesignator, code.CodeValue, dataset.ValueType),
        )
    for child in dataset.get("ContentSequence", []):
        yield from _concepts(child)


def _shape(dataset):
    """Return the tree's Value Types and concept names, depth first."""
    found = [(dataset.get("ValueType"), tuple(_concepts(dataset))[:1])]
    for child in dataset.get("ContentSequence", []):
        found.extend(_shape(child))
    return found


def _transformed(composed, dataset):
    data = synthetic.written(dataset)
    record = InstanceRecord.from_file(data)
    cleaning = (
        DescriptorCleaning(None, ReviewedNames.empty())
        if policy.CLEAN_DESCRIPTORS in composed.options
        else None
    )
    transform = InstanceTransform(
        composed,
        KEY,
        cleaning=cleaning,
        face_review=_corpus_run.face_review_for(composed),
        unvalidated_policy=True,
    )
    # Under tps-import, the subject's synthetic birth date is chosen first.
    transform.prepare({0: record}, [data].__getitem__)
    return transform(data, record)


def _released(composed, dataset):
    """Return the written file and the release gate's decision on it."""
    result = _transformed(composed, dataset)
    assert isinstance(result, run.Transformed), result
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    return result.data, decision


def _evidence_item(written, sequence="CurrentRequestedProcedureEvidenceSequence"):
    """Return the series item and the instance item of an evidence sequence."""
    (study,) = written[sequence]
    (series,) = study.ReferencedSeriesSequence
    (instance,) = series.ReferencedSOPSequence
    return series, instance


@pytest.mark.parametrize("name", REPORTS)
def test_each_report_is_of_a_supported_iod(name):
    build, iod, _, template = REPORTS[name]
    dataset = build()
    classification = scope.classify(
        dataset.SOPClassUID, synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    )

    assert classification == scope.Classification(scope.Disposition.SUPPORTED, iod)
    iod_ = load_iod_tables().iods[iod]
    assert iod_.lookup(CONTENT, ())
    # Each IOD's SR Document General Module has a Verification Flag, so each
    # report is also built VERIFIED below.
    assert iod_.lookup(VERIFYING_OBSERVER, ())
    (identifier,) = dataset.ContentTemplateSequence
    assert identifier.MappingResource == "DCMR"
    assert identifier.TemplateIdentifier == template


@pytest.mark.parametrize("name", REPORTS)
def test_without_the_option_a_report_is_sequestered(name):
    dataset, iod = _report(name)

    _, plan = _planned(dataset, iod, policy.compose_policy("basic"))

    # Table E.1-1 gives Content Sequence D, and a sequence has no dummy
    # value (D-021).
    assert [s.path for s in plan.sequestrations] == [ElementPath((), CONTENT)]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", OPTION_SETS)
def test_which_option_sets_keep_a_report_of_required_rows(with_option, preset, options):
    composed = _composed(with_option, preset, options)

    # Every report but the macular grid's is kept under every option set,
    # with its required identifiers given dummy values or replaced UIDs, as
    # tested below.
    for name in REPORTS:
        dataset, iod = _report(name)
        _, plan = _planned(dataset, iod, composed)
        assert _kept(dataset, iod, composed) is (name != MACULAR), name
        assert bool(plan.sequestrations) is (name == MACULAR), name


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", OPTION_SETS)
def test_a_macular_grid_report_is_taken_out_by_its_loinc_coded_rows(
    with_option, preset, options
):
    composed = _composed(with_option, preset, options)
    dataset, iod = _report(MACULAR)
    actions = content_items.concept_actions(composed.options)
    concepts = list(_concepts(dataset))

    # TID 2101 codes its findings' container (row 1) and its thicknesses and
    # volume (rows 4 to 14) in LOINC, all of them required, and the pin
    # leaves LOINC's rows out (D-001).
    loinc = {meaning for meaning, key in concepts if key[0] == "LN"}
    assert loinc == {
        reports.FINDINGS.meaning,
        reports.MACULAR_GRID_TOTAL_VOLUME.meaning,
        *(code.meaning for code in reports.MACULAR_GRID_THICKNESSES),
    }
    assert "LN" in content_items.UNMATCHED_SCHEMES
    assert not _kept(dataset, iod, composed)
    # No other concept of the tree is removed, so LOINC is what takes it out.
    assert not {
        meaning
        for meaning, key in concepts
        if key[0] != "LN" and actions.get(key) == content_items.REMOVE
    }


# The optional rows of the procedure log that take the tree out under every
# option set: Table E.3.4-1 gives each X, or X with C under Clean
# Descriptors, which falls back to X (D-009).
LOG_REMOVED_UNDER_EVERY_OPTION = {
    "TID 1003 row 1a",  # Person Observer's Login Name
    "TID 3001 row 4",  # Room identification
    "TID 3010 row 2",  # Comment
    "TID 3001 row 6 Physician Note",
}
# Retain Institution Identity keeps Person Observer's Organization Name.
LOG_INSTITUTION = {"TID 1003 row 2"}
# Retain Device Identity keeps Equipment identification.
LOG_DEVICE = {"TID 3001 row 5"}
# A dates option keeps DateTime of Recording of Log Entry, X otherwise.
LOG_DATES = {"TID 3010 row 5"}
LOG_REMOVED_UNDER_BASIC = (
    LOG_REMOVED_UNDER_EVERY_OPTION | LOG_INSTITUTION | LOG_DEVICE | LOG_DATES
)
# Anatomic Identifier is X, with C under Clean Descriptors.
CHEST_REMOVED_UNDER_EVERY_OPTION = {"TID 4104 row 3"}
# Comment is X, with C under Clean Descriptors.
SPECTACLES_REMOVED_UNDER_EVERY_OPTION = {"TID 2020 row 8"}
# TID 3752 row 5 includes TID 321 with $Purpose (121112, DCM, "Source of
# Measurement"), whose WAVEFORM item Table E.3.4-1 gives X, K under Retain
# UIDs.
WAVEFORM_UIDS = {"TID 3750 row 19"}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("name, preset, options, removed", [
    (CHEST, "basic", None, CHEST_REMOVED_UNDER_EVERY_OPTION),
    (CHEST, None, EVERY_OPTION, CHEST_REMOVED_UNDER_EVERY_OPTION),
    (COLON, "basic", None, set()),
    (COLON, None, EVERY_OPTION, set()),
    (LOG, "basic", None, LOG_REMOVED_UNDER_BASIC),
    (
        LOG,
        "tps-import",
        None,
        LOG_REMOVED_UNDER_EVERY_OPTION | LOG_INSTITUTION,
    ),
    (
        LOG,
        "public-release",
        None,
        LOG_REMOVED_UNDER_EVERY_OPTION | LOG_INSTITUTION | LOG_DEVICE,
    ),
    (LOG, None, EVERY_OPTION, LOG_REMOVED_UNDER_EVERY_OPTION),
    (SPECTACLES, "basic", None, SPECTACLES_REMOVED_UNDER_EVERY_OPTION),
    (SPECTACLES, None, EVERY_OPTION, SPECTACLES_REMOVED_UNDER_EVERY_OPTION),
    (WAVEFORM, "basic", None, WAVEFORM_UIDS),
    (WAVEFORM, "tps-import", None, WAVEFORM_UIDS),
    (WAVEFORM, "public-release", None, WAVEFORM_UIDS),
    (WAVEFORM, None, (CSC, policy.UIDS), set()),
    (WAVEFORM, None, EVERY_OPTION, set()),
])  # fmt: skip
def test_the_optional_rows_that_take_the_tree_out(
    with_option, name, preset, options, removed
):
    composed = _composed(with_option, preset, options)
    build, iod, optional, _ = REPORTS[name]

    assert _kept(build(()), iod, composed)
    assert {
        key
        for key in optional
        if not _kept(build(reports.with_holders(key)), iod, composed)
    } == removed


def _keepable(name, removed):
    """Return the optional rows of a report other than ``removed``."""
    return tuple(key for key in REPORTS[name][2] if key not in removed)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("name, preset, options, removed, values", [
    (
        CHEST,
        "basic",
        None,
        CHEST_REMOVED_UNDER_EVERY_OPTION,
        {
            # X/D, which gives D (D-047).
            "Study Date": "D",
            "Study Time": "D",
            # D on a UIDREF item gives U's replacement; Frame of Reference
            # UID is X/D.
            "Frame of Reference UID": "U",
            "Series Instance UID": "U",
            "Tracking Unique Identifier": "U",
            # The duplicated finding's original observer.
            "Person Observer Name": "D",
        },
    ),
    (
        CHEST,
        "public-release",
        None,
        CHEST_REMOVED_UNDER_EVERY_OPTION,
        {
            "Study Date": "C",
            "Study Time": "C",
            "Frame of Reference UID": "U",
            "Series Instance UID": "U",
            "Tracking Unique Identifier": "U",
            "Person Observer Name": "D",
        },
    ),
    (
        COLON,
        "basic",
        None,
        set(),
        {
            "Frame of Reference UID": "U",
            "Study Instance UID": "U",
            "Study Date": "D",
            "Study Time": "D",
            "Series Instance UID": "U",
        },
    ),
    (
        COLON,
        None,
        EVERY_OPTION,
        set(),
        {
            "Frame of Reference UID": "K",
            "Study Instance UID": "K",
            "Study Date": "K",
            "Study Time": "K",
            "Series Instance UID": "K",
        },
    ),
    (
        LOG,
        "tps-import",
        None,
        LOG_REMOVED_UNDER_EVERY_OPTION | LOG_INSTITUTION,
        {
            "Person Observer Name": "D",
            # X/D, with C under Clean Descriptors, which falls back to D.
            "Procedure Description": "D",
            "Equipment identification": "K",
            # X/D.
            "Procedure Action ID": "D",
            "DateTime of Recording of Log Entry": "C",
        },
    ),
    (
        LOG,
        None,
        EVERY_OPTION,
        LOG_REMOVED_UNDER_EVERY_OPTION,
        {
            "Person Observer Name": "D",
            "Person Observer's Organization Name": "K",
            "Procedure Description": "D",
            "Equipment identification": "K",
            "Procedure Action ID": "D",
            "DateTime of Recording of Log Entry": "K",
        },
    ),
    (SPECTACLES, "public-release", None, SPECTACLES_REMOVED_UNDER_EVERY_OPTION, {}),
    (
        WAVEFORM,
        "public-release",
        None,
        WAVEFORM_UIDS,
        # The report's observer and the pattern event's own.
        {"Person Observer Name": "D"},
    ),
])  # fmt: skip
def test_a_kept_tree_gives_each_listed_value_its_action(
    with_option, name, preset, options, removed, values
):
    dataset, iod = _report(name, _keepable(name, removed))

    actions, plan = _planned(dataset, iod, _composed(with_option, preset, options))

    assert not plan.sequestrations
    assert _values_by_concept(dataset, actions) == values
    # The other values, among them the algorithms' names, versions, and
    # parameters, the tracking identifier, the log's notes, its lesion
    # identifier, and the person named in its staff action, the waveform
    # group's label, short label, and annotation note, and the temporal
    # coordinates' Referenced DateTime, are not listed, so they take their
    # own rules.


# The optional rows of each report that public-release, with the option
# added, keeps.
RELEASED_UNDER_PUBLIC_RELEASE = {
    CHEST: _keepable(CHEST, CHEST_REMOVED_UNDER_EVERY_OPTION),
    COLON: _keepable(COLON, set()),
    LOG: _keepable(LOG, LOG_REMOVED_UNDER_EVERY_OPTION | LOG_INSTITUTION | LOG_DEVICE),
    SPECTACLES: _keepable(SPECTACLES, SPECTACLES_REMOVED_UNDER_EVERY_OPTION),
    WAVEFORM: _keepable(WAVEFORM, WAVEFORM_UIDS),
}
# The optional rows that basic, with the option added, keeps, where they
# differ: it keeps no date in the log.
RELEASED_UNDER_BASIC = {
    **RELEASED_UNDER_PUBLIC_RELEASE,
    LOG: _keepable(LOG, LOG_REMOVED_UNDER_BASIC),
}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, released", [
    ("basic", RELEASED_UNDER_BASIC),
    ("public-release", RELEASED_UNDER_PUBLIC_RELEASE),
])  # fmt: skip
@pytest.mark.parametrize("name", KEPT)
def test_a_written_report_holds_no_source_value_and_is_released(
    with_option, name, preset, released
):
    dataset, _ = _report(name, released[name])

    data, decision = _released(with_option(preset), dataset)

    # Free text that the table does not list, such as the log's notes and
    # the waveform's labels, takes Text Value's dummy, and a person named
    # in the log's staff action Person Name's.
    for value in SOURCE_VALUES:
        assert value.encode() not in data, value
    assert isinstance(decision, run.Release), decision
    written = pydicom.dcmread(io.BytesIO(data))
    assert _shape(written) == _shape(dataset)
    assert CSC_CODE in [
        code.get("CodeValue") for code in written.DeidentificationMethodCodeSequence
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset", ("basic", "public-release"))
def test_a_written_colon_report_names_the_replaced_study_and_series(
    with_option, preset
):
    dataset, _ = _report(COLON)

    data, _ = _released(with_option(preset), dataset)

    written = pydicom.dcmread(io.BytesIO(data))
    properties = written.ContentSequence[1]
    frame, study, date = properties.ContentSequence[:3]
    # The Study Instance UID item takes the replacement that U gives the
    # header's, and the detection's Series Instance UID the one that the
    # evidence's series takes, so that the report still names them.
    assert study.UID == written.StudyInstanceUID != reports.STUDY
    detection = written.ContentSequence[3].ContentSequence[0].ContentSequence[0]
    series, _ = _evidence_item(written)
    assert detection.ContentSequence[-1].UID == series.SeriesInstanceUID
    assert series.SeriesInstanceUID != reports.CT_SERIES
    assert frame.UID != reports.FRAME_OF_REFERENCE
    # public-release modifies the Study Date as it does the header's, and
    # basic gives it a dummy value.
    assert date.Date != reports.STUDY_DATE
    if preset == "public-release":
        assert date.Date == written.StudyDate


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset", ("basic", "public-release"))
def test_a_written_waveform_annotation_keeps_its_references(with_option, preset):
    dataset, _ = _report(WAVEFORM, reports.with_holders("TID 321 row 3 datetime"))

    data, _ = _released(with_option(preset), dataset)

    written = pydicom.dcmread(io.BytesIO(data))
    (group,) = written.ContentSequence[1].ContentSequence
    event = group.ContentSequence[1]
    (coordinates,) = [i for i in event.ContentSequence if i.ValueType == "TCOORD"]
    (waveform,) = coordinates.ContentSequence
    (reference,) = waveform.ReferencedSOPSequence
    # The waveform reference names the EEG by the UID that the evidence
    # gives it, and keeps its channel.
    _, evidence = _evidence_item(written)
    assert reference.ReferencedSOPInstanceUID == evidence.ReferencedSOPInstanceUID
    assert reference.ReferencedSOPInstanceUID != reports.EEG_WAVEFORM
    assert list(reference.ReferencedWaveformChannels) == [1, 1]
    # Table E.1-1 gives Referenced DateTime (0040,A13A) D, C under Modified
    # Dates.
    assert coordinates.ReferencedDateTime != reports.ANNOTATED_DATETIME
    assert coordinates.TemporalRangeType == "POINT"


# The log's events that every option set keeps: a technologist's note, a
# staff action, an equipment event, and a complication.
LOG_EVENTS = ("TID 3001 row 6", "TID 3001 row 10", "TID 3001 row 12", "TID 3001 row 23")
OBSERVATION_DATETIME = "(0040,A032)"


def _event_times(dataset):
    """Return the Observation DateTime of each first level item that the root CONTAINS."""
    return [
        event.get("ObservationDateTime")
        for event in dataset.ContentSequence
        if event.RelationshipType == "CONTAINS"
    ]


def test_each_log_event_carries_the_time_it_occurred_in_increasing_order():
    dataset, _ = _report(LOG, REPORTS[LOG][2])

    # PS3.3 Section A.35.7.3.1.2: each first level item that the root
    # CONTAINS has Observation DateTime (0040,A032), Type 1, the time the
    # event occurred, not that of its recording, strictly increasing.
    times = _event_times(dataset)
    assert len(times) == 5
    assert times == sorted(set(times)) == list(reports.EVENT_DATETIMES)
    assert reports.LOG_DATETIME not in times
    for event in dataset.ContentSequence:
        if event.RelationshipType != "CONTAINS":
            assert "ObservationDateTime" not in event
    # A log with no events has none.
    assert _event_times(_report(LOG)[0]) == []


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options, action", [
    # X/D, which gives D in this Type 1 place.
    ("basic", None, "D"),
    ("basic-clean-descriptors", None, "D"),
    ("tps-import", None, "C"),
    ("public-release", None, "C"),
    (None, (CSC, policy.FULL_DATES), "K"),
    (None, EVERY_OPTION, "K"),
])  # fmt: skip
def test_the_log_events_times_take_their_dates_action(
    with_option, preset, options, action
):
    dataset, iod = _report(LOG, LOG_EVENTS)

    actions, plan = _planned(dataset, iod, _composed(with_option, preset, options))

    # Observation DateTime is not a content item's value, so the option
    # gives it no action of its own; Table E.1-1 gives it X/D, K under Full
    # Dates, and C under Modified Dates, in each kept event.
    assert actions.get(ElementPath((), CONTENT)) == "K"
    assert not plan.sequestrations
    assert [
        element.action
        for element in plan.elements
        if element.path.tag == OBSERVATION_DATETIME
    ] == [action] * len(LOG_EVENTS)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
def test_a_written_log_shifts_its_event_times_under_modified_dates(with_option):
    dataset, _ = _report(LOG, LOG_EVENTS)

    data, decision = _released(with_option("public-release"), dataset)

    written = pydicom.dcmread(io.BytesIO(data))
    times = _event_times(written)
    for source in reports.EVENT_DATETIMES:
        assert source.encode() not in data, source
    # Modified Dates shifts every date of the instance alike, so the events
    # keep their order and spacing.
    assert len(times) == len(LOG_EVENTS)
    assert times == sorted(set(times))
    assert [time[8:] for time in times] == [
        time[8:] for time in reports.EVENT_DATETIMES[: len(LOG_EVENTS)]
    ]
    assert isinstance(decision, run.Release), decision


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
def test_a_written_log_gives_every_event_the_same_dummy_time_under_basic(
    with_option,
):
    dataset, _ = _report(LOG, LOG_EVENTS)

    data, decision = _released(with_option("basic"), dataset)

    # D writes D-021's one dummy value for the VR, so the events keep a
    # time but lose their order: a written log of several events no longer
    # meets A.35.7.3.1.2's strictly increasing Observation DateTime. This
    # records the engine as it is; no source time is released.
    written = pydicom.dcmread(io.BytesIO(data))
    for source in reports.EVENT_DATETIMES:
        assert source.encode() not in data, source
    assert _event_times(written) == ["19000101000000"] * len(LOG_EVENTS)
    assert isinstance(decision, run.Release), decision


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("name", REPORTS)
def test_a_verified_report_is_planned_as_an_unverified_one_is(
    with_option, preset, name
):
    dataset, iod = _report(name, verified=True)

    _, plan = _planned(dataset, iod, with_option(preset))

    # Table E.1-1 gives Verifying Observer Sequence D under every option,
    # and it is Type 1C, required where the report is VERIFIED; D keeps each
    # verifier's item, with dummy values, so it sequesters nothing (D-021).
    (observer,) = [
        e for e in plan.elements if e.path == ElementPath((), VERIFYING_OBSERVER)
    ]
    assert observer.action == "D"
    unverified, _ = _report(name)
    _, unverified_plan = _planned(unverified, iod, with_option(preset))
    assert [s.path for s in plan.sequestrations] == [
        s.path for s in unverified_plan.sequestrations
    ]


@pytest.mark.parametrize("name", KEPT)
def test_a_verified_report_is_written_with_a_dummy_verifier(with_option, name):
    dataset, _ = _report(name, verified=True)

    result = _transformed(with_option("public-release"), dataset)

    assert isinstance(result, run.Transformed), result
    for value in (reports.VERIFIERS_NAME, f"{reports.SENTINEL} HOSPITAL"):
        assert value.encode() not in result.data, value
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.VerificationFlag == "VERIFIED"
    (verifier,) = written.VerifyingObserverSequence
    assert verifier.VerifyingObserverName == "DEIDENTIFIED"
    assert verifier.VerifyingOrganization == "DEIDENTIFIED"
    assert verifier.VerificationDateTime != reports.VERIFICATION_DATETIME
