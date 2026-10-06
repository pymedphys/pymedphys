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

"""The graph of a collection's instances and references, and what it reports."""

import logging
import re
import warnings

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import reference_graph
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_references as synthetic

Edge = reference_graph.Edge
Finding = reference_graph.Finding
DANGLING = reference_graph.FindingKind.DANGLING_REFERENCE
MISSING = reference_graph.FindingKind.MISSING_IDENTIFIER
DUPLICATE = reference_graph.FindingKind.DUPLICATE_INSTANCE
CONFLICTING = reference_graph.FindingKind.CONFLICTING_INSTANCE
SEVERAL_STUDIES = reference_graph.FindingKind.SERIES_IN_SEVERAL_STUDIES
SEVERAL_PATIENTS = reference_graph.FindingKind.STUDY_WITH_SEVERAL_PATIENTS
SOP_INSTANCE_UID, SERIES_INSTANCE_UID, STUDY_INSTANCE_UID = (
    "(0008,0018)",
    "(0020,000E)",
    "(0020,000D)",
)

# Positions in synthetic.collection().
CT_POSITIONS = (0, 1, 2)
STRUCTURE_SET, PLAN, DOSE = 3, 4, 5
TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")


def _graph(inputs):
    """Return the graph of the inputs: data sets to write, or written files."""
    return reference_graph.build_reference_graph(
        [
            InstanceRecord.from_file(each)
            if isinstance(each, bytes)
            else synthetic.record(each)
            for each in inputs
        ]
    )


def _dangling(position, attribute, count=1):
    return Finding(DANGLING, ((position,),), attribute, count)


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_a_consistent_collection_has_no_findings():
    records = [synthetic.record(dataset) for dataset in synthetic.collection()]

    graph = reference_graph.build_reference_graph(records)

    assert not graph.findings
    assert graph.records == tuple(records)
    assert len(graph.records) == 6


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_each_reference_resolves_to_its_instance():
    datasets = synthetic.collection()
    # Padding does not stop a reference resolving.
    synthetic.uid(datasets[0], "SOPInstanceUID", synthetic.CT_SLICES[0] + "\x00")
    datasets[PLAN].ReferencedDoseSequence = [
        synthetic.reference(synthetic.RT_DOSE_STORAGE, synthetic.DOSE + " \x00")
    ]

    graph = _graph(datasets)

    assert not graph.findings
    assert graph.edges == {
        *(
            Edge(STRUCTURE_SET, attribute, position)
            for attribute in (synthetic.CONTOUR_IMAGES, synthetic.ROI_CONTOUR_IMAGES)
            for position in CT_POSITIONS
        ),
        Edge(PLAN, synthetic.REFERENCED_STRUCTURE_SET, STRUCTURE_SET),
        Edge(PLAN, synthetic.REFERENCED_DOSE, DOSE),
        Edge(DOSE, synthetic.REFERENCED_PLAN, PLAN),
        Edge(DOSE, synthetic.REFERENCED_STRUCTURE_SET, STRUCTURE_SET),
    }


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize(
    "dropped, expected",
    [
        pytest.param(
            1,
            [
                _dangling(2, synthetic.CONTOUR_IMAGES),
                _dangling(2, synthetic.ROI_CONTOUR_IMAGES),
            ],
            id="ct-slice",
        ),
        pytest.param(
            STRUCTURE_SET,
            [
                _dangling(3, synthetic.REFERENCED_STRUCTURE_SET),
                _dangling(4, synthetic.REFERENCED_STRUCTURE_SET),
            ],
            id="structure-set",
        ),
        pytest.param(PLAN, [_dangling(4, synthetic.REFERENCED_PLAN)], id="plan"),
        pytest.param(DOSE, [_dangling(4, synthetic.REFERENCED_DOSE)], id="dose"),
    ],
)
def test_a_reference_to_an_instance_not_in_the_collection_is_dangling(
    dropped, expected
):
    datasets = synthetic.collection()
    del datasets[dropped]

    assert _graph(datasets).findings == tuple(expected)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "sequence, keyword, attribute, value, dangling",
    [
        pytest.param(
            "ReferencedSeriesSequence",
            "SeriesInstanceUID",
            ("(0008,1115)", "(0020,000E)"),
            value,
            dangling,
            id=f"series-{name}",
        )
        for name, value, dangling in [
            ("in-collection", synthetic.CT_SERIES, False),
            ("not-in-collection", "2.25.9001", True),
            # A study is not a series.
            ("naming-a-study", synthetic.STUDY, True),
        ]
    ]
    + [
        pytest.param(
            "StudiesContainingOtherReferencedInstancesSequence",
            "StudyInstanceUID",
            ("(0008,1200)", "(0020,000D)"),
            value,
            dangling,
            id=f"study-{name}",
        )
        for name, value, dangling in [
            ("in-collection", synthetic.STUDY, False),
            ("not-in-collection", "2.25.9002", True),
            ("naming-a-series", synthetic.CT_SERIES, True),
        ]
    ],
)
def test_a_reference_to_a_series_or_study_not_in_the_collection_is_dangling(
    sequence, keyword, attribute, value, dangling
):
    datasets = synthetic.collection()
    setattr(datasets[DOSE], sequence, [synthetic.item(**{keyword: value})])

    graph = _graph(datasets)

    assert graph.findings == ((_dangling(DOSE, attribute),) if dangling else ())
    # Only references to instances are edges.
    assert len(graph.edges) == 10


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize("padding", ["", "\x00"], ids=["unpadded", "padded"])
@pytest.mark.parametrize(
    "sop_class",
    [synthetic.PRIVATE_SOP_CLASS, synthetic.NM_IMAGE_STORAGE_RETIRED],
    ids=["private", "retired-storage"],
)
def test_a_reference_to_an_input_of_a_class_outside_table_b5_1_resolves(
    sop_class, padding
):
    # A Private SOP Class can follow the semantics of the Storage Service Class
    # (PS3.4 B.4.1.2), and a retired Storage SOP Class was stored under an
    # earlier edition, so a collection can hold an instance of either.
    datasets = synthetic.collection()
    other = synthetic.instance(None, synthetic.OTHER, synthetic.OTHER_SERIES)
    synthetic.uid(other, "SOPClassUID", sop_class + padding)
    datasets.append(other)
    datasets[PLAN].ReferencedImageSequence = [
        synthetic.reference(sop_class + padding, synthetic.OTHER)
    ]

    graph = _graph(datasets)

    assert not graph.findings
    assert graph.edges == _graph(synthetic.collection()).edges | {
        Edge(PLAN, synthetic.REFERENCED_IMAGE, len(datasets) - 1)
    }


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "sequence, attribute, sop_class, dangling",
    [
        pytest.param(
            "ReferencedPerformedProcedureStepSequence",
            ("(0008,1111)", "(0008,1155)"),
            synthetic.MODALITY_PERFORMED_PROCEDURE_STEP,
            False,
            id="performed-procedure-step",
        ),
        pytest.param(
            "ReferencedPerformedProcedureStepSequence",
            ("(0008,1111)", "(0008,1155)"),
            synthetic.MODALITY_PERFORMED_PROCEDURE_STEP + "\x00",
            False,
            id="padded-performed-procedure-step",
        ),
        pytest.param(
            "ReferencedImageSequence",
            synthetic.REFERENCED_IMAGE,
            synthetic.PRIVATE_SOP_CLASS,
            False,
            id="private",
        ),
        pytest.param(
            "ReferencedImageSequence",
            synthetic.REFERENCED_IMAGE,
            synthetic.NM_IMAGE_STORAGE_RETIRED,
            False,
            id="retired-storage",
        ),
        pytest.param(
            "ReferencedImageSequence",
            synthetic.REFERENCED_IMAGE,
            synthetic.CT_IMAGE_STORAGE,
            True,
            id="ct-image-storage",
        ),
        pytest.param(
            "ReferencedImageSequence",
            synthetic.REFERENCED_IMAGE,
            synthetic.MR_IMAGE_STORAGE,
            True,
            id="storage-of-another-iod",
        ),
        pytest.param(
            "ReferencedImageSequence",
            synthetic.REFERENCED_IMAGE,
            None,
            True,
            id="no-sop-class",
        ),
    ],
)
def test_a_missing_target_of_a_class_outside_table_b5_1_is_not_dangling(
    sequence, attribute, sop_class, dangling
):
    datasets = synthetic.collection()
    setattr(datasets[PLAN], sequence, [synthetic.reference(sop_class, "2.25.9003")])

    findings = _graph(datasets).findings

    assert findings == ((_dangling(PLAN, attribute),) if dangling else ())


def _refer_to_study(dataset, attribute, sop_class, value):
    """Make ``dataset`` refer to the study ``value`` at ``attribute``."""
    if attribute == synthetic.RT_REFERENCED_STUDY:
        frame = dataset.ReferencedFrameOfReferenceSequence[0]
        study = frame.RTReferencedStudySequence[0]
        del study.ReferencedSOPClassUID
        if sop_class is not None:
            synthetic.uid(study, "ReferencedSOPClassUID", sop_class)
        synthetic.uid(study, "ReferencedSOPInstanceUID", value)
        return
    study = synthetic.reference(sop_class, value)
    if attribute == synthetic.REFERENCED_STUDY:
        dataset.ReferencedStudySequence = [study]
    else:
        dataset.RequestAttributesSequence = [
            synthetic.item(ReferencedStudySequence=[study])
        ]


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "value, dangling",
    [
        (synthetic.STUDY, False),
        (synthetic.STUDY + "\x00", False),
        ("2.25.9005", True),
        # The SOP Instance UID of an input is not a Study Instance UID.
        (synthetic.CT_SLICES[0], True),
    ],
    ids=["in-collection", "padded", "not-in-collection", "naming-an-instance"],
)
@pytest.mark.parametrize(
    "sop_class",
    [
        synthetic.DETACHED_STUDY_MANAGEMENT,
        None,
        synthetic.PRIVATE_SOP_CLASS,
        synthetic.CT_IMAGE_STORAGE,
    ],
    ids=["detached-study-management", "no-sop-class", "private", "ct-image-storage"],
)
@pytest.mark.parametrize(
    "attribute",
    [
        synthetic.RT_REFERENCED_STUDY,
        synthetic.REFERENCED_STUDY,
        synthetic.REQUESTED_REFERENCED_STUDY,
    ],
    ids=["rt-referenced-study", "referenced-study", "requested-study"],
)
def test_a_reference_to_a_study_resolves_to_the_study_whatever_its_class(
    attribute, sop_class, value, dangling
):
    # PS3.3 Sections 10.6.1 and C.8.8.5.4: in these sequences, Referenced SOP
    # Instance UID is the study's, and Referenced SOP Class UID is the study's
    # own class, which may be retired or private. So the study resolves among
    # the inputs' Study Instance UIDs, and the class rule does not apply.
    datasets = synthetic.collection()
    _refer_to_study(datasets[STRUCTURE_SET], attribute, sop_class, value)

    graph = _graph(datasets)

    assert graph.findings == (
        (_dangling(STRUCTURE_SET, attribute),) if dangling else ()
    )
    # Only references to instances are edges.
    assert graph.edges == _graph(synthetic.collection()).edges


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "value",
    [synthetic.HOT_IRON_COLOR_PALETTE, synthetic.HOT_IRON_COLOR_PALETTE + "\x00"],
    ids=["unpadded", "padded"],
)
def test_a_reference_to_a_well_known_instance_is_not_dangling(value):
    datasets = synthetic.collection()
    datasets[PLAN].ReferencedImageSequence = [synthetic.reference(None, value)]

    assert not _graph(datasets).findings


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "value", ["", "\x00", " \x00"], ids=["empty", "nul", "space-and-nul"]
)
def test_an_empty_value_where_the_iod_requires_one_is_dangling(value):
    # Referenced SOP Instance UID is Type 1 in the Referenced Structure Set
    # Sequence of an RT Plan.
    datasets = synthetic.collection()
    datasets[PLAN].ReferencedStructureSetSequence = [
        synthetic.reference(synthetic.RT_STRUCTURE_SET_STORAGE, value)
    ]

    assert _graph(datasets).findings == (
        _dangling(PLAN, synthetic.REFERENCED_STRUCTURE_SET),
    )


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "value, dangling",
    [
        ("", False),
        ("\x00", False),
        (" \x00", False),
        ("2.25.9004", True),
        ([synthetic.STUDY, synthetic.STUDY], True),
    ],
    ids=["empty", "nul", "space-and-nul", "not-in-collection", "two-values"],
)
@pytest.mark.parametrize(
    "position, attribute",
    [
        (0, synthetic.REQUESTED_STUDY),
        (STRUCTURE_SET, synthetic.REQUESTED_STUDY),
        (PLAN, synthetic.REQUESTED_STUDY),
        (DOSE, synthetic.REQUESTED_STUDY),
        (PLAN, synthetic.PERTINENT_DOCUMENTS),
    ],
    ids=[
        "ct-request",
        "structure-set-request",
        "plan-request",
        "dose-request",
        "plan-document",
    ],
)
def test_an_empty_value_where_the_iod_makes_a_reference_optional_is_absent(
    position, attribute, value, dangling
):
    # PS3.5 7.4.5: a Type 3 element with zero length means the same as an
    # absent one.
    datasets = synthetic.collection()
    if attribute == synthetic.REQUESTED_STUDY:
        request = synthetic.item()
        synthetic.uid(request, "StudyInstanceUID", value)
        datasets[position].RequestAttributesSequence = [request]
    else:
        document = synthetic.reference(synthetic.ENCAPSULATED_PDF_STORAGE, value)
        datasets[position].add(synthetic.rt_assertions(document))

    findings = _graph(datasets).findings

    assert findings == ((_dangling(position, attribute),) if dangling else ())


@pytest.mark.pydicom
def test_a_reference_with_several_values_is_dangling():
    # Referenced SOP Instance UID has one value (VM 1), so two values name
    # nothing, even when each names an instance in the collection.
    datasets = synthetic.collection()
    datasets[PLAN].ReferencedStructureSetSequence = [
        synthetic.reference(
            synthetic.RT_STRUCTURE_SET_STORAGE,
            [synthetic.STRUCTURE_SET, synthetic.STRUCTURE_SET],
        )
    ]

    assert _graph(datasets).findings == (
        _dangling(PLAN, synthetic.REFERENCED_STRUCTURE_SET),
    )


@pytest.mark.pydicom
def test_distinct_missing_instances_are_counted_once():
    datasets = synthetic.collection()
    # Two contours on the first slice and one on the second.
    datasets[STRUCTURE_SET].ROIContourSequence[0].ContourSequence = [
        synthetic.contour(synthetic.CT_SLICES[0]),
        synthetic.contour(synthetic.CT_SLICES[0]),
        synthetic.contour(synthetic.CT_SLICES[1]),
    ]

    # Without the CT slices, the structure set is at position 0.
    findings = _graph(datasets[STRUCTURE_SET:]).findings

    assert findings == (
        _dangling(0, synthetic.RT_REFERENCED_SERIES, 1),
        _dangling(0, synthetic.CONTOUR_IMAGES, 3),
        _dangling(0, synthetic.ROI_CONTOUR_IMAGES, 2),
    )


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "keyword, tag",
    [
        ("SOPInstanceUID", "(0008,0018)"),
        ("SeriesInstanceUID", "(0020,000E)"),
        ("StudyInstanceUID", "(0020,000D)"),
    ],
)
@pytest.mark.parametrize(
    "value", ["absent", "", "\x00", "twice"], ids=["absent", "empty", "nul", "twice"]
)
def test_an_instance_without_an_identifier_is_reported(keyword, tag, value):
    datasets = synthetic.collection()
    if value == "absent":
        delattr(datasets[0], keyword)
    elif value == "twice":
        original = getattr(datasets[0], keyword)
        synthetic.uid(datasets[0], keyword, [original, original])
    else:
        synthetic.uid(datasets[0], keyword, value)

    findings = _graph(datasets).findings

    assert [finding for finding in findings if finding.kind is MISSING] == [
        Finding(MISSING, ((0,),), (tag,), 0)
    ]


def _text_values(dataset):
    for element in dataset.iterall():
        if element.VR in ("LO", "PN", "UI") and element.VM == 1:
            yield str(element.value)


@pytest.mark.pydicom
def test_findings_contain_no_values():
    datasets = synthetic.collection()
    del datasets[PLAN].SeriesInstanceUID
    datasets = datasets[1:]

    graph = _graph(datasets)

    assert {finding.kind for finding in graph.findings} == {DANGLING, MISSING}
    assert repr(graph) == f"ReferenceGraph(findings={graph.findings!r})"
    shown = repr(graph) + repr(graph.findings) + repr(sorted(graph.edges))
    shown += "".join(repr(record) for record in graph.records)
    values = {value for dataset in datasets for value in _text_values(dataset)}
    # Including the missing slice's UID, which the structure set references.
    assert {
        synthetic.PATIENT_ID,
        synthetic.PATIENTS_NAME,
        synthetic.CT_SLICES[0],
    } <= values
    for value in values:
        assert value not in shown
    for finding in graph.findings:
        assert all(TAG.fullmatch(tag) for tag in finding.attribute)
        assert all(
            isinstance(position, int)
            for group in finding.instances
            for position in group
        )
        assert isinstance(finding.count, int)


@pytest.mark.pydicom
def test_building_the_graph_neither_warns_nor_logs(caplog, capsys):
    datasets = synthetic.collection()[1:]
    del datasets[0].StudyInstanceUID

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG):
            graph = _graph(datasets)

    assert graph.findings
    assert not caught
    assert not caplog.records
    assert capsys.readouterr() == ("", "")


@pytest.mark.pydicom
def test_findings_are_ordered_by_kind_then_position():
    datasets = synthetic.collection()
    datasets[0].ReferencedImageSequence = [synthetic.reference(None, "2.25.9010")]
    datasets[PLAN].ReferencedStructureSetSequence = [
        synthetic.reference(synthetic.RT_STRUCTURE_SET_STORAGE, "2.25.9011")
    ]
    datasets[PLAN].ReferencedDoseSequence = [
        synthetic.reference(synthetic.RT_DOSE_STORAGE, "2.25.9012")
    ]
    datasets[PLAN].ReferencedRTPlanSequence = [
        synthetic.reference(synthetic.RT_PLAN_STORAGE, "2.25.9013")
    ]
    del datasets[DOSE].SeriesInstanceUID

    assert _graph(datasets).findings == (
        Finding(MISSING, ((DOSE,),), ("(0020,000E)",)),
        _dangling(0, synthetic.REFERENCED_IMAGE),
        # By tag path, not by the order of the IOD's modules.
        _dangling(PLAN, synthetic.REFERENCED_PLAN),
        _dangling(PLAN, synthetic.REFERENCED_STRUCTURE_SET),
        _dangling(PLAN, synthetic.REFERENCED_DOSE),
    )


SOURCE_ISSUER = "SYNTHETIC-ISSUER-3H8M"
OTHER_ISSUER = "SYNTHETIC-ISSUER-9W4D"
OTHER_PATIENT_ID = "SYNTHETIC-5R8N"
OTHER_STUDY = "2.25.110"
# How to build another copy of an instance in synthetic.collection(), and
# the position of the instance there.
INSTANCES = [
    pytest.param(lambda: synthetic.ct_slice(0), 0, id="ct-slice"),
    pytest.param(synthetic.structure_set, STRUCTURE_SET, id="structure-set"),
    pytest.param(synthetic.rt_plan, PLAN, id="plan"),
    pytest.param(synthetic.rt_dose, DOSE, id="dose"),
]


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize("build, position", INSTANCES)
def test_copies_of_one_instance_are_duplicates(build, position):
    datasets = synthetic.collection() + [build(), build()]

    graph = _graph(datasets)

    assert graph.findings == (
        Finding(DUPLICATE, ((position, 6, 7),), (SOP_INSTANCE_UID,)),
    )


def _private_text(dataset, value):
    block = dataset.private_block(0x0009, "SYNTHETIC CREATOR 5T", create=True)
    block.add_new(0x01, "LO", value)


def _plans_in_implicit_and_explicit_vr(change=None):
    """Return the collection, its plan written in Implicit VR, and a copy.

    The copy, at position 6, is written in Explicit VR. ``change``, if given,
    changes both plans before they are written.
    """

    def plan():
        dataset = synthetic.rt_plan()
        if change is not None:
            change(dataset)
        return dataset

    datasets = synthetic.collection()
    datasets[PLAN] = synthetic.written(plan(), synthetic.IMPLICIT_VR_LITTLE_ENDIAN)
    datasets.append(synthetic.written(plan(), synthetic.EXPLICIT_VR_LITTLE_ENDIAN))
    return datasets


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_copies_in_implicit_and_explicit_vr_conflict():
    # Every element of the plan has a VR in pydicom's data dictionary, so
    # the copies decode to the same elements, but their source bytes differ.
    datasets = _plans_in_implicit_and_explicit_vr()

    assert _graph(datasets).findings == (
        Finding(CONFLICTING, ((PLAN,), (6,)), (SOP_INSTANCE_UID,)),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_copies_in_implicit_and_explicit_vr_with_a_private_element_conflict():
    # pydicom reads the private element from the Implicit VR copy as UN,
    # without the VR that the Explicit VR copy holds.
    datasets = _plans_in_implicit_and_explicit_vr(
        lambda dataset: _private_text(dataset, "SYNTHETIC PRIVATE TEXT")
    )
    assert synthetic.read(datasets[PLAN])[0x00091001].VR == "UN"

    assert _graph(datasets).findings == (
        Finding(CONFLICTING, ((PLAN,), (6,)), (SOP_INSTANCE_UID,)),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize(
    "change",
    [
        lambda dataset: setattr(dataset, "PatientName", "FICTITIOUS^OTHER"),
        lambda dataset: setattr(dataset, "StudyDescription", "SYNTHETIC"),
        lambda dataset: delattr(dataset, "PatientName"),
        lambda dataset: _private_text(dataset, "SYNTHETIC PRIVATE TEXT"),
    ],
    ids=["changed-value", "added-element", "removed-element", "private-element"],
)
@pytest.mark.parametrize("build, position", INSTANCES)
def test_one_sop_instance_uid_with_different_content_conflicts(build, position, change):
    changed = build()
    change(changed)
    datasets = synthetic.collection() + [changed]

    assert _graph(datasets).findings == (
        Finding(CONFLICTING, ((position,), (6,)), (SOP_INSTANCE_UID,)),
    )


@pytest.mark.pydicom
def test_conflicting_copies_are_grouped_by_content():
    def changed(value):
        dataset = synthetic.ct_slice(1)
        _private_text(dataset, value)
        return dataset

    datasets = synthetic.collection() + [
        changed("SYNTHETIC-A"),
        synthetic.ct_slice(1),
        changed("SYNTHETIC-B"),
        changed("SYNTHETIC-A"),
    ]

    assert _graph(datasets).findings == (
        Finding(CONFLICTING, ((1, 7), (6, 9), (8,)), (SOP_INSTANCE_UID,)),
    )


@pytest.mark.pydicom
def test_references_to_a_duplicated_instance_resolve_to_each_copy():
    datasets = synthetic.collection() + [synthetic.ct_slice(0)]

    graph = _graph(datasets)

    assert graph.findings == (Finding(DUPLICATE, ((0, 6),), (SOP_INSTANCE_UID,)),)
    assert graph.edges == _graph(synthetic.collection()).edges | {
        Edge(STRUCTURE_SET, attribute, 6)
        for attribute in (synthetic.CONTOUR_IMAGES, synthetic.ROI_CONTOUR_IMAGES)
    }


@pytest.mark.pydicom
def test_each_copy_of_an_instance_reports_its_dangling_references_once():
    # Without the second CT slice, each copy of the structure set has one
    # distinct missing instance at each of the two sites, however many
    # copies there are.
    datasets = synthetic.collection()
    del datasets[1]
    datasets.append(synthetic.structure_set())

    findings = _graph(datasets).findings

    assert findings == (
        _dangling(2, synthetic.CONTOUR_IMAGES),
        _dangling(2, synthetic.ROI_CONTOUR_IMAGES),
        _dangling(5, synthetic.CONTOUR_IMAGES),
        _dangling(5, synthetic.ROI_CONTOUR_IMAGES),
        Finding(DUPLICATE, ((2, 5),), (SOP_INSTANCE_UID,)),
    )


@pytest.mark.pydicom
def test_an_instance_without_a_sop_instance_uid_is_no_duplicate():
    datasets = synthetic.collection() + [synthetic.ct_slice(0), synthetic.ct_slice(0)]
    for dataset in datasets[-2:]:
        del dataset.SOPInstanceUID

    findings = _graph(datasets).findings

    # The first CT slice and its copies would be duplicates.
    assert findings == (
        Finding(MISSING, ((6,),), (SOP_INSTANCE_UID,)),
        Finding(MISSING, ((7,),), (SOP_INSTANCE_UID,)),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize(
    "study, several",
    [
        (OTHER_STUDY, True),
        (OTHER_STUDY + "\x00", True),
        (synthetic.STUDY + "\x00", False),
        (synthetic.STUDY, False),
    ],
    ids=["other-study", "other-study-padded", "same-study-padded", "same-study"],
)
def test_a_series_in_two_studies_is_inconsistent(study, several):
    datasets = synthetic.collection()
    synthetic.uid(datasets[1], "StudyInstanceUID", study)

    findings = _graph(datasets).findings

    assert findings == (
        (Finding(SEVERAL_STUDIES, ((0, 2), (1,)), (SERIES_INSTANCE_UID,)),)
        if several
        else ()
    )


@pytest.mark.pydicom
def test_a_series_in_three_studies_is_grouped_by_study():
    datasets = synthetic.collection() + [synthetic.ct_slice(0)]
    synthetic.uid(datasets[6], "SOPInstanceUID", "2.25.204")
    synthetic.uid(datasets[1], "StudyInstanceUID", OTHER_STUDY)
    synthetic.uid(datasets[6], "StudyInstanceUID", "2.25.120")
    synthetic.uid(datasets[2], "StudyInstanceUID", OTHER_STUDY)

    assert _graph(datasets).findings == (
        Finding(SEVERAL_STUDIES, ((0,), (1, 2), (6,)), (SERIES_INSTANCE_UID,)),
    )


@pytest.mark.pydicom
def test_an_instance_without_a_study_does_not_name_another_study():
    datasets = synthetic.collection()
    del datasets[1].StudyInstanceUID

    assert _graph(datasets).findings == (
        Finding(MISSING, ((1,),), (STUDY_INSTANCE_UID,)),
    )


def _set_patient(dataset, patient_id, issuer):
    """Set the Patient ID and its issuer, where each is given."""
    for keyword, value in [("PatientID", patient_id), ("IssuerOfPatientID", issuer)]:
        if value is None:
            if keyword in dataset:
                delattr(dataset, keyword)
        else:
            setattr(dataset, keyword, value)


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize(
    "first, second, several",
    [
        ((synthetic.PATIENT_ID, None), (OTHER_PATIENT_ID, None), True),
        # The same Patient ID from another issuer is another subject.
        (
            (synthetic.PATIENT_ID, SOURCE_ISSUER),
            (synthetic.PATIENT_ID, OTHER_ISSUER),
            True,
        ),
        ((synthetic.PATIENT_ID, SOURCE_ISSUER), (synthetic.PATIENT_ID, None), True),
        ((synthetic.PATIENT_ID, SOURCE_ISSUER), (synthetic.PATIENT_ID, ""), True),
        ((synthetic.PATIENT_ID, SOURCE_ISSUER), (synthetic.PATIENT_ID, "  "), True),
        (
            (synthetic.PATIENT_ID, SOURCE_ISSUER),
            (synthetic.PATIENT_ID, SOURCE_ISSUER),
            False,
        ),
        ((synthetic.PATIENT_ID, None), (synthetic.PATIENT_ID, ""), False),
        # Padding is not significant (PS3.5 Section 6.2).
        (
            (synthetic.PATIENT_ID, SOURCE_ISSUER),
            (synthetic.PATIENT_ID + " ", " " + SOURCE_ISSUER + "\x00"),
            False,
        ),
        # An instance without a Patient ID is a patient apart from every
        # identity, and the instances without one are one patient.
        ((synthetic.PATIENT_ID, SOURCE_ISSUER), (None, SOURCE_ISSUER), True),
        ((synthetic.PATIENT_ID, SOURCE_ISSUER), ("", SOURCE_ISSUER), True),
        ((synthetic.PATIENT_ID, None), (" ", None), True),
        ((None, SOURCE_ISSUER), (synthetic.PATIENT_ID, SOURCE_ISSUER), True),
        ((None, SOURCE_ISSUER), ("  ", OTHER_ISSUER), False),
    ],
    ids=[
        "other-patient-id",
        "other-issuer",
        "issuer-and-none",
        "issuer-and-empty",
        "issuer-and-padding",
        "same-issuer",
        "none-and-empty",
        "padded",
        "no-patient-id",
        "empty-patient-id",
        "padding-only-patient-id",
        "one-patient-id",
        "no-patient-ids",
    ],
)
def test_a_study_with_two_patients_is_inconsistent(first, second, several):
    datasets = synthetic.collection()
    for dataset in datasets:
        _set_patient(dataset, *first)
    _set_patient(datasets[PLAN], *second)

    findings = _graph(datasets).findings

    assert findings == (
        (Finding(SEVERAL_PATIENTS, ((0, 1, 2, 3, 5), (PLAN,)), (STUDY_INSTANCE_UID,)),)
        if several
        else ()
    )


@pytest.mark.pydicom
def test_patients_in_different_studies_are_consistent():
    other = synthetic.ct_slice(0)
    synthetic.uid(other, "SOPInstanceUID", "2.25.1201")
    synthetic.uid(other, "SeriesInstanceUID", "2.25.1200")
    synthetic.uid(other, "StudyInstanceUID", OTHER_STUDY)
    other.PatientID = OTHER_PATIENT_ID

    assert not _graph(synthetic.collection() + [other]).findings


@pytest.mark.pydicom
def test_a_study_with_three_patients_is_grouped_by_patient():
    datasets = synthetic.collection()
    _set_patient(datasets[1], synthetic.PATIENT_ID, SOURCE_ISSUER)
    _set_patient(datasets[PLAN], OTHER_PATIENT_ID, None)
    _set_patient(datasets[DOSE], synthetic.PATIENT_ID, SOURCE_ISSUER)

    assert _graph(datasets).findings == (
        Finding(
            SEVERAL_PATIENTS, ((0, 2, 3), (1, DOSE), (PLAN,)), (STUDY_INSTANCE_UID,)
        ),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_a_study_whose_instances_all_lack_a_patient_id_has_one_patient():
    # Whether the Patient ID is absent, empty, or only padding, and whatever
    # the issuer.
    datasets = synthetic.collection()
    forms = [(None, None), ("", SOURCE_ISSUER), ("  ", OTHER_ISSUER), (None, "")]
    for position, dataset in enumerate(datasets):
        _set_patient(dataset, *forms[position % len(forms)])

    assert synthetic.record(datasets[2]).patient is None
    assert not _graph(datasets).findings


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_the_instances_without_a_patient_id_are_grouped_as_one_patient():
    datasets = synthetic.collection()
    _set_patient(datasets[1], None, SOURCE_ISSUER)
    _set_patient(datasets[STRUCTURE_SET], "", None)
    _set_patient(datasets[PLAN], OTHER_PATIENT_ID, None)
    _set_patient(datasets[DOSE], "  ", OTHER_ISSUER)

    assert _graph(datasets).findings == (
        Finding(
            SEVERAL_PATIENTS,
            ((0, 2), (1, STRUCTURE_SET, DOSE), (PLAN,)),
            (STUDY_INSTANCE_UID,),
        ),
    )


def _inconsistent_collection():
    """Return a collection with each kind of finding, and their values."""
    datasets = synthetic.collection()
    datasets[DOSE].PatientID = OTHER_PATIENT_ID
    datasets[PLAN].IssuerOfPatientID = SOURCE_ISSUER
    synthetic.uid(datasets[2], "StudyInstanceUID", OTHER_STUDY)
    del datasets[STRUCTURE_SET].SeriesInstanceUID
    conflicting = synthetic.rt_plan()
    _private_text(conflicting, "SYNTHETIC PRIVATE TEXT")
    datasets += [synthetic.ct_slice(1), conflicting]
    datasets[PLAN].ReferencedRTPlanSequence = [
        synthetic.reference(synthetic.RT_PLAN_STORAGE, "2.25.9013")
    ]
    values = {
        OTHER_PATIENT_ID,
        SOURCE_ISSUER,
        OTHER_STUDY,
        "2.25.9013",
        "SYNTHETIC PRIVATE TEXT",
    }
    return datasets, values


@pytest.mark.pydicom
def test_findings_are_ordered_by_kind_from_instance_to_study():
    datasets, _ = _inconsistent_collection()

    findings = _graph(datasets).findings

    assert findings == (
        Finding(MISSING, ((STRUCTURE_SET,),), (SERIES_INSTANCE_UID,)),
        _dangling(PLAN, synthetic.REFERENCED_PLAN),
        Finding(DUPLICATE, ((1, 6),), (SOP_INSTANCE_UID,)),
        Finding(CONFLICTING, ((PLAN,), (7,)), (SOP_INSTANCE_UID,)),
        Finding(SEVERAL_STUDIES, ((0, 1, 6), (2,)), (SERIES_INSTANCE_UID,)),
        Finding(
            SEVERAL_PATIENTS,
            ((0, 1, 3, 6, 7), (PLAN,), (DOSE,)),
            (STUDY_INSTANCE_UID,),
        ),
    )


@pytest.mark.pydicom
def test_hierarchy_findings_contain_no_values(caplog, capsys):
    datasets, planted = _inconsistent_collection()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG):
            graph = _graph(datasets)

    assert not caught
    assert not caplog.records
    assert capsys.readouterr() == ("", "")
    assert {finding.kind for finding in graph.findings} == set(
        reference_graph.FindingKind
    )
    assert repr(graph) == f"ReferenceGraph(findings={graph.findings!r})"
    shown = [repr(graph), str(graph), repr(sorted(graph.edges))]
    shown += [repr(finding) + str(finding) for finding in graph.findings]
    shown += [repr(record) + str(record) for record in graph.records]
    shown += [repr(record.patient) + str(record.patient) for record in graph.records]
    shown = "".join(shown).lower()
    values = {value for dataset in datasets for value in _text_values(dataset)}
    assert planted | {synthetic.PATIENT_ID, synthetic.STUDY} <= values
    for value in values:
        assert value.lower() not in shown
    for record in graph.records:
        assert record.digest.hex() not in shown
