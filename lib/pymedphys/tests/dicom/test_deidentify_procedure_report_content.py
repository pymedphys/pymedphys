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

"""The Clean Structured Content Option on planning and procedure reports.

The Implantation Plan SR Document, Simplified Adult Echo SR, Planned and
Performed Imaging Agent Administration SR, and Acquisition Context SR IODs
are not supported yet, so the engine sequesters their instances. These
tests show, ahead of supporting them, what the option does with their
content trees (D-047): that every preset and Retain option, with the option
added, keeps a report that holds only the rows that its templates require;
which optional rows take the whole tree out under each option set, among
them concept names coded in a scheme that the engine cannot look up; the
action that each listed value of a kept tree takes; and what is written and
released, in the tests that add the IODs to the supported ones for that
test alone, as supporting them would. The reports are synthetic, built from
the templates of PS3.16 2026d by :mod:`._synthetic_procedure_reports`.

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
from . import _synthetic_procedure_reports as reports
from . import _synthetic_references as synthetic
from . import _synthetic_structured_reports as general

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
CSC_CODE = "113104"
CONTENT = "(0040,A730)"
VERIFYING_OBSERVER = "(0040,A073)"
TIMEZONE = "(0008,0201)"
IMPLANTATION = "implantation plan"
ECHO = "echo"
PLANNED = "planned administration"
PERFORMED = "performed administration"
ACQUISITION_CONTEXT = "acquisition context"
REPORTS = {
    IMPLANTATION: (reports.implantation_plan, reports.IMPLANTATION_PLAN_IOD),
    ECHO: (reports.echo_report, reports.SIMPLIFIED_ADULT_ECHO_IOD),
    PLANNED: (reports.planned_administration, reports.PLANNED_ADMINISTRATION_IOD),
    PERFORMED: (
        reports.performed_administration,
        reports.PERFORMED_ADMINISTRATION_IOD,
    ),
    ACQUISITION_CONTEXT: (
        reports.acquisition_context,
        reports.ACQUISITION_CONTEXT_IOD,
    ),
}
OPTIONAL_ROWS = {
    IMPLANTATION: reports.IMPLANTATION_OPTIONAL_ROWS,
    ECHO: reports.ECHO_OPTIONAL_ROWS,
    PLANNED: reports.PLANNED_OPTIONAL_ROWS,
    PERFORMED: reports.PERFORMED_OPTIONAL_ROWS,
    ACQUISITION_CONTEXT: reports.ACQUISITION_CONTEXT_OPTIONAL_ROWS,
}
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
EVERY_OPTION_SET = [
    *((preset, None) for preset in PRESETS),
    *((None, (CSC, option)) for option in EVERY_OPTION[1:]),
    (None, (CSC, policy.MODIFIED_DATES)),
    (None, EVERY_OPTION),
]
# The value attributes of content items (PS3.3 Table 10-2).
VALUE_TAGS = frozenset(content_items.VALUE_ATTRIBUTES.values())
SOURCE_VALUES = (
    general.SENTINEL,
    general.PATIENT_ID,
    *general.NAMES,
    *general.UIDS,
    *general.DATES,
    *reports.UIDS,
    *reports.DATES,
    reports.SYRINGE_UDI,
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


@pytest.fixture(name="supported")
def _supported(monkeypatch):
    """Add the five IODs to the supported ones, as supporting them would."""
    monkeypatch.setattr(
        scope,
        "SUPPORTED_IODS",
        scope.SUPPORTED_IODS | {iod for _, iod in REPORTS.values()},
    )


def _header_sequestrations(name, composed):
    """Return the header elements that sequester a report under ``composed``.

    The Simplified Adult Echo SR's Timezone Module (PS3.3 Section C.12.5)
    requires Timezone Offset From UTC, Type 1, to which Table E.1-1 gives X,
    K under Full Dates, and C under Modified Dates, and a plain X on an
    attribute that the IOD requires sequesters the instance (D-020). The
    other IODs do not require it.
    """
    dated = {policy.FULL_DATES, policy.MODIFIED_DATES} & set(composed.options)
    return [] if name != ECHO or dated else [ElementPath((), TIMEZONE)]


def _report(name, optional=(), **kwargs):
    build, iod = REPORTS[name]
    return build(optional, **kwargs), iod


def _composed(with_option, preset, options):
    return (
        with_option(preset)
        if options is None
        else policy.compose_custom_policy(options)
    )


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
    """Return the action of each content item's value, by its concept's meaning."""
    found = {}
    for path, action in actions.items():
        if path.tag in VALUE_TAGS:
            item = _item(dataset, path.items)
            meaning = item.ConceptNameCodeSequence[0].CodeMeaning
            found.setdefault(meaning, set()).add(action)
    return {meaning: "/".join(sorted(taken)) for meaning, taken in found.items()}


def _shape(dataset):
    """Return the tree's Value Types and concept names, depth first."""
    names = dataset.get("ConceptNameCodeSequence", [])
    found = [(dataset.get("ValueType"), tuple(code.CodeValue for code in names))]
    for child in dataset.get("ContentSequence", []):
        found.extend(_shape(child))
    return found


def _items(dataset):
    """Yield each item of a tree, the root first."""
    yield dataset
    for child in dataset.get("ContentSequence", []):
        yield from _items(child)


def _by_meaning(dataset, meaning):
    """Return the one item of a tree whose concept name has ``meaning``."""
    (found,) = [
        each
        for each in _items(dataset)
        if each.get("ConceptNameCodeSequence")
        and each.ConceptNameCodeSequence[0].CodeMeaning == meaning
    ]
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


def test_the_reports_are_of_iods_that_are_not_supported_yet():
    for name, (build, iod) in REPORTS.items():
        dataset = build()
        classification = scope.classify(
            dataset.SOPClassUID, synthetic.EXPLICIT_VR_LITTLE_ENDIAN
        )

        assert classification.reason == scope.UnsupportedIod(iod), name
        assert load_iod_tables().iods[iod].lookup(CONTENT, ()), name
        # Each IOD has the SR Document General Module, so each report can be
        # verified.
        assert load_iod_tables().iods[iod].lookup(VERIFYING_OBSERVER, ()), name


@pytest.mark.parametrize("name", REPORTS)
def test_without_the_option_a_report_is_sequestered(name):
    dataset, iod = _report(name)
    composed = policy.compose_policy("basic")

    _, plan = _planned(dataset, iod, composed)

    # Table E.1-1 gives Content Sequence D, and a sequence has no dummy
    # value (D-021).
    assert {s.path for s in plan.sequestrations} == {
        ElementPath((), CONTENT),
        *_header_sequestrations(name, composed),
    }


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", EVERY_OPTION_SET)
def test_every_option_set_keeps_a_report_of_required_rows(with_option, preset, options):
    composed = _composed(with_option, preset, options)

    # The required rows' listed concepts each take D or K, as the test below
    # shows, and the rest are not listed.
    for name in REPORTS:
        dataset, iod = _report(name)
        _, plan = _planned(dataset, iod, composed)
        assert _kept(dataset, iod, composed), name
        assert [s.path for s in plan.sequestrations] == _header_sequestrations(
            name, composed
        ), name


def _listed(dataset, actions):
    """Return the action of each item of a tree that Table E.3.4-1 lists."""
    found = {}
    for each in _items(dataset):
        if "ConceptNameCodeSequence" in each:
            code = each.ConceptNameCodeSequence[0]
            key = (code.CodingSchemeDesignator, code.CodeValue, each.ValueType)
            if key in actions:
                found[code.CodeMeaning, each.ValueType] = actions[key]
    return found


@pytest.mark.parametrize("preset, options", EVERY_OPTION_SET)
def test_the_required_rows_that_table_e3_4_1_lists(with_option, preset, options):
    composed = _composed(with_option, preset, options)
    actions = content_items.concept_actions(composed.options)

    # Retain UIDs keeps the frame of reference and the reference to the
    # manufacturer's template, which otherwise take D: U's replacement of
    # the UID, and the reference, whose UIDs take their own rules. Drug
    # administered (122083, DCM) is listed only as TEXT, while TID 11004 row
    # 2 gives it the Value Type CODE, so it is not listed there.
    retained = "K" if policy.UIDS in composed.options else "D"
    observer = {("Person Observer Name", "PNAME"): "D"}
    assert {name: _listed(_report(name)[0], actions) for name in REPORTS} == {
        IMPLANTATION: {
            **observer,
            ("Component ID", "TEXT"): "D",
            ("Frame of Reference UID", "UIDREF"): retained,
            ("Manufacturer Implant Template", "COMPOSITE"): retained,
        },
        ECHO: observer,
        PLANNED: observer,
        PERFORMED: observer,
        ACQUISITION_CONTEXT: observer,
    }


@pytest.mark.parametrize("preset, options, sequestered", [
    ("basic", None, True),
    ("basic-clean-descriptors", None, True),
    ("tps-import", None, False),
    ("public-release", None, False),
    (None, (CSC, policy.UIDS), True),
    (None, (CSC, policy.FULL_DATES), False),
    (None, (CSC, policy.MODIFIED_DATES), False),
])  # fmt: skip
def test_an_echo_reports_timezone_sequesters_it_without_a_dates_option(
    with_option, preset, options, sequestered
):
    dataset, iod = _report(ECHO)

    _, plan = _planned(dataset, iod, _composed(with_option, preset, options))

    # The header alone, whatever the option does with the content tree.
    assert [s.path for s in plan.sequestrations] == (
        [ElementPath((), TIMEZONE)] if sequestered else []
    )


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", EVERY_OPTION_SET)
def test_an_echo_measurement_coded_in_loinc_takes_the_tree_out(
    with_option, preset, options
):
    composed = _composed(with_option, preset, options)
    dataset, iod = _report(ECHO, measurement=reports.AORTIC_ANNULUS_DIAMETER)

    # TID 5301 row 1 takes its concept name from CID 12300, whose 196
    # measurements are coded in LOINC, and the 13 that it includes from CID
    # 12309 in DCM, so that a report of any but those 13 cannot be kept.
    assert "LN" in content_items.UNMATCHED_SCHEMES
    assert not _kept(dataset, iod, composed)


# The optional rows that take the tree out under every option set: Table
# E.3.4-1 gives each X under every option, or X with C under Clean
# Descriptors, which falls back to X (D-009), or its concept name is coded
# in a scheme whose rows the pin leaves out (D-001).
IMPLANTATION_REMOVED_UNDER_EVERY_OPTION = {"TID 7000 row 37"}  # Physician Note
# Retain UIDs keeps the references to the implant assembly, the CT image,
# the fiducials, and the registration, each X without it; the fiducial's
# intent, which the table does not list, goes with its reference.
IMPLANTATION_UIDS = {
    "TID 7000 row 7",
    "TID 7000 row 30",
    "TID 7000 row 33",
    "TID 7000 row 35",
    "TID 7000 row 40",
}
# The heading of the procedure's description, coded in LOINC.
ECHO_REMOVED_UNDER_EVERY_OPTION = {"TID 5300 row 4"}
ADMINISTRATION_REMOVED_UNDER_EVERY_OPTION = {
    "TID 1005 row 7",  # Accession Number
    "TID 11004 row 18",  # Description of Material
    "TID 11004 row 19",  # Medical Product Expiration Date, coded in NCIt
    "TID 11004 row 20",  # Manufacturer Name, coded in UMLS
    "TID 10024 row 6",  # Patient Weight, coded in LOINC
    "TID 10024 row 14",  # Recent Physical Activity
}
PLANNED_REMOVED_UNDER_EVERY_OPTION = ADMINISTRATION_REMOVED_UNDER_EVERY_OPTION | {
    "TID 11001 row 8"  # Comment
}
PERFORMED_REMOVED_UNDER_EVERY_OPTION = ADMINISTRATION_REMOVED_UNDER_EVERY_OPTION | {
    "TID 11020 row 8",  # Summary, coded in LOINC
    "TID 11020 row 13",  # Adverse Event, coded in NCIt
}
# Retain UIDs keeps Procedure Study Instance UID, and Retain Patient
# Characteristics Subject Age.
ADMINISTRATION_UIDS = {"TID 1005 row 1"}
ADMINISTRATION_PATIENT = {"TID 10024 row 3"}
ACQUISITION_CONTEXT_REMOVED_UNDER_EVERY_OPTION = {
    "TID 8101 row 5",  # Comment, in TID 8110
    "TID 8121 row 25",  # Environmental temperature, coded in NCIt
}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("name, preset, options, removed", [
    (
        IMPLANTATION,
        "public-release",
        None,
        IMPLANTATION_REMOVED_UNDER_EVERY_OPTION | IMPLANTATION_UIDS,
    ),
    (IMPLANTATION, None, (CSC, policy.UIDS), IMPLANTATION_REMOVED_UNDER_EVERY_OPTION),
    (IMPLANTATION, None, EVERY_OPTION, IMPLANTATION_REMOVED_UNDER_EVERY_OPTION),
    (ECHO, "public-release", None, ECHO_REMOVED_UNDER_EVERY_OPTION),
    (ECHO, None, EVERY_OPTION, ECHO_REMOVED_UNDER_EVERY_OPTION),
    (
        PLANNED,
        "basic",
        None,
        PLANNED_REMOVED_UNDER_EVERY_OPTION
        | ADMINISTRATION_UIDS
        | ADMINISTRATION_PATIENT,
    ),
    (
        PLANNED,
        "tps-import",
        None,
        PLANNED_REMOVED_UNDER_EVERY_OPTION | ADMINISTRATION_UIDS,
    ),
    (
        PLANNED,
        "public-release",
        None,
        PLANNED_REMOVED_UNDER_EVERY_OPTION
        | ADMINISTRATION_UIDS
        | ADMINISTRATION_PATIENT,
    ),
    (PLANNED, None, EVERY_OPTION, PLANNED_REMOVED_UNDER_EVERY_OPTION),
    (
        PERFORMED,
        "tps-import",
        None,
        PERFORMED_REMOVED_UNDER_EVERY_OPTION | ADMINISTRATION_UIDS,
    ),
    (
        PERFORMED,
        "public-release",
        None,
        PERFORMED_REMOVED_UNDER_EVERY_OPTION
        | ADMINISTRATION_UIDS
        | ADMINISTRATION_PATIENT,
    ),
    (PERFORMED, None, EVERY_OPTION, PERFORMED_REMOVED_UNDER_EVERY_OPTION),
    (
        ACQUISITION_CONTEXT,
        "public-release",
        None,
        ACQUISITION_CONTEXT_REMOVED_UNDER_EVERY_OPTION,
    ),
    (
        ACQUISITION_CONTEXT,
        None,
        EVERY_OPTION,
        ACQUISITION_CONTEXT_REMOVED_UNDER_EVERY_OPTION,
    ),
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


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("name, preset, options, removed, values", [
    (
        IMPLANTATION,
        "public-release",
        None,
        IMPLANTATION_REMOVED_UNDER_EVERY_OPTION | IMPLANTATION_UIDS,
        {
            "Person Observer Name": "D",
            "Component ID": "D",
            # X/D gives D, which gives the UID U's replacement.
            "Frame of Reference UID": "U",
        },
    ),
    (
        IMPLANTATION,
        None,
        EVERY_OPTION,
        IMPLANTATION_REMOVED_UNDER_EVERY_OPTION,
        {
            "Person Observer Name": "D",
            "Component ID": "D",
            # Retain UIDs keeps the UIDs, and the references to the
            # assembly, the image, the fiducials, and the registration.
            "Frame of Reference UID": "K",
            "User Selected Fiducial": "K",
        },
    ),
    (
        PERFORMED,
        "tps-import",
        None,
        PERFORMED_REMOVED_UNDER_EVERY_OPTION | ADMINISTRATION_UIDS,
        {
            "Person Observer Name": "D",
            # X/D, which Modified Dates modifies.
            "DateTime Started": "C",
        },
    ),
    (
        ACQUISITION_CONTEXT,
        "public-release",
        None,
        ACQUISITION_CONTEXT_REMOVED_UNDER_EVERY_OPTION,
        {
            "Person Observer Name": "D",
            # X/D and X, which Modified Dates modifies.
            "DateTime Started": "C",
            "DateTime Ended": "C",
        },
    ),
    (
        ACQUISITION_CONTEXT,
        "basic",
        None,
        ACQUISITION_CONTEXT_REMOVED_UNDER_EVERY_OPTION,
        {
            "Person Observer Name": "D",
            # X/D gives D, and so does X for DateTime Ended, a reviewed row.
            "DateTime Started": "D",
            "DateTime Ended": "D",
        },
    ),
])  # fmt: skip
def test_a_kept_tree_gives_each_listed_value_its_action(
    with_option, name, preset, options, removed, values
):
    dataset, iod = _report(name, _keepable(name, removed))

    actions, plan = _planned(dataset, iod, _composed(with_option, preset, options))

    assert not plan.sequestrations
    assert _values_by_concept(dataset, actions) == values
    # The other values, among them the imaging agent's identifier, its
    # barcode, unit serial, and lot, the step's UID, and the animal's room,
    # are not listed, so they take their own rules. A reference or a number
    # has no value attribute of its own: a reference kept under K or D keeps
    # its UIDs' own rules, and a number is kept.


# The optional rows of each report that public-release, with the option
# added, keeps, other than the UDI coded as TID 11004 row 26 gives it.
RELEASED_UNDER_PUBLIC_RELEASE = {
    IMPLANTATION: _keepable(
        IMPLANTATION, IMPLANTATION_REMOVED_UNDER_EVERY_OPTION | IMPLANTATION_UIDS
    ),
    ECHO: _keepable(ECHO, ECHO_REMOVED_UNDER_EVERY_OPTION),
    PLANNED: _keepable(
        PLANNED,
        PLANNED_REMOVED_UNDER_EVERY_OPTION
        | ADMINISTRATION_UIDS
        | ADMINISTRATION_PATIENT
        | {"TID 11004 row 26"},
    ),
    PERFORMED: _keepable(
        PERFORMED,
        PERFORMED_REMOVED_UNDER_EVERY_OPTION
        | ADMINISTRATION_UIDS
        | ADMINISTRATION_PATIENT
        | {"TID 11004 row 26"},
    ),
    ACQUISITION_CONTEXT: _keepable(
        ACQUISITION_CONTEXT, ACQUISITION_CONTEXT_REMOVED_UNDER_EVERY_OPTION
    ),
}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
@pytest.mark.parametrize("name", RELEASED_UNDER_PUBLIC_RELEASE)
def test_a_written_report_holds_no_source_value_and_is_released(with_option, name):
    dataset, _ = _report(name, RELEASED_UNDER_PUBLIC_RELEASE[name])

    data, decision = _released(with_option("public-release"), dataset)

    # Unlisted free text, such as the imaging agent's identifier, its
    # barcode, unit serial, and lot, and the animal's room, takes Text
    # Value's own rule, a dummy value.
    for value in SOURCE_VALUES:
        assert value.encode() not in data, value
    assert isinstance(decision, run.Release), decision
    written = pydicom.dcmread(io.BytesIO(data))
    assert _shape(written) == _shape(dataset)
    assert CSC_CODE in [
        code.get("CodeValue") for code in written.DeidentificationMethodCodeSequence
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
def test_a_written_performed_administration_references_its_plan(with_option):
    dataset, _ = _report(PERFORMED, ("TID 11020 row 11",))

    data, _ = _released(with_option("public-release"), dataset)

    # Planned Imaging Agent Administration SOP Instance is not listed, so
    # its reference is kept, and its UID takes U's replacement, the same as
    # the evidence's.
    written = pydicom.dcmread(io.BytesIO(data))
    (plan,) = _by_meaning(
        written, "Planned Imaging Agent Administration SOP Instance"
    ).ReferencedSOPSequence
    (evidence,) = (
        written.CurrentRequestedProcedureEvidenceSequence[0]
        .ReferencedSeriesSequence[0]
        .ReferencedSOPSequence
    )
    assert plan.ReferencedSOPClassUID == reports.PLANNED_ADMINISTRATION_SR
    assert (
        plan.ReferencedSOPInstanceUID
        == evidence.ReferencedSOPInstanceUID
        != reports.PLANNED_ADMINISTRATION[1]
    )


@pytest.mark.parametrize("name", [PLANNED, PERFORMED])
@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_a_udi_coded_as_tid_11004_gives_it_is_not_looked_up(
    with_option, name, preset, options
):
    composed = _composed(with_option, preset, options)
    dataset, iod = _report(name, ("TID 11004 row 26",))
    actions, _ = _planned(dataset, iod, composed)

    # UDI (128739, DCM) is not listed in Table E.3.4-1, so the tree is kept,
    # and the identifier, the code's Long Code Value, keeps its own rule, as
    # a code in any kept sequence does.
    assert all(
        key[:2] != ("DCM", "128739")
        for key in content_items.concept_actions(composed.options)
    )
    assert actions.get(ElementPath((), CONTENT)) == "K"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A UDI content item with the Value Type CODE, as TID 11004 row 26 "
        "gives it, is not listed in Table E.3.4-1, so its code, the device's "
        "Unique Device Identifier, is kept and released, while Table E.1-1 "
        "removes UDI Sequence and Unique Device Identifier unless Retain "
        "Device Identity is selected."
    ),
)
@pytest.mark.usefixtures("supported")
@pytest.mark.parametrize("name", [PLANNED, PERFORMED])
def test_a_udi_is_not_released(with_option, name):
    dataset, _ = _report(name, ("TID 11004 row 26",))

    result = _transformed(with_option("public-release"), dataset)

    # Removing the item, sequestering the instance for it, or withholding the
    # written file at the release gate each keep the identifier unreleased.
    if not isinstance(result, run.Transformed):
        assert isinstance(result, run.Sequestered), result
        return
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert reports.SYRINGE_UDI.encode() not in result.data or not isinstance(
        decision, run.Release
    )


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


@pytest.mark.usefixtures("supported")
@pytest.mark.parametrize("name", REPORTS)
def test_a_verified_report_is_written_with_a_dummy_verifier(with_option, name):
    dataset, _ = _report(name, verified=True)

    data, decision = _released(with_option("public-release"), dataset)

    assert isinstance(decision, run.Release), decision
    for value in (general.VERIFIERS_NAME, f"{general.SENTINEL} HOSPITAL"):
        assert value.encode() not in data, value
    written = pydicom.dcmread(io.BytesIO(data))
    assert written.VerificationFlag == "VERIFIED"
    (verifier,) = written.VerifyingObserverSequence
    assert verifier.VerifyingObserverName == "DEIDENTIFIED"
    assert verifier.VerifyingOrganization == "DEIDENTIFIED"
