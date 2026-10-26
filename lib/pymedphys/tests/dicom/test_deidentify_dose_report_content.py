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

"""The Clean Structured Content Option on Radiation Dose Structured Reports.

The X-Ray and Radiopharmaceutical Radiation Dose SR IODs are supported, but
without the option the engine sequesters each of their instances, since the
Basic Profile gives Content Sequence (0040,A730) D and a sequence has no
dummy value (D-021). These tests show what the option does with their
content trees (D-047): which presets, with the option added, keep a report
that holds only the rows that its templates require; which optional rows
take the whole tree out under each option set; the action that each value
of a kept tree takes; what is written; and which attributes of a report's
header sequester it whatever the option does. The reports are synthetic,
built from the templates of PS3.16 2026d by
:mod:`._synthetic_dose_reports`.

A preset with the option added is composed by adding it to the preset's
options for the test alone, since no preset selects it, and ``tps-import``'s
options cannot be composed as a custom set.
"""

import io
import types

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import content_items, policy, run, scope
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_dose_reports as reports
from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
CSC_CODE = "113104"
CONTENT = "(0040,A730)"
VERIFYING_OBSERVER = "(0040,A073)"
REFERENCED_REQUEST = "(0040,A370)"
REQUESTED_PROCEDURE_ID = "(0040,1001)"
X_RAY = "x-ray"
RADIOPHARMACEUTICAL = "radiopharmaceutical"
REPORTS = {
    X_RAY: (reports.x_ray_dose_report, reports.X_RAY_IOD),
    RADIOPHARMACEUTICAL: (
        reports.radiopharmaceutical_dose_report,
        reports.RADIOPHARMACEUTICAL_IOD,
    ),
}
OPTIONAL_ROWS = {
    X_RAY: reports.X_RAY_OPTIONAL_ROWS,
    RADIOPHARMACEUTICAL: reports.RADIOPHARMACEUTICAL_OPTIONAL_ROWS,
}
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
# The value attributes of content items (PS3.3 Table 10-2).
VALUE_TAGS = frozenset(content_items.VALUE_ATTRIBUTES.values())
SOURCE_VALUES = (
    reports.SENTINEL,
    reports.STUDY,
    reports.X_RAY_SERIES,
    reports.X_RAY_REPORT,
    reports.RADIOPHARMACEUTICAL_SERIES,
    reports.RADIOPHARMACEUTICAL_REPORT,
    *reports.UIDS,
    *reports.DATES,
)


@pytest.fixture(name="with_option")
def _with_option(monkeypatch):
    """Return a function that composes a preset's policy with the option added."""
    presets = dict(policy.PRESETS)

    def compose(preset):
        monkeypatch.setattr(
            policy,
            "PRESETS",
            types.MappingProxyType({**presets, preset: (*presets[preset], CSC)}),
        )
        return policy.compose_policy(preset)

    return compose


def _report(name, optional=(), verified=False):
    build, iod = REPORTS[name]
    return build(optional, verified=verified), iod


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


def _int(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _item(dataset, items):
    for tag, index in items:
        dataset = dataset[_int(tag)].value[index]
    return dataset


def _values_by_concept(dataset, actions):
    """Return the action of each content item's value, by its concept's meaning.

    Each meaning is given once with the set of the actions that its values
    take, since a concept can name several items.
    """
    found = {}
    for path, action in actions.items():
        if path.tag in VALUE_TAGS:
            item = _item(dataset, path.items)
            meaning = item.ConceptNameCodeSequence[0].CodeMeaning
            found.setdefault(meaning, set()).add(action)
    return {meaning: "/".join(sorted(taken)) for meaning, taken in found.items()}


def _concepts(dataset):
    """Yield each content item of a tree, the root first, and its concept's key."""
    code = dataset.ConceptNameCodeSequence[0]
    value_type = "NUM" if dataset.ValueType == "NUMERIC" else dataset.ValueType
    yield (
        code.CodeMeaning,
        (code.CodingSchemeDesignator, code.CodeValue, value_type),
    )
    for child in dataset.get("ContentSequence", []):
        yield from _concepts(child)


def _transform(composed):
    return InstanceTransform(
        composed,
        KEY,
        cleaning=DescriptorCleaning(None, ReviewedNames.empty()),
        unvalidated_policy=True,
    )


def _written(composed, dataset):
    data = synthetic.written(dataset)
    record = InstanceRecord.from_file(data)
    transform = _transform(composed)
    # Under tps-import, the subject's synthetic birth date is chosen first.
    transform.prepare({0: record}, [data].__getitem__)
    result = transform(data, record)
    assert isinstance(result, run.Transformed), result
    return result.data


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_the_reports_are_of_supported_iods():
    for name, (build, iod) in REPORTS.items():
        dataset = build()
        classification = scope.classify(
            dataset.SOPClassUID, synthetic.EXPLICIT_VR_LITTLE_ENDIAN
        )

        assert classification == scope.Classification(
            scope.Disposition.SUPPORTED, iod
        ), name
        assert load_iod_tables().iods[iod].lookup(CONTENT, ()), name


@pytest.mark.parametrize("name", REPORTS)
def test_without_the_option_a_report_is_sequestered(name):
    dataset, iod = _report(name)

    _, plan = _planned(dataset, iod, policy.compose_policy("basic"))

    # Table E.1-1 gives Content Sequence D, and a sequence has no dummy
    # value (D-021).
    assert [s.path for s in plan.sequestrations] == [ElementPath((), CONTENT)]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "preset, x_ray, radiopharmaceutical",
    [
        ("basic", False, False),
        ("basic-clean-descriptors", False, False),
        ("tps-import", True, True),
        ("public-release", False, True),
    ],
)
def test_which_presets_with_the_option_keep_a_report_of_required_rows(
    with_option, preset, x_ray, radiopharmaceutical
):
    composed = with_option(preset)

    for name, kept in ((X_RAY, x_ray), (RADIOPHARMACEUTICAL, radiopharmaceutical)):
        dataset, iod = _report(name)
        _, plan = _planned(dataset, iod, composed)
        assert _kept(dataset, iod, composed) is kept, name
        assert bool(plan.sequestrations) is not kept, name
        # A report with every optional row is never kept.
        everything, _ = _report(name, OPTIONAL_ROWS[name])
        assert not _kept(everything, iod, composed), name


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "options, x_ray, radiopharmaceutical",
    [
        ((), False, False),
        ((policy.SAFE_PRIVATE,), False, False),
        ((policy.UIDS,), False, False),
        ((policy.DEVICE_IDENTITY,), False, False),
        ((policy.INSTITUTION_IDENTITY,), False, False),
        ((policy.PATIENT_CHARACTERISTICS,), False, False),
        ((policy.FULL_DATES,), False, True),
        ((policy.MODIFIED_DATES,), False, True),
        ((policy.CLEAN_DESCRIPTORS,), False, False),
        ((policy.FULL_DATES, policy.DEVICE_IDENTITY), True, True),
        ((policy.MODIFIED_DATES, policy.UIDS), True, True),
    ],
)
def test_which_retain_options_with_the_option_keep_a_report_of_required_rows(
    options, x_ray, radiopharmaceutical
):
    composed = policy.compose_custom_policy((CSC, *options))

    for name, kept in ((X_RAY, x_ray), (RADIOPHARMACEUTICAL, radiopharmaceutical)):
        dataset, iod = _report(name)
        assert _kept(dataset, iod, composed) is kept, name


# A report made by a modality is observed by a device (TID 1004): its Device
# Observer UID (row 1) is X/D, and its Name (row 2) and Serial Number (row 5)
# are X unless Retain Device Identity is selected. The X-ray report's required
# rows hold one; a radiopharmaceutical report holds one only through the dose
# calibrator (TID 10022 rows 13 and 15).
DEVICE_OBSERVERS = {
    "x-ray, UID": (X_RAY, ()),
    "x-ray, UID, name, and serial number": (
        X_RAY,
        ("TID 1004 row 2", "TID 1004 row 5"),
    ),
    "radiopharmaceutical, UID": (RADIOPHARMACEUTICAL, ("TID 10022 row 13",)),
    "radiopharmaceutical, UID, name, and serial number": (
        RADIOPHARMACEUTICAL,
        (
            "TID 10022 row 13",
            "TID 10022 row 15 TID 1004 row 2",
            "TID 10022 row 15 TID 1004 row 5",
        ),
    ),
}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "options, kept",
    [
        # Without a dates option the required start datetimes take the tree
        # out, whatever is retained.
        ((), set()),
        ((policy.UIDS,), set()),
        ((policy.DEVICE_IDENTITY,), set()),
        ((policy.FULL_DATES,), set()),
        ((policy.MODIFIED_DATES,), set()),
        # Retain UIDs keeps the UID but not the name or serial number.
        (
            (policy.MODIFIED_DATES, policy.UIDS),
            {"x-ray, UID", "radiopharmaceutical, UID"},
        ),
        ((policy.FULL_DATES, policy.UIDS), {"x-ray, UID", "radiopharmaceutical, UID"}),
        ((policy.FULL_DATES, policy.DEVICE_IDENTITY), set(DEVICE_OBSERVERS)),
    ],
)
def test_which_retain_options_keep_a_report_observed_by_a_device(options, kept):
    composed = policy.compose_custom_policy((CSC, *options))

    assert {
        case
        for case, (name, optional) in DEVICE_OBSERVERS.items()
        if _kept(*_report(name, optional), composed)
    } == kept


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "preset, kept", [("public-release", set()), ("tps-import", set(DEVICE_OBSERVERS))]
)
def test_which_presets_keep_a_report_observed_by_a_device(with_option, preset, kept):
    composed = with_option(preset)

    assert {
        case
        for case, (name, optional) in DEVICE_OBSERVERS.items()
        if _kept(*_report(name, optional), composed)
    } == kept


@pytest.mark.parametrize(
    "preset, name, removed",
    [
        # TID 1004 row 1 and TID 10003 row 6, both M, are X/D, which the
        # engine resolves to X, since it checks no template.
        ("basic", X_RAY, {"Device Observer UID", "DateTime Started"}),
        ("basic-clean-descriptors", X_RAY, {"Device Observer UID", "DateTime Started"}),
        ("tps-import", X_RAY, set()),
        ("public-release", X_RAY, {"Device Observer UID"}),
        # TID 10022 row 9, M, is X/D.
        ("basic", RADIOPHARMACEUTICAL, {"Radiopharmaceutical Start DateTime"}),
        (
            "basic-clean-descriptors",
            RADIOPHARMACEUTICAL,
            {"Radiopharmaceutical Start DateTime"},
        ),
        ("tps-import", RADIOPHARMACEUTICAL, set()),
        ("public-release", RADIOPHARMACEUTICAL, set()),
    ],
)
def test_the_required_rows_that_table_e3_4_1_removes(
    with_option, preset, name, removed
):
    composed = with_option(preset)
    dataset, _ = _report(name)
    actions = content_items.concept_actions(composed.options)

    assert {
        meaning
        for meaning, key in _concepts(dataset)
        if actions.get(key) == content_items.REMOVE
    } == removed


# Under every option set, these optional rows take the tree out: Table
# E.3.4-1 gives each X under every option, or X with C under Clean
# Descriptors, which falls back to X (D-009), or its concept name is coded in
# LOINC, whose rows the generated table leaves out (D-001).
X_RAY_REMOVED_UNDER_EVERY_OPTION = {
    "TID 10002 row 9",  # Calibration Protocol
    "TID 10003 row 4",  # Irradiation Event Label
    "TID 10003 row 8",  # Acquisition Protocol
    "TID 10003 row 25",  # Comment
    "TID 10003 row 26 TID 1020 row 3",  # Person ID
    "TID 10001 row 15",  # Comment
}
RADIOPHARMACEUTICAL_REMOVED_UNDER_EVERY_OPTION = {
    "TID 10022 row 23 TID 1020 row 3",  # Person ID
    "TID 10022 row 27",  # Radiopharmaceutical Dispense Unit Identifier
    "TID 10022 row 28",  # Radiopharmaceutical Lot Identifier
    "TID 10022 row 31",  # Prescription Identifier
    "TID 10022 row 32",  # Comment
    "TID 10024 row 6",  # Patient Weight, coded in LOINC
    "TID 10024 row 14",  # Recent Physical Activity
    "TID 10021 row 6",  # Comment
}
# Retain Institution Identity keeps these.
X_RAY_INSTITUTION = {
    "TID 1004 row 6",  # Device Observer Physical Location During Observation
    "TID 1003 row 2",  # Person Observer's Organization Name
    "TID 10003 row 26 TID 1020 row 5",  # Organization Name
}
RADIOPHARMACEUTICAL_INSTITUTION = {"TID 10022 row 23 TID 1020 row 5"}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "name, preset, options, removed",
    [
        (
            X_RAY,
            "tps-import",
            None,
            X_RAY_REMOVED_UNDER_EVERY_OPTION | X_RAY_INSTITUTION,
        ),
        (
            X_RAY,
            None,
            (CSC, policy.UIDS, policy.MODIFIED_DATES),
            X_RAY_REMOVED_UNDER_EVERY_OPTION
            | X_RAY_INSTITUTION
            | {
                # Retain Device Identity keeps these.
                "TID 1004 row 2",  # Device Observer Name
                "TID 1004 row 5",  # Device Observer Serial Number
                "TID 10002 row 14",  # Device Name and Device Serial Number
            },
        ),
        (X_RAY, None, EVERY_OPTION, X_RAY_REMOVED_UNDER_EVERY_OPTION),
        (
            RADIOPHARMACEUTICAL,
            "public-release",
            None,
            RADIOPHARMACEUTICAL_REMOVED_UNDER_EVERY_OPTION
            | RADIOPHARMACEUTICAL_INSTITUTION
            | {
                # Retain UIDs or Retain Device Identity keeps the dose
                # calibrator's Device Observer UID, and Retain Device
                # Identity its name and serial number.
                "TID 10022 row 13",
                "TID 10022 row 15 TID 1004 row 2",
                "TID 10022 row 15 TID 1004 row 5",
                # Retain Patient Characteristics keeps these.
                "TID 10024 row 3",  # Subject Age
                "TID 10024 row 4",  # Subject Sex
            },
        ),
        (
            RADIOPHARMACEUTICAL,
            "tps-import",
            None,
            RADIOPHARMACEUTICAL_REMOVED_UNDER_EVERY_OPTION
            | RADIOPHARMACEUTICAL_INSTITUTION,
        ),
        (
            RADIOPHARMACEUTICAL,
            None,
            EVERY_OPTION,
            RADIOPHARMACEUTICAL_REMOVED_UNDER_EVERY_OPTION,
        ),
    ],
)
def test_the_optional_rows_that_take_the_tree_out(
    with_option, name, preset, options, removed
):
    composed = (
        with_option(preset)
        if options is None
        else policy.compose_custom_policy(options)
    )
    build, iod = REPORTS[name]

    assert _kept(build(()), iod, composed)
    assert {
        key
        for key in OPTIONAL_ROWS[name]
        if not _kept(build(reports.with_holders(key)), iod, composed)
    } == removed


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_kept_x_ray_tree_gives_each_listed_value_its_action():
    kept = set(reports.X_RAY_OPTIONAL_ROWS) - X_RAY_REMOVED_UNDER_EVERY_OPTION
    dataset = reports.x_ray_dose_report(kept)

    actions, plan = _planned(
        dataset, reports.X_RAY_IOD, policy.compose_custom_policy(EVERY_OPTION)
    )

    assert not plan.sequestrations
    assert _values_by_concept(dataset, actions) == {
        "Device Observer UID": "K",
        "Device Observer Name": "K",
        "Device Observer Serial Number": "K",
        "Device Observer Physical Location During Observation": "K",
        "Person Observer Name": "D",
        "Person Observer's Organization Name": "K",
        "Study Instance UID": "K",
        "Calibration DateTime": "K",
        # D, with C under Clean Descriptors, which falls back to D.
        "Calibration Responsible Party": "D",
        "Device Name": "K",
        "Device Serial Number": "K",
        "Irradiation Event UID": "K",
        "DateTime Started": "K",
        "Person Name": "D",
        "Organization Name": "K",
    }
    # Device Observer Manufacturer and Model Name, and Device Manufacturer
    # and Model Name, are not listed, so their values take their own rules.


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize(
    "name, preset, values",
    [
        (
            X_RAY,
            "tps-import",
            {
                "Device Observer UID": "K",
                "Study Instance UID": "D",
                "Irradiation Event UID": "D",
                "DateTime Started": "C",
            },
        ),
        (
            RADIOPHARMACEUTICAL,
            "tps-import",
            {
                "Radiopharmaceutical Administration Event UID": "D",
                "Radiopharmaceutical Start DateTime": "C",
                "Person Name": "D",
            },
        ),
        (
            RADIOPHARMACEUTICAL,
            "public-release",
            {
                "Radiopharmaceutical Administration Event UID": "D",
                "Radiopharmaceutical Start DateTime": "C",
                "Person Name": "D",
            },
        ),
    ],
)
def test_a_kept_tree_of_required_rows_gives_each_listed_value_its_action(
    with_option, name, preset, values
):
    dataset, iod = _report(name)

    actions, _ = _planned(dataset, iod, with_option(preset))

    assert _values_by_concept(dataset, actions) == values


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_written_radiopharmaceutical_report_holds_no_source_value(with_option):
    dataset, _ = _report(RADIOPHARMACEUTICAL)

    data = _written(with_option("public-release"), dataset)

    for value in SOURCE_VALUES:
        assert value.encode() not in data, value
    written = pydicom.dcmread(io.BytesIO(data))
    assert [meaning for meaning, _ in _concepts(written)] == [
        meaning for meaning, _ in _concepts(dataset)
    ]
    assert CSC_CODE in [
        code.get("CodeValue") for code in written.DeidentificationMethodCodeSequence
    ]
    (administration,) = (
        item for item in written.ContentSequence if item.ValueType == "CONTAINER"
    )
    by_meaning = {
        item.ConceptNameCodeSequence[0].CodeMeaning: item
        for item in administration.ContentSequence
    }
    # Modified Dates shifts the administration as it shifts the study, both
    # on the same day in the source.
    started = by_meaning["Radiopharmaceutical Start DateTime"].DateTime
    assert started[:8] == written.StudyDate
    assert started[8:] == reports.ADMINISTRATION_START[8:]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
def test_a_written_x_ray_report_keeps_the_references_between_its_uids(with_option):
    dataset, _ = _report(X_RAY)

    written = pydicom.dcmread(io.BytesIO(_written(with_option("tps-import"), dataset)))

    assert [meaning for meaning, _ in _concepts(written)] == [
        meaning for meaning, _ in _concepts(dataset)
    ]
    items = {}

    def collect(item):
        for child in item.get("ContentSequence", []):
            items[child.ConceptNameCodeSequence[0].CodeMeaning] = child
            collect(child)

    collect(written)
    # Retain Device Identity keeps the Device Observer UID.
    assert items["Device Observer UID"].UID == reports.DEVICE_OBSERVER_UID
    # D replaces a UID as the header's U does, so the scope still names the
    # study.
    assert items["Study Instance UID"].UID == written.StudyInstanceUID != reports.STUDY
    assert items["Irradiation Event UID"].UID != reports.IRRADIATION_EVENT_UID
    started = items["DateTime Started"].DateTime
    assert started[:8] == written.StudyDate != reports.STUDY_DATE


@pytest.mark.parametrize(
    "preset", ["basic", "basic-clean-descriptors", "tps-import", "public-release"]
)
@pytest.mark.parametrize("name", REPORTS)
def test_a_verified_report_is_sequestered_by_its_verifying_observer(
    with_option, preset, name
):
    dataset, iod = _report(name, verified=True)

    _, plan = _planned(dataset, iod, with_option(preset))

    # Table E.1-1 gives Verifying Observer Sequence D under every option,
    # and it is Type 1C, required where the report is VERIFIED; a sequence
    # has no dummy value (D-021).
    assert ElementPath((), VERIFYING_OBSERVER) in [s.path for s in plan.sequestrations]
    unverified, _ = _report(name)
    _, plan = _planned(unverified, iod, with_option(preset))
    assert ElementPath((), VERIFYING_OBSERVER) not in [
        s.path for s in plan.sequestrations
    ]


@pytest.mark.parametrize(
    "preset", ["basic", "basic-clean-descriptors", "tps-import", "public-release"]
)
@pytest.mark.parametrize("name", REPORTS)
def test_a_report_made_for_a_request_is_sequestered_by_its_procedure_id(
    with_option, preset, name
):
    dataset, iod = _report(name)
    request = pydicom.Dataset()
    request.StudyInstanceUID = reports.STUDY
    request.ReferencedStudySequence = []
    request.AccessionNumber = ""
    request.PlacerOrderNumberImagingServiceRequest = ""
    request.FillerOrderNumberImagingServiceRequest = ""
    request.RequestedProcedureID = "REQUESTED-PROCEDURE"
    request.RequestedProcedureDescription = ""
    request.RequestedProcedureCodeSequence = []
    dataset.ReferencedRequestSequence = [request]
    procedure_id = ElementPath(((REFERENCED_REQUEST, 0),), REQUESTED_PROCEDURE_ID)

    _, plan = _planned(dataset, iod, with_option(preset))

    # Table E.1-1 gives Requested Procedure ID a plain X, and the IODs
    # require it (Type 2) in Referenced Request Sequence, which is Type 1C,
    # required where the report was made for a request, and no Type 3
    # sequence encloses it, so removing it would make the instance
    # nonconformant (D-020), even where the option keeps the tree.
    assert procedure_id in [s.path for s in plan.sequestrations]
    del request.RequestedProcedureID
    _, plan = _planned(dataset, iod, with_option(preset))
    assert all(
        s.path.items[:1] != ((REFERENCED_REQUEST, 0),) for s in plan.sequestrations
    )
