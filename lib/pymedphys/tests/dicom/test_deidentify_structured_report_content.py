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

"""The Clean Structured Content Option on general Structured Reports.

The Comprehensive SR, Comprehensive 3D SR, Key Object Selection Document,
and Mammography CAD SR IODs are not supported yet, so the engine
sequesters their instances. These tests show, ahead of supporting them,
what the option does with their content trees (D-047): which presets and
Retain options, with the option added, keep a report that holds only the
rows that its templates require; which features take the whole tree out,
among them concept names coded in a scheme that the engine cannot look up;
which optional rows take it out under each option set; the action that each
value of a kept tree takes; and what is written and released, in the tests
that add the IODs to the supported ones for that test alone, as supporting
them would. The reports are synthetic, built from the templates of PS3.16
2026d by :mod:`._synthetic_structured_reports`.

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

from . import _corpus_run
from . import _synthetic_references as synthetic
from . import _synthetic_structured_reports as reports

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
CSC_CODE = "113104"
CONTENT = "(0040,A730)"
VERIFYING_OBSERVER = "(0040,A073)"
VERIFICATION_FLAG = "(0040,A493)"
IMAGING = "imaging"
MEASUREMENT = "measurement"
KEY_OBJECTS = "key objects"
CAD = "mammography CAD"
REPORTS = {
    IMAGING: (reports.imaging_report, reports.COMPREHENSIVE_SR_IOD),
    MEASUREMENT: (reports.measurement_report, reports.COMPREHENSIVE_3D_SR_IOD),
    KEY_OBJECTS: (
        lambda optional=(), **_: reports.key_object_selection(optional),
        reports.KEY_OBJECT_SELECTION_IOD,
    ),
    CAD: (reports.mammography_cad_report, reports.MAMMOGRAPHY_CAD_SR_IOD),
}
OPTIONAL_ROWS = {
    IMAGING: reports.IMAGING_OPTIONAL_ROWS,
    MEASUREMENT: reports.MEASUREMENT_OPTIONAL_ROWS,
    KEY_OBJECTS: reports.KEY_OBJECT_OPTIONAL_ROWS,
    CAD: reports.CAD_OPTIONAL_ROWS,
}
# The reports whose IOD has a Verification Flag.
VERIFIABLE = (IMAGING, MEASUREMENT, CAD)
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


@pytest.fixture(name="supported")
def _supported(monkeypatch):
    """Add the four IODs to the supported ones, as supporting them would."""
    monkeypatch.setattr(
        scope,
        "SUPPORTED_IODS",
        scope.SUPPORTED_IODS | {iod for _, iod in REPORTS.values()},
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


def test_the_reports_are_of_iods_that_are_not_supported_yet():
    for name, (build, iod) in REPORTS.items():
        dataset = build()
        classification = scope.classify(
            dataset.SOPClassUID, synthetic.EXPLICIT_VR_LITTLE_ENDIAN
        )

        assert classification.reason == scope.UnsupportedIod(iod), name
        assert load_iod_tables().iods[iod].lookup(CONTENT, ()), name


def test_a_key_object_selection_document_has_no_verification_flag():
    iod = load_iod_tables().iods[reports.KEY_OBJECT_SELECTION_IOD]

    # The Key Object Document Module (PS3.3 Table C.17.6-2) has neither, so
    # only the other reports are built VERIFIED.
    assert not iod.lookup(VERIFICATION_FLAG, ())
    assert not iod.lookup(VERIFYING_OBSERVER, ())
    for name in VERIFIABLE:
        assert load_iod_tables().iods[REPORTS[name][1]].lookup(VERIFYING_OBSERVER, ())


@pytest.mark.parametrize("name", REPORTS)
def test_without_the_option_a_report_is_sequestered(name):
    dataset, iod = _report(name)

    _, plan = _planned(dataset, iod, policy.compose_policy("basic"))

    # Table E.1-1 gives Content Sequence D, and a sequence has no dummy
    # value (D-021).
    assert [s.path for s in plan.sequestrations] == [ElementPath((), CONTENT)]


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, cad", [
    ("basic", True),
    ("basic-clean-descriptors", True),
    ("tps-import", True),
    ("public-release", True),
])  # fmt: skip
def test_which_presets_with_the_option_keep_a_report_of_required_rows(
    with_option, preset, cad
):
    composed = with_option(preset)

    for name in REPORTS:
        kept = cad if name == CAD else True
        dataset, iod = _report(name)
        _, plan = _planned(dataset, iod, composed)
        assert _kept(dataset, iod, composed) is kept, name
        assert bool(plan.sequestrations) is not kept, name
        # The CAD optional rows can all be cleaned; the other reports
        # include optional identifiers that still require removal.
        everything, _ = _report(name, OPTIONAL_ROWS[name])
        assert _kept(everything, iod, composed) is (name == CAD), name


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("options, cad", [
    ((), True),
    ((policy.SAFE_PRIVATE,), True),
    ((policy.UIDS,), True),
    ((policy.DEVICE_IDENTITY,), True),
    ((policy.INSTITUTION_IDENTITY,), True),
    ((policy.PATIENT_CHARACTERISTICS,), True),
    ((policy.FULL_DATES,), True),
    ((policy.MODIFIED_DATES,), True),
    ((policy.CLEAN_DESCRIPTORS,), True),
])  # fmt: skip
def test_which_retain_options_with_the_option_keep_a_report_of_required_rows(
    options, cad
):
    composed = policy.compose_custom_policy((CSC, *options))

    for name in REPORTS:
        dataset, iod = _report(name)
        assert _kept(dataset, iod, composed) is (cad if name == CAD else True), name


@pytest.mark.parametrize("preset, removed", [
    # TID 4020 rows 7 and 8 receive dummy dates and times under X/D.
    ("basic", set()),
    ("basic-clean-descriptors", set()),
    ("tps-import", set()),
    ("public-release", set()),
])  # fmt: skip
def test_the_required_rows_that_table_e3_4_1_removes(with_option, preset, removed):
    actions = content_items.concept_actions(with_option(preset).options)

    for name in REPORTS:
        dataset, _ = _report(name)
        assert {
            meaning
            for meaning, key in _concepts(dataset)
            if actions.get(key) == content_items.REMOVE
        } == (removed if name == CAD else set()), name


# Each feature whose concept name is coded in a scheme whose rows the
# generated table cannot hold: LOINC, NCIt, and UMLS, whose rows the pin
# leaves out (D-001). Each is given with the report and options that hold it,
# and the scheme of the concept name that takes the tree out.
UNMATCHED_FEATURES = {
    # Most of CID 7000's titles, for the root of TID 2000.
    "LOINC title": (IMAGING, (), {"title": reports.DIAGNOSTIC_IMAGING_REPORT}, "LN"),
    # A heading of CID 7001 in its preferred encoding, LOINC, for TID 2000
    # row 8.
    "LOINC heading": (IMAGING, ("TID 2000 row 8",), {}, "LN"),
    # TID 1004 row 11, required in a Unique Device Identifiers container.
    "LOINC device identifier": (
        MEASUREMENT,
        reports.with_holders("TID 1004 row 10"),
        {},
        "LN",
    ),
    "NCIt activity session": (MEASUREMENT, ("TID 1411 row 1b",), {}, "NCIt"),
    # TID 1502 row 3, required where TID 1411 row 4 includes TID 1502.
    "UMLS time point": (MEASUREMENT, ("TID 1411 row 4",), {}, "UMLS"),
}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("feature", UNMATCHED_FEATURES)
@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS[2:]),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_a_concept_name_that_cannot_be_looked_up_takes_the_tree_out(
    with_option, feature, preset, options
):
    name, optional, kwargs, scheme = UNMATCHED_FEATURES[feature]
    composed = _composed(with_option, preset, options)
    dataset, iod = _report(name, optional, **kwargs)

    assert scheme in content_items.UNMATCHED_SCHEMES
    assert scheme in {key[0] for _, key in _concepts(dataset)}
    assert not _kept(dataset, iod, composed)
    # The same report without the feature, with a DCM title, is kept.
    plain, _ = _report(name)
    assert _kept(plain, iod, composed)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS[2:]),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_a_finding_site_coded_by_its_snomed_ids_is_kept_as_in_snomed_ct(
    with_option, preset, options
):
    composed = _composed(with_option, preset, options)
    retired, iod = _report(MEASUREMENT, ("TID 1419 row 2",), snomed_ids=True)
    current, _ = _report(MEASUREMENT, ("TID 1419 row 2",))

    assert "SRT" in {key[0] for _, key in _concepts(retired)}
    assert "SRT" not in {key[0] for _, key in _concepts(current)}
    # PS3.16 Table O-1 maps each SNOMED ID to the SNOMED CT code that the
    # other report gives the same concept, so each item takes the same action.
    actions, _ = _planned(retired, iod, composed)
    assert actions == _planned(current, iod, composed)[0]
    assert actions.get(ElementPath((), CONTENT)) == "K"


# The optional rows of TID 1001 that take the tree out under every option
# set: Table E.3.4-1 gives each X under every option, or X with C under Clean
# Descriptors, which falls back to X (D-009), or its concept name is
# coded in LOINC.
OBSERVATION_REMOVED_UNDER_EVERY_OPTION = {
    "TID 1003 row 1a",  # Person Observer's Login Name
    "TID 1004 row 10",  # Unique Device Identifier, coded in LOINC
    "TID 1005 row 7",  # Accession Number
    "TID 1007 row 4",  # Subject Birth Date
}
# Retain Institution Identity keeps Person Observer's Organization Name.
OBSERVATION_INSTITUTION = {"TID 1003 row 2"}
# Retain UIDs keeps Procedure Study Instance UID and Subject UID,
# whose plain X actions otherwise remove their items.
OBSERVATION_UIDS = {"TID 1005 row 1", "TID 1007 row 1"}
# Retain Device Identity keeps Device Observer Name; the observer UID
# otherwise takes U under the dummy action.
OBSERVATION_DEVICE = {"TID 1004 row 2"}
# Retain Patient Characteristics keeps Subject Sex and Subject Age.
OBSERVATION_PATIENT = {"TID 1007 row 5", "TID 1007 row 6"}
OBSERVATION_REMOVED_UNDER_BASIC = (
    OBSERVATION_REMOVED_UNDER_EVERY_OPTION
    | OBSERVATION_INSTITUTION
    | OBSERVATION_UIDS
    | OBSERVATION_DEVICE
    | OBSERVATION_PATIENT
)
# tps-import retains device identity and patient characteristics.
OBSERVATION_REMOVED_UNDER_TPS_IMPORT = (
    OBSERVATION_REMOVED_UNDER_EVERY_OPTION | OBSERVATION_INSTITUTION | OBSERVATION_UIDS
)
MEASUREMENT_REMOVED_UNDER_EVERY_OPTION = {
    "TID 1602 row 5c",  # Series Description, X with C under Clean Descriptors
    "TID 1411 row 1b",  # Activity Session, coded in NCIt
    "TID 1411 row 4",  # Time Point, coded in UMLS
}
# Retain UIDs keeps the Frame of Reference UID, X/D, and the Illustration of
# ROI, X.
MEASUREMENT_UIDS = {"TID 1411 row 13"}
# Study Date and Content Date take dummy values without a dates option.
# Frame of Reference UID takes U without Retain UIDs.


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.parametrize("name, preset, options, removed", [
    (IMAGING, "basic", None, OBSERVATION_REMOVED_UNDER_BASIC | {"TID 2000 row 8"}),
    (
        IMAGING,
        "tps-import",
        None,
        OBSERVATION_REMOVED_UNDER_TPS_IMPORT | {"TID 2000 row 8"},
    ),
    (
        IMAGING,
        "public-release",
        None,
        OBSERVATION_REMOVED_UNDER_BASIC | {"TID 2000 row 8"},
    ),
    (
        IMAGING,
        None,
        EVERY_OPTION,
        OBSERVATION_REMOVED_UNDER_EVERY_OPTION | {"TID 2000 row 8"},
    ),
    (
        MEASUREMENT,
        "basic",
        None,
        OBSERVATION_REMOVED_UNDER_BASIC
        | MEASUREMENT_REMOVED_UNDER_EVERY_OPTION
        | MEASUREMENT_UIDS,
    ),
    (
        MEASUREMENT,
        "tps-import",
        None,
        OBSERVATION_REMOVED_UNDER_TPS_IMPORT
        | MEASUREMENT_REMOVED_UNDER_EVERY_OPTION
        | MEASUREMENT_UIDS,
    ),
    (
        MEASUREMENT,
        None,
        EVERY_OPTION,
        OBSERVATION_REMOVED_UNDER_EVERY_OPTION | MEASUREMENT_REMOVED_UNDER_EVERY_OPTION,
    ),
    # Key Object Description is X, with C under Clean Descriptors, and
    # Person Observer's Login Name X; Retain Institution Identity keeps
    # Person Observer's Organization Name.
    (
        KEY_OBJECTS,
        "public-release",
        None,
        {
            "TID 2010 row 7",
            "TID 2010 row 6 TID 1003 row 1a",
            "TID 2010 row 6 TID 1003 row 2",
        },
    ),
    (
        KEY_OBJECTS,
        None,
        EVERY_OPTION,
        {"TID 2010 row 7", "TID 2010 row 6 TID 1003 row 1a"},
    ),
    # Frame of Reference UID takes U under its dummy action; Modified Dates
    # modifies the Content Date and Time and the Recommended Follow-up Date,
    # X/D, and the Impression Description is D.
    (CAD, "tps-import", None, set()),
    (CAD, "public-release", None, set()),
    (CAD, None, EVERY_OPTION, set()),
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
        MEASUREMENT,
        None,
        EVERY_OPTION,
        OBSERVATION_REMOVED_UNDER_EVERY_OPTION | MEASUREMENT_REMOVED_UNDER_EVERY_OPTION,
        {
            "Person Observer Name": "D",
            "Person Observer's Organization Name": "K",
            "Device Observer UID": "K",
            "Device Observer Name": "K",
            "Procedure Study Instance UID": "K",
            "Subject UID": "K",
            "Subject Name": "D",
            "Subject ID": "D",
            "Study Date": "K",
            "Series Instance UID": "K",
            "Content Date": "K",
            "Frame of Reference UID": "K",
            "Tracking Unique Identifier": "K",
            "Source series for segmentation": "K",
        },
    ),
    (
        MEASUREMENT,
        "public-release",
        None,
        OBSERVATION_REMOVED_UNDER_BASIC
        | MEASUREMENT_REMOVED_UNDER_EVERY_OPTION
        | MEASUREMENT_UIDS,
        {
            "Person Observer Name": "D",
            "Subject Name": "D",
            "Subject ID": "D",
            "Study Date": "C",
            "Series Instance UID": "U",
            "Content Date": "C",
            "Tracking Unique Identifier": "U",
            "Source series for segmentation": "U",
            "Device Observer UID": "U",
            "Frame of Reference UID": "U",
        },
    ),
    (
        CAD,
        "tps-import",
        None,
        set(),
        {
            "Study Date": "C",
            "Study Time": "C",
            "Content Date": "C",
            "Content Time": "C",
            # D, with C under Clean Descriptors, which falls back to D.
            "Impression Description": "D",
            "Recommended Follow-up Date": "C",
            "Frame of Reference UID": "U",
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
    # The other values, among them the Tracking Identifier, the Algorithm
    # Name and Version, and the Patient Orientation, are not listed, so they
    # take their own rules.


@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_the_narrative_of_an_imaging_report_keeps_only_unlisted_text(
    with_option, preset, options
):
    actions = content_items.concept_actions(
        _composed(with_option, preset, options).options
    )

    found = {
        code.meaning: (
            "unmatched"
            if code.designator in content_items.UNMATCHED_SCHEMES
            else actions.get((code.designator, code.value, "TEXT"))
        )
        for code in reports.DIAGNOSTIC_IMAGING_REPORT_ELEMENTS
    }

    # Under every option set, each TEXT item of TID 2002 that Table E.3.4-1
    # lists is removed, X or X/D, with C under Clean Descriptors falling back
    # to X; Previous Finding and Impression are not listed; and the rest are
    # coded in LOINC. TID 2000 holds the narrative only in a section, whose
    # heading CID 7001 prefers in LOINC, which takes the tree out; a section
    # under its equivalent DCM heading is kept, as tested below.
    assert found == {
        "History": "unmatched",
        "Request": "unmatched",
        "Procedure Description": "D",
        "Previous Finding": None,
        "Finding": "D",
        "Impression": None,
        "Recommendation": "X",
        "Conclusion": "X",
        "Complication of Procedure": "X",
        "Patient Presentation": "unmatched",
        "Summary": "unmatched",
    }


@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_a_section_under_an_equivalent_dcm_heading_is_kept(
    with_option, preset, options
):
    composed = _composed(with_option, preset, options)
    dataset, iod = _report(
        IMAGING, ("TID 2000 row 8",), heading=reports.DCM_IMPRESSIONS
    )
    actions, _ = _planned(dataset, iod, composed)

    # The heading and the Impression are not listed, so the tree is kept, and
    # the impression's free text takes Text Value's own rule, a dummy.
    listed = content_items.concept_actions(composed.options)
    for meaning, key in _concepts(dataset):
        if meaning in {"Impressions", "Impression"}:
            assert key not in listed, meaning
    assert _kept(dataset, iod, composed)
    assert _values_by_concept(dataset, actions) == {"Person Observer Name": "D"}


@pytest.mark.usefixtures("supported")
def test_a_section_under_an_equivalent_dcm_heading_is_written_and_released(
    with_option,
):
    dataset, _ = _report(IMAGING, ("TID 2000 row 8",), heading=reports.DCM_IMPRESSIONS)

    data, decision = _released(with_option("public-release"), dataset)

    assert reports.SENTINEL.encode() not in data
    assert isinstance(decision, run.Release), decision
    assert _shape(pydicom.dcmread(io.BytesIO(data))) == _shape(dataset)


@pytest.mark.parametrize("preset, options", [
    *((preset, None) for preset in PRESETS),
    (None, EVERY_OPTION),
])  # fmt: skip
def test_a_subject_id_coded_as_tid_1007_gives_it_is_not_looked_up(
    with_option, preset, options
):
    composed = _composed(with_option, preset, options)
    dataset, iod = _report(IMAGING, ("TID 1007 row 3",))
    actions, _ = _planned(dataset, iod, composed)

    # TID 1007 row 3 gives Subject ID the Value Type CODE, and Table E.3.4-1
    # lists it only as TEXT, so the item is not listed: the tree is kept,
    # and the identifier, its Code Value, keeps its own rule, K.
    assert ("DCM", "121030", "CODE") not in content_items.concept_actions(
        composed.options
    )
    assert actions.get(ElementPath((), CONTENT)) == "K"
    assert _values_by_concept(dataset, actions) == {"Person Observer Name": "D"}


@pytest.mark.usefixtures("supported")
def test_the_residual_search_withholds_a_subject_id_that_is_the_patient_id(
    with_option,
):
    dataset, _ = _report(IMAGING, ("TID 1007 row 3",))

    data, decision = _released(with_option("public-release"), dataset)

    assert reports.PATIENT_ID.encode() in data
    assert isinstance(decision, run.Sequestered)
    assert {reason.code for reason in decision.reasons} == {
        ReasonCode.RESIDUAL_DIRECT_IDENTIFIER
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A Subject ID content item with the Value Type CODE, as TID 1007 "
        "gives it, is not listed in Table E.3.4-1, so its Code Value is kept; "
        "the residual search finds it only where it is the header's Patient ID."
    ),
)
@pytest.mark.usefixtures("supported")
def test_a_subject_id_other_than_the_patient_id_is_not_released(with_option):
    dataset, _ = _report(IMAGING)
    dataset.ContentSequence.append(reports.subject_identifier("SYNTHETIC-OTHER9"))

    result = _transformed(with_option("public-release"), dataset)

    # Removing the item, sequestering the instance for it, or withholding the
    # written file at the release gate each keep the identifier unreleased.
    if not isinstance(result, run.Transformed):
        assert isinstance(result, run.Sequestered), result
        return
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert b"SYNTHETIC-OTHER9" not in result.data or not isinstance(
        decision, run.Release
    )


# The optional rows of each report that public-release, with the option
# added, keeps, other than the Subject ID coded as TID 1007 gives it.
RELEASED_UNDER_PUBLIC_RELEASE = {
    MEASUREMENT: _keepable(
        MEASUREMENT,
        OBSERVATION_REMOVED_UNDER_BASIC
        | MEASUREMENT_REMOVED_UNDER_EVERY_OPTION
        | MEASUREMENT_UIDS
        | {"TID 1007 row 3"},
    ),
    KEY_OBJECTS: ("TID 2010 row 5", "TID 2010 row 6"),
    CAD: _keepable(CAD, {"TID 4020 row 17"}),
}


@pytest.mark.deid_requirement("PS3.15-E.3.4-01")
@pytest.mark.usefixtures("supported")
@pytest.mark.parametrize("name", RELEASED_UNDER_PUBLIC_RELEASE)
def test_a_written_report_holds_no_source_value_and_is_released(with_option, name):
    dataset, _ = _report(name, RELEASED_UNDER_PUBLIC_RELEASE[name])

    data, decision = _released(with_option("public-release"), dataset)

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
def test_a_written_cad_report_keeps_its_references(with_option):
    dataset, _ = _report(CAD)

    data, _ = _released(with_option("public-release"), dataset)

    written = pydicom.dcmread(io.BytesIO(data))
    # The Summary of Detections, its Successful Detections, and its
    # Detection Performed, whose last item is the by-reference relationship.
    detection = written.ContentSequence[3].ContentSequence[0].ContentSequence[0]
    by_reference = detection.ContentSequence[-1]
    # The by-reference relationship keeps its place along the tree, and its
    # target, the image library's entry, is still there, referring to the
    # same image as the evidence does, by its replaced UID.
    assert list(by_reference.ReferencedContentItemIdentifier) == list(reports.CAD_ENTRY)
    target = written
    for position in reports.CAD_ENTRY[1:]:
        target = target.ContentSequence[position - 1]
    assert target.ValueType == "IMAGE"
    (evidence,) = (
        written.CurrentRequestedProcedureEvidenceSequence[0]
        .ReferencedSeriesSequence[0]
        .ReferencedSOPSequence
    )
    image = target.ReferencedSOPSequence[0].ReferencedSOPInstanceUID
    assert image == evidence.ReferencedSOPInstanceUID != reports.MG_IMAGE


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("name", VERIFIABLE)
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
@pytest.mark.parametrize("name", VERIFIABLE)
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
    assert len(verifier.VerifyingObserverIdentificationCodeSequence) == 0
    # public-release selects Modified Dates, which modifies the time as it
    # does the instance's other dates.
    assert verifier.VerificationDateTime not in (
        reports.VERIFICATION_DATETIME,
        "19000101000000",
    )
