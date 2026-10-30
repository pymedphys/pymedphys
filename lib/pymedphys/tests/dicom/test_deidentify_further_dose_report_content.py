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

"""The Clean Structured Content Option on CT, Enhanced X-Ray, and Patient dose reports.

The X-Ray Radiation Dose SR IOD, whose root may be TID 10011, is supported,
but the Enhanced X-Ray and Patient Radiation Dose SR IODs are not yet, so
the engine sequesters their instances. These tests show what the option
does with the content trees of a CT Radiation Dose report (TID 10011, with
TID 10015), an Enhanced X-Ray Radiation Dose report (TID 10040), and a
Patient Radiation Dose report (TID 10030), as
:mod:`.test_deidentify_dose_report_content` does for TID 10001 and TID
10021 (D-047): which option sets, chiefly the option alone, with Retain
UIDs, and with Retain Device Identity, and which presets, with the option
added, keep a report that holds only the rows that its templates require;
the action that its required rows take; which optional rows take the tree
out under each option set; the action that each value of a kept tree takes;
and what is written and released, in the tests that add the two IODs to
the supported ones for that test alone, as supporting them would. The
reports are synthetic, built from the templates of PS3.16 2026d by
:mod:`._synthetic_further_dose_reports`.

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
from pymedphys._dicom.deidentify.release_gate import ReasonCode
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_further_dose_reports as reports
from . import _synthetic_references as synthetic
from . import _synthetic_structured_reports as general

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
CSC_CODE = "113104"
CONTENT = "(0040,A730)"
VERIFYING_OBSERVER = "(0040,A073)"
MANUFACTURER = "(0008,0070)"
MODEL_NAME = "(0008,1090)"
TEXT_VALUE = "(0040,A160)"
CT = "CT"
ENHANCED = "enhanced X-ray"
PATIENT = "patient"
REPORTS = {
    CT: (reports.ct_dose_report, reports.X_RAY_IOD),
    ENHANCED: (reports.enhanced_dose_report, reports.ENHANCED_IOD),
    PATIENT: (reports.patient_dose_report, reports.PATIENT_IOD),
}
OPTIONAL_ROWS = {
    CT: reports.CT_OPTIONAL_ROWS,
    ENHANCED: reports.ENHANCED_OPTIONAL_ROWS,
    PATIENT: reports.PATIENT_OPTIONAL_ROWS,
}
PRESETS = ("basic", "basic-clean-descriptors", "tps-import", "public-release")
UIDS = (CSC, policy.UIDS)
DEVICE = (CSC, policy.DEVICE_IDENTITY)
# Retain Device Identity conflicts with Modified Dates.
DATED_UIDS = (CSC, policy.FULL_DATES, policy.UIDS)
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
# The device observer's Manufacturer and Model Name (TID 1004 rows 3 and 4),
# which default to the header's.
DEVICE_OBSERVER_MAKE = ("TID 1004 row 3", "TID 1004 row 4")
# The irradiating device (TID 1021), whose Manufacturer and Model Name (rows
# 3 and 4), required, are the header's here.
IRRADIATING_DEVICES = {
    "TID 10012 row 13",
    "TID 10013 row 39",
    "TID 10041 row 10",
    "TID 10042 row 47",
}


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


@pytest.fixture(name="supported")
def _supported(monkeypatch):
    """Add the two unsupported IODs to the supported ones, as supporting them would."""
    monkeypatch.setattr(
        scope,
        "SUPPORTED_IODS",
        scope.SUPPORTED_IODS | {reports.ENHANCED_IOD, reports.PATIENT_IOD},
    )


def _report(name, optional=(), **kwargs):
    build, iod = REPORTS[name]
    return build(optional, **kwargs), iod


def _planned(dataset, iod, composed):
    """Return the content items' actions and the instance's plan."""
    source = read_source(synthetic.written(dataset))
    iod_ = load_iod_tables().iods[iod]
    actions = content_items.content_item_actions(source, composed, iod_)
    return actions, plan_instance(source, ElementRules(composed), iod_, actions)


def _kept(dataset, iod, composed):
    """Return whether the option keeps the report's content tree.

    Only the content items' actions are found, without the plan, which the
    tests that need it find with :func:`_planned`.
    """
    source = read_source(synthetic.written(dataset))
    actions = content_items.content_item_actions(
        source, composed, load_iod_tables().iods[iod]
    )
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
    """Yield each named content item of a tree, the root first, with its key."""
    if "ConceptNameCodeSequence" in dataset:
        code = dataset.ConceptNameCodeSequence[0]
        yield (
            code.CodeMeaning,
            (code.CodingSchemeDesignator, code.CodeValue, dataset.ValueType),
        )
    for child in dataset.get("ContentSequence", []):
        yield from _concepts(child)


def _items(dataset):
    """Yield each content item of a tree below the root, depth first."""
    for child in dataset.get("ContentSequence", []):
        yield child
        yield from _items(child)


def _shape(dataset):
    """Return the tree's Value Types and concept names, depth first."""
    found = [(dataset.get("ValueType"), tuple(_concepts(dataset))[:1])]
    for child in dataset.get("ContentSequence", []):
        found.extend(_shape(child))
    return found


def _released(composed, dataset):
    """Return the written file and the release gate's decision on it."""
    data = synthetic.written(dataset)
    record = InstanceRecord.from_file(data)
    cleaning = (
        DescriptorCleaning(None, ReviewedNames.empty())
        if policy.CLEAN_DESCRIPTORS in composed.options
        else None
    )
    transform = InstanceTransform(
        composed, KEY, cleaning=cleaning, unvalidated_policy=True
    )
    # Under tps-import, the subject's synthetic birth date is chosen first.
    transform.prepare({0: record}, [data].__getitem__)
    result = transform(data, record)
    assert isinstance(result, run.Transformed), result
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    return result.data, decision


def test_only_the_ct_report_is_of_a_supported_iod():
    for name, (build, iod) in REPORTS.items():
        dataset = build()
        classification = scope.classify(
            dataset.SOPClassUID, synthetic.EXPLICIT_VR_LITTLE_ENDIAN
        )

        if name == CT:
            assert classification == scope.Classification(
                scope.Disposition.SUPPORTED, iod
            ), name
        else:
            assert classification.reason == scope.UnsupportedIod(iod), name
        assert load_iod_tables().iods[iod].lookup(CONTENT, ()), name
        assert load_iod_tables().iods[iod].lookup(VERIFYING_OBSERVER, ()), name


@pytest.mark.parametrize("name", REPORTS)
def test_without_the_option_a_report_is_sequestered(name):
    dataset, iod = _report(name)

    _, plan = _planned(dataset, iod, policy.compose_policy("basic"))

    # Table E.1-1 gives Content Sequence D, and a sequence has no dummy
    # value (D-021).
    assert [s.path for s in plan.sequestrations] == [ElementPath((), CONTENT)]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("options", [
    (),
    (policy.SAFE_PRIVATE,),
    (policy.INSTITUTION_IDENTITY,),
    (policy.PATIENT_CHARACTERISTICS,),
    (policy.CLEAN_DESCRIPTORS,),
    (policy.FULL_DATES,),
    (policy.MODIFIED_DATES,),
    (policy.UIDS,),
    (policy.DEVICE_IDENTITY,),
    (policy.FULL_DATES, policy.UIDS),
    (policy.MODIFIED_DATES, policy.UIDS),
    (policy.FULL_DATES, policy.DEVICE_IDENTITY),
])  # fmt: skip
def test_every_option_set_keeps_a_report_of_required_rows(options):
    composed = policy.compose_custom_policy((CSC, *options))

    # Each report is observed by the device that recorded it, whose Device
    # Observer UID (TID 1004 row 1, M) is X/D, as are the Enhanced X-Ray
    # report's DateTime Started (TID 10042 row 3 and TID 10043 row 2) and
    # RDSR Frame of Reference UID (TID 10043 row 4); X/D gives D, and so does
    # the X of its DateTime Ended (TID 10042 row 4 and TID 10043 row 3), so
    # none of them takes the tree out (D-047).
    for name in REPORTS:
        assert _kept(*_report(name), composed), name


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset", PRESETS)
def test_every_preset_with_the_option_keeps_a_report_of_required_rows(
    with_option, preset
):
    composed = with_option(preset)

    for name in REPORTS:
        dataset, iod = _report(name)
        _, plan = _planned(dataset, iod, composed)
        assert _kept(dataset, iod, composed), name
        assert not plan.sequestrations, name
        # A report with every optional row is never kept.
        everything, _ = _report(name, OPTIONAL_ROWS[name])
        assert not _kept(everything, iod, composed), name


# The required rows that Table E.3.4-1 gives X/D, or, for DateTime Ended, X.
REQUIRED_X_D = {
    "Device Observer UID",
    "DateTime Started",
    "DateTime Ended",
    "Frame of Reference UID",
}


@pytest.mark.parametrize("preset, options, taken", [
    (
        None,
        (CSC,),
        {
            CT: {"Device Observer UID": "D"},
            ENHANCED: {
                "Device Observer UID": "D",
                "DateTime Started": "D",
                "DateTime Ended": "D",
                "Frame of Reference UID": "D",
            },
            PATIENT: {"Device Observer UID": "D"},
        },
    ),
    (
        None,
        UIDS,
        {
            CT: {"Device Observer UID": "K"},
            ENHANCED: {
                "Device Observer UID": "K",
                "DateTime Started": "D",
                "DateTime Ended": "D",
                "Frame of Reference UID": "K",
            },
            PATIENT: {"Device Observer UID": "K"},
        },
    ),
    (
        None,
        DEVICE,
        {
            CT: {"Device Observer UID": "K"},
            ENHANCED: {
                "Device Observer UID": "K",
                "DateTime Started": "D",
                "DateTime Ended": "D",
                "Frame of Reference UID": "D",
            },
            PATIENT: {"Device Observer UID": "K"},
        },
    ),
    (
        "tps-import",
        None,
        {
            CT: {"Device Observer UID": "K"},
            ENHANCED: {
                "Device Observer UID": "K",
                "DateTime Started": "C",
                "DateTime Ended": "C",
                "Frame of Reference UID": "D",
            },
            PATIENT: {"Device Observer UID": "K"},
        },
    ),
    (
        "public-release",
        None,
        {
            CT: {"Device Observer UID": "D"},
            ENHANCED: {
                "Device Observer UID": "D",
                "DateTime Started": "C",
                "DateTime Ended": "C",
                "Frame of Reference UID": "D",
            },
            PATIENT: {"Device Observer UID": "D"},
        },
    ),
])  # fmt: skip
def test_the_action_that_the_required_x_d_rows_take(
    with_option, preset, options, taken
):
    actions = content_items.concept_actions(
        _composed(with_option, preset, options).options
    )

    for name in REPORTS:
        dataset, _ = _report(name)
        found = {meaning: actions.get(key) for meaning, key in _concepts(dataset)}
        assert content_items.REMOVE not in found.values(), name
        # A UIDREF item's D is a replacement UID (U) in the plan, as the
        # next tests show.
        assert {
            meaning: action
            for meaning, action in found.items()
            if meaning in REQUIRED_X_D
        } == taken[name], name


# Under every option set, these optional rows take the tree out: Table
# E.3.4-1 gives each X under every option, or X with C under Clean
# Descriptors, which falls back to X (D-009).
CT_REMOVED_UNDER_EVERY_OPTION = {
    "TID 10012 row 12",  # Comment
    "TID 10013 row 2",  # Acquisition Protocol
    "TID 10013 row 6b",  # Irradiation Event Label
    "TID 10015 row 8",  # Reason for Proceeding
    "TID 10015 row 17",  # Reason for Proceeding
    "TID 10013 row 37",  # Comment
    "TID 10013 row 38 TID 1020 row 3",  # Person ID
    "TID 10011 row 11",  # Comment
}
ENHANCED_REMOVED_UNDER_EVERY_OPTION = {
    "TID 10041 row 9",  # Calibration Protocol
    "TID 10041 row 28",  # Comment
    "TID 10042 row 6",  # Irradiation Event Label
    "TID 10042 row 45",  # Comment
    "TID 10042 row 46 TID 1020 row 3",  # Person ID
    "TID 10043 row 6",  # RDSR Frame of Reference Description
    "TID 10040 row 10",  # Comment
}
PATIENT_REMOVED_UNDER_EVERY_OPTION = {
    "TID 10031 row 3",  # Comment
    "TID 10033 row 11",  # Patient Radiation Dose Model Reference
    "TID 10033 row 12",  # Comment
    "TID 10032 row 7",  # Comment
    "TID 10031 row 9",  # Comment
    "TID 10030 row 5",  # Comment
}
# Retain Institution Identity keeps these.
CT_INSTITUTION = {
    "TID 1004 row 6",  # Device Observer Physical Location During Observation
    "TID 10013 row 38 TID 1020 row 5",  # Organization Name
}
ENHANCED_INSTITUTION = {"TID 1004 row 6", "TID 10042 row 46 TID 1020 row 5"}
PATIENT_INSTITUTION = {"TID 1004 row 6"}
# Retain Device Identity keeps the Device Observer Name and Serial Number,
# and the irradiating device's Device Name and Serial Number, X and X/D.
CT_DEVICE = {"TID 1004 row 2", "TID 1004 row 5", "TID 10012 row 13", "TID 10013 row 39"}
ENHANCED_DEVICE = {
    "TID 1004 row 2",
    "TID 1004 row 5",
    "TID 10041 row 10",
    "TID 10042 row 47",
}
PATIENT_DEVICE = {"TID 1004 row 2", "TID 1004 row 5"}
# Retain UIDs keeps these, X: the Spatial Fiducials and the model's data
# that the patient's estimate used. The CT scan's Frame of Reference UID
# (TID 10014 row 8) and the CT event's DateTime Started (TID 10013 row 6f),
# X/D, take D under every option set.
PATIENT_UIDS = {"TID 10033 row 3", "TID 10033 row 10"}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("name, preset, options, removed", [
    (
        CT,
        None,
        (CSC,),
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION | CT_DEVICE,
    ),
    (CT, None, UIDS, CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION | CT_DEVICE),
    (CT, None, DEVICE, CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION),
    (CT, "tps-import", None, CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION),
    (
        CT,
        "public-release",
        None,
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION | CT_DEVICE,
    ),
    (CT, None, EVERY_OPTION, CT_REMOVED_UNDER_EVERY_OPTION),
    (
        ENHANCED,
        None,
        (CSC,),
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION | ENHANCED_DEVICE,
    ),
    (
        ENHANCED,
        None,
        UIDS,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION | ENHANCED_DEVICE,
    ),
    (
        ENHANCED,
        None,
        DEVICE,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION,
    ),
    (
        ENHANCED,
        "tps-import",
        None,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION,
    ),
    (ENHANCED, None, EVERY_OPTION, ENHANCED_REMOVED_UNDER_EVERY_OPTION),
    (
        PATIENT,
        None,
        (CSC,),
        PATIENT_REMOVED_UNDER_EVERY_OPTION
        | PATIENT_INSTITUTION
        | PATIENT_DEVICE
        | PATIENT_UIDS,
    ),
    (
        PATIENT,
        None,
        UIDS,
        PATIENT_REMOVED_UNDER_EVERY_OPTION | PATIENT_INSTITUTION | PATIENT_DEVICE,
    ),
    (
        PATIENT,
        None,
        DEVICE,
        PATIENT_REMOVED_UNDER_EVERY_OPTION | PATIENT_INSTITUTION | PATIENT_UIDS,
    ),
    (
        PATIENT,
        "tps-import",
        None,
        PATIENT_REMOVED_UNDER_EVERY_OPTION | PATIENT_INSTITUTION | PATIENT_UIDS,
    ),
    (PATIENT, None, EVERY_OPTION, PATIENT_REMOVED_UNDER_EVERY_OPTION),
])  # fmt: skip
def test_the_optional_rows_that_take_the_tree_out(
    with_option, name, preset, options, removed
):
    composed = _composed(with_option, preset, options)
    build, iod = REPORTS[name]

    assert _kept(build(()), iod, composed)
    assert {
        key
        for key in OPTIONAL_ROWS[name]
        if not _kept(build(reports.with_holders(key)), iod, composed)
    } == removed


def _keepable(name, removed):
    """Return the optional rows of a report other than ``removed``."""
    return tuple(key for key in OPTIONAL_ROWS[name] if key not in removed)


# A listed UIDREF item that is not kept takes U's replacement rather than
# D-021's dummy, so that it names what the rest of the output names (D-047).
@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("name, options, removed, values", [
    (
        CT,
        (CSC,),
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION | CT_DEVICE,
        {
            "Device Observer UID": "U",
            "Start of X-Ray Irradiation": "D",
            "End of X-Ray Irradiation": "D",
            "Study Instance UID": "U",
            "Patient Model": "D",
            "Irradiation Event UID": "U",
            "DateTime Started": "D",
            "Frame of Reference UID": "U",
            "Identification of the X-Ray Source": "D",
            "Person Name": "D",
        },
    ),
    (
        CT,
        UIDS,
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION | CT_DEVICE,
        {
            "Device Observer UID": "K",
            "Start of X-Ray Irradiation": "D",
            "End of X-Ray Irradiation": "D",
            "Study Instance UID": "K",
            "Patient Model": "D",
            "Irradiation Event UID": "K",
            "DateTime Started": "D",
            "Frame of Reference UID": "K",
            "Identification of the X-Ray Source": "D",
            "Person Name": "D",
        },
    ),
    (
        CT,
        DEVICE,
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION,
        {
            "Device Observer UID": "K",
            "Device Observer Name": "K",
            "Device Observer Serial Number": "K",
            "Start of X-Ray Irradiation": "D",
            "End of X-Ray Irradiation": "D",
            "Study Instance UID": "U",
            "Patient Model": "D",
            "Device Name": "K",
            "Device Serial Number": "K",
            "Irradiation Event UID": "U",
            "DateTime Started": "D",
            "Frame of Reference UID": "U",
            "Identification of the X-Ray Source": "K",
            "Person Name": "D",
        },
    ),
    (
        ENHANCED,
        UIDS,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION | ENHANCED_DEVICE,
        {
            "Device Observer UID": "K",
            "Identification of the X-Ray Source": "D",
            "Calibration DateTime": "D",
            # D, with C under Clean Descriptors, which falls back to D.
            "Calibration Responsible Party": "D",
            "Irradiation Event UID": "K",
            "DateTime Started": "D",
            "DateTime Ended": "D",
            "Frame of Reference UID": "K",
            "Person Name": "D",
        },
    ),
    (
        ENHANCED,
        DATED_UIDS,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION | ENHANCED_DEVICE,
        {
            "Device Observer UID": "K",
            "Identification of the X-Ray Source": "D",
            "Calibration DateTime": "K",
            "Calibration Responsible Party": "D",
            "Irradiation Event UID": "K",
            "DateTime Started": "K",
            "DateTime Ended": "K",
            "Frame of Reference UID": "K",
            "Person Name": "D",
        },
    ),
    (
        ENHANCED,
        DEVICE,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION,
        {
            "Device Observer UID": "K",
            "Device Observer Name": "K",
            "Device Observer Serial Number": "K",
            "Identification of the X-Ray Source": "K",
            "Calibration DateTime": "D",
            "Calibration Responsible Party": "D",
            "Device Name": "K",
            "Device Serial Number": "K",
            "Irradiation Event UID": "U",
            "DateTime Started": "D",
            "DateTime Ended": "D",
            "Frame of Reference UID": "U",
            "Person Name": "D",
        },
    ),
    (
        PATIENT,
        (CSC,),
        PATIENT_REMOVED_UNDER_EVERY_OPTION
        | PATIENT_INSTITUTION
        | PATIENT_DEVICE
        | PATIENT_UIDS,
        {
            "Device Observer UID": "U",
            "Radiation Dose Estimate Name": "D",
            "Event UID Used": "U",
        },
    ),
    (
        PATIENT,
        UIDS,
        PATIENT_REMOVED_UNDER_EVERY_OPTION | PATIENT_INSTITUTION | PATIENT_DEVICE,
        {
            "Device Observer UID": "K",
            "Radiation Dose Estimate Name": "D",
            "Event UID Used": "K",
            "Patient Radiation Dose Model Data": "K",
        },
    ),
    (
        PATIENT,
        DEVICE,
        PATIENT_REMOVED_UNDER_EVERY_OPTION | PATIENT_INSTITUTION | PATIENT_UIDS,
        {
            "Device Observer UID": "K",
            "Device Observer Name": "K",
            "Device Observer Serial Number": "K",
            "Radiation Dose Estimate Name": "D",
            "Event UID Used": "U",
        },
    ),
])  # fmt: skip
def test_a_kept_tree_gives_each_listed_value_its_action(name, options, removed, values):
    dataset, iod = _report(name, _keepable(name, removed))

    actions, plan = _planned(dataset, iod, policy.compose_custom_policy(options))

    assert not plan.sequestrations
    assert _values_by_concept(dataset, actions) == values
    # The other values are not listed, so they take their own rules: the
    # free text of the next test, and the references of COMPOSITE and IMAGE
    # items, whose UIDs are kept under Retain UIDs and replaced otherwise.


# The TEXT items of each report whose concept names Table E.3.4-1 does not
# list, so that their values take Text Value's own rule.
UNLISTED_TEXT = {
    CT: {
        "Device Observer Manufacturer",
        "Device Observer Model Name",
        "Reference Authority",
        "Device Manufacturer",
        "Device Model Name",
    },
    ENHANCED: {
        "Device Observer Manufacturer",
        "Device Observer Model Name",
        "Calibration Intended Acquisition Protocol",
        "Reference Point Definition",
        "Device Manufacturer",
        "Device Model Name",
    },
    PATIENT: {
        "Device Observer Manufacturer",
        "Device Observer Model Name",
        "Radiation Dose Estimate Method Reference",
        "Reference to Uncertainty Determination Method",
    },
}


@pytest.mark.parametrize("name", REPORTS)
def test_the_unlisted_text_of_each_report(name):
    dataset, _ = _report(name, OPTIONAL_ROWS[name])
    listed = content_items.concept_actions((CSC,))

    assert {
        meaning
        for meaning, key in _concepts(dataset)
        if key[2] == "TEXT" and key not in listed
    } == UNLISTED_TEXT[name]


# The option sets under which each report is written below, with the rows
# that take its tree out under them, and the irradiating device and the
# device observer's Manufacturer and Model Name, tested on their own.
WRITTEN = {
    "CT, option alone": (
        CT,
        (CSC,),
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION | CT_DEVICE,
    ),
    "CT, Retain UIDs": (
        CT,
        UIDS,
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION | CT_DEVICE,
    ),
    "CT, Retain Device Identity": (
        CT,
        DEVICE,
        CT_REMOVED_UNDER_EVERY_OPTION | CT_INSTITUTION,
    ),
    "enhanced X-ray, option alone": (
        ENHANCED,
        (CSC,),
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION | ENHANCED_DEVICE,
    ),
    "enhanced X-ray, Retain UIDs and Full Dates": (
        ENHANCED,
        DATED_UIDS,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION | ENHANCED_DEVICE,
    ),
    "enhanced X-ray, Retain Device Identity": (
        ENHANCED,
        DEVICE,
        ENHANCED_REMOVED_UNDER_EVERY_OPTION | ENHANCED_INSTITUTION,
    ),
    "patient, option alone": (
        PATIENT,
        (CSC,),
        PATIENT_REMOVED_UNDER_EVERY_OPTION
        | PATIENT_INSTITUTION
        | PATIENT_DEVICE
        | PATIENT_UIDS,
    ),
    "patient, Retain UIDs": (
        PATIENT,
        UIDS,
        PATIENT_REMOVED_UNDER_EVERY_OPTION | PATIENT_INSTITUTION | PATIENT_DEVICE,
    ),
    "patient, Retain Device Identity": (
        PATIENT,
        DEVICE,
        PATIENT_REMOVED_UNDER_EVERY_OPTION | PATIENT_INSTITUTION | PATIENT_UIDS,
    ),
}


def _written_rows(case):
    name, options, removed = WRITTEN[case]
    rows = _keepable(name, removed | IRRADIATING_DEVICES | set(DEVICE_OBSERVER_MAKE))
    return name, options, rows


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
@pytest.mark.parametrize("case", WRITTEN)
def test_a_written_report_is_released(case):
    name, options, rows = _written_rows(case)
    dataset, _ = _report(name, rows)

    data, decision = _released(policy.compose_custom_policy(options), dataset)

    assert isinstance(decision, run.Release), decision
    written = pydicom.dcmread(io.BytesIO(data))
    assert _shape(written) == _shape(dataset)
    assert CSC_CODE in [
        code.get("CodeValue") for code in written.DeidentificationMethodCodeSequence
    ]
    absent = [*general.NAMES, reports.PARTICIPANTS_NAME, general.PATIENT_ID]
    if policy.FULL_DATES not in options:
        absent += [*general.DATES, *reports.DATETIMES]
    for value in absent:
        assert value.encode() not in data, value
    # Text Value's own rule replaces unlisted free text with a dummy value.
    texts = {
        item.ConceptNameCodeSequence[0].CodeMeaning: item.TextValue
        for item in _items(written)
        if item.ValueType == "TEXT"
    }
    for meaning in UNLISTED_TEXT[name] & set(texts):
        assert reports.SENTINEL not in texts[meaning], meaning
    if policy.UIDS in options:
        assert reports.SENTINEL.encode() not in data
        for uid in reports.UIDS:
            if uid.encode() in synthetic.written(dataset):
                assert uid.encode() in data, uid
    else:
        # Retain Device Identity keeps the Device Observer UID, Name, and
        # Serial Number, and only them of the report's identifying values;
        # without it, none is kept.
        device = policy.DEVICE_IDENTITY in options
        kept = {
            item.ConceptNameCodeSequence[0].CodeMeaning
            for item in _items(written)
            if reports.SENTINEL in str(item.get("TextValue", ""))
        }
        assert kept == (
            {"Device Observer Name", "Device Observer Serial Number"}
            if device
            else set()
        )
        observers = {
            reports.CT_DEVICE_OBSERVER_UID,
            reports.ENHANCED_DEVICE_OBSERVER_UID,
            reports.PATIENT_DEVICE_OBSERVER_UID,
        }
        for uid in set(reports.UIDS) - (observers if device else set()):
            assert uid.encode() not in data, uid


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
@pytest.mark.parametrize("case, extra", [
    ("CT, option alone", DEVICE_OBSERVER_MAKE),
    ("CT, Retain UIDs", DEVICE_OBSERVER_MAKE),
    ("CT, Retain Device Identity", DEVICE_OBSERVER_MAKE),
    ("CT, Retain Device Identity", ("TID 10013 row 39",)),
    ("enhanced X-ray, Retain UIDs and Full Dates", DEVICE_OBSERVER_MAKE),
    ("enhanced X-ray, Retain Device Identity", ("TID 10042 row 47",)),
    ("patient, Retain UIDs", DEVICE_OBSERVER_MAKE),
    ("patient, Retain Device Identity", DEVICE_OBSERVER_MAKE),
])  # fmt: skip
def test_a_device_named_as_the_header_names_it_holds_a_report_for_review(case, extra):
    name, options, rows = _written_rows(case)
    dataset, _ = _report(name, (*rows, *extra))

    data, decision = _released(policy.compose_custom_policy(options), dataset)

    # TID 1004 rows 3 and 4 default to the header's Manufacturer and Model
    # Name, and TID 1021 requires them. Table E.3.4-1 lists neither concept,
    # so Text Value's own rule replaces each with a dummy value, and the
    # residual search finds the source text in the header, which keeps both,
    # so a reviewer is to look before the report is released.
    assert isinstance(decision, run.HoldForReview), decision
    assert {
        (reason.code, reason.path.tag, reason.location.element.tag)
        for reason in decision.reasons
    } == {
        (ReasonCode.RESIDUAL_TEXT, TEXT_VALUE, MANUFACTURER),
        (ReasonCode.RESIDUAL_TEXT, TEXT_VALUE, MODEL_NAME),
    }
    written = pydicom.dcmread(io.BytesIO(data))
    assert written.Manufacturer == dataset.Manufacturer
    assert written.ManufacturerModelName == dataset.ManufacturerModelName


@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, UIDS),
    (None, DEVICE),
])  # fmt: skip
@pytest.mark.parametrize("name", REPORTS)
def test_a_verified_report_is_planned_as_an_unverified_one_is(
    with_option, preset, options, name
):
    composed = _composed(with_option, preset, options)
    dataset, iod = _report(name, verified=True)

    _, plan = _planned(dataset, iod, composed)

    # Table E.1-1 gives Verifying Observer Sequence D under every option,
    # and it is Type 1C, required where the report is VERIFIED; D keeps each
    # verifier's item, with dummy values, so it sequesters nothing (D-021).
    (observer,) = [
        e for e in plan.elements if e.path == ElementPath((), VERIFYING_OBSERVER)
    ]
    assert observer.action == "D"
    unverified, _ = _report(name)
    _, unverified_plan = _planned(unverified, iod, composed)
    assert [s.path for s in plan.sequestrations] == [
        s.path for s in unverified_plan.sequestrations
    ]
    if _kept(unverified, iod, composed):
        assert not plan.sequestrations


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
@pytest.mark.parametrize("case", WRITTEN)
def test_a_verified_report_is_released_with_a_dummy_verifier(case):
    name, options, rows = _written_rows(case)
    dataset, _ = _report(name, rows, verified=True)

    data, decision = _released(policy.compose_custom_policy(options), dataset)

    assert isinstance(decision, run.Release), decision
    for value in (general.VERIFIERS_NAME, f"{reports.SENTINEL} HOSPITAL"):
        assert value.encode() not in data, value
    written = pydicom.dcmread(io.BytesIO(data))
    assert written.VerificationFlag == "VERIFIED"
    (verifier,) = written.VerifyingObserverSequence
    assert verifier.VerifyingObserverName == "DEIDENTIFIED"
    assert verifier.VerifyingOrganization == "DEIDENTIFIED"
    assert len(verifier.VerifyingObserverIdentificationCodeSequence) == 0
    if policy.FULL_DATES not in options:
        assert verifier.VerificationDateTime != general.VERIFICATION_DATETIME
