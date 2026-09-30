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

# Positions in synthetic.collection().
CT_POSITIONS = (0, 1, 2)
STRUCTURE_SET, PLAN, DOSE = 3, 4, 5
TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")


def _graph(datasets):
    return reference_graph.build_reference_graph(
        [InstanceRecord.from_dataset(dataset) for dataset in datasets]
    )


def _dangling(position, attribute, count=1):
    return Finding(DANGLING, ((position,),), attribute, count)


@pytest.mark.pydicom
def test_a_consistent_collection_has_no_findings():
    graph = _graph(synthetic.collection())

    assert not graph.findings
    assert len(graph.records) == 6


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


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "sequence, attribute, sop_class, followed",
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
            "ReferencedStudySequence",
            ("(0008,1110)", "(0008,1155)"),
            synthetic.DETACHED_STUDY_MANAGEMENT,
            False,
            id="detached-study-management",
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
def test_references_to_classes_that_are_not_stored_are_not_followed(
    sequence, attribute, sop_class, followed
):
    datasets = synthetic.collection()
    setattr(datasets[PLAN], sequence, [synthetic.reference(sop_class, "2.25.9003")])

    findings = _graph(datasets).findings

    assert findings == ((_dangling(PLAN, attribute),) if followed else ())


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
def test_an_empty_reference_is_dangling(value):
    datasets = synthetic.collection()
    datasets[PLAN].ReferencedStructureSetSequence = [
        synthetic.reference(synthetic.RT_STRUCTURE_SET_STORAGE, value)
    ]

    assert _graph(datasets).findings == (
        _dangling(PLAN, synthetic.REFERENCED_STRUCTURE_SET),
    )


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
        Finding(MISSING, ((0,),), (tag,))
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
