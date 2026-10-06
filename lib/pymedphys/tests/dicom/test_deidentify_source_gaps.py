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

"""Tests for finding what a source instance lacks of its IOD's requirements."""

import functools
import json
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    output_names,
    qc_pack,
    release_report,
    run,
    run_qc,
    run_report,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iod_conformance import SourceGap, source_gaps
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.uids import replacement_uid

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
MODALITY = "(0008,0060)"
SOURCE_SERIES = "(3006,004C)"


@pytest.fixture(name="basic")
def _basic():
    return compose_policy("basic")


@functools.lru_cache(maxsize=None)
def _iods():
    return load_iod_tables().iods


def _gaps(dataset, iod):
    return source_gaps(read_source(synthetic.written(dataset)), _iods()[iod])


def _structure_set(**series):
    dataset = synthetic.structure_set()
    dataset.SourceSeriesInformationSequence = [synthetic.item(**series)]
    return dataset


def test_a_type_1_attribute_of_a_mandatory_module_that_the_source_lacks_is_a_gap():
    gaps = _gaps(synthetic.ct_slice(0), "CT Image")

    assert SourceGap(ElementPath((), MODALITY), "1") in gaps


def test_an_attribute_the_source_holds_is_not_a_gap():
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    held = {gap.path for gap in _gaps(dataset, "CT Image")}

    assert ElementPath((), MODALITY) not in held
    assert ElementPath((), "(0010,0020)") not in held  # Patient ID


def test_a_type_2_attribute_that_the_source_lacks_is_a_gap():
    gaps = _gaps(synthetic.ct_slice(0), "CT Image")

    assert SourceGap(ElementPath((), "(0010,0030)"), "2") in gaps  # Birth Date


def test_only_unconditional_requirements_of_mandatory_modules_are_gaps():
    iod = _iods()["CT Image"]
    usage = {module.module: module.usage for module in iod.modules}

    for gap in _gaps(synthetic.ct_slice(0), "CT Image"):
        assert not gap.path.items
        assert any(
            definition.type == gap.type and usage[definition.module] == "M"
            for definition in iod.lookup(gap.path.tag)
        )


def test_the_overlay_plane_modules_attributes_are_not_gaps():
    tags = {gap.path.tag for gap in _gaps(synthetic.ct_slice(0), "CT Image")}

    assert not any(tag.startswith("(60") for tag in tags)


def test_a_requirement_in_an_item_the_source_holds_is_a_gap_at_its_path():
    gaps = _gaps(_structure_set(SeriesDescription="SYNTHETIC"), "RT Structure Set")
    in_item = {gap.path.tag for gap in gaps if gap.path.items == ((SOURCE_SERIES, 0),)}

    assert in_item == {
        MODALITY,
        "(0008,0021)",
        "(0008,0031)",
        "(0020,000E)",
        "(0020,0011)",
    }


def test_nothing_is_a_gap_in_an_item_the_source_does_not_hold():
    gaps = _gaps(synthetic.structure_set(), "RT Structure Set")

    assert not any(SOURCE_SERIES in dict(gap.path.items) for gap in gaps)


def test_gaps_are_in_file_order_then_in_the_iods_order():
    gaps = _gaps(_structure_set(SeriesDescription="SYNTHETIC"), "RT Structure Set")
    depths = [len(gap.path.items) for gap in gaps]

    assert depths[0] == 0
    assert gaps == tuple(dict.fromkeys(gaps))


def test_the_repr_names_only_the_path_and_type():
    gap = SourceGap(ElementPath((), MODALITY), "1")

    assert repr(gap) == (
        "SourceGap(path=ElementPath(items=(), tag='(0008,0060)'), type='1')"
    )


def _gap(tag="(0008,0060)", items=(), gap_type="1"):
    return SourceGap(ElementPath(items, tag), gap_type)


def test_the_release_report_counts_each_instance_once_per_attribute_and_type():
    nested = _gap(items=((SOURCE_SERIES, 0),))
    second = _gap(items=((SOURCE_SERIES, 1),))

    assert release_report.source_gaps([[_gap(), nested, second], [_gap()], []]) == (
        release_report.SourceGapCount("(0008,0060)", "1", 2),
        release_report.SourceGapCount("(3006,004C) > (0008,0060)", "1", 1),
    )


def test_the_release_report_lists_the_counts_by_attribute_and_type(basic):
    report = release_report.release_report(
        basic,
        vocabulary=None,
        reviewed_roi_names=None,
        gaps=release_report.source_gaps([[_gap("(0010,0030)", gap_type="2"), _gap()]]),
    )

    assert release_report.report_document(report)["source_gaps"] == [
        {"attribute": "(0008,0060)", "type": "1", "count": 1},
        {"attribute": "(0010,0030)", "type": "2", "count": 1},
    ]


@pytest.mark.parametrize(
    "count",
    [
        release_report.SourceGapCount("(0008,0060)", "1", 0),
        release_report.SourceGapCount("(0008,0060)", "1", True),
        release_report.SourceGapCount("(0008,0060)", "1C", 1),
        release_report.SourceGapCount("SENTINEL", "1", 1),
    ],
)
def test_the_release_report_refuses_a_count_not_of_its_form(basic, count):
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None, gaps=[count]
    )

    with pytest.raises(release_report.ReleaseReportError, match="source_gaps") as error:
        release_report.report_document(report)
    assert "SENTINEL" not in str(error.value)


def test_the_release_report_counts_need_gaps_for_each_instance():
    with pytest.raises(TypeError):
        release_report.source_gaps([_gap()])  # type: ignore[list-item]


def _instance(position):
    return qc_pack.InstanceEntry(
        position, "in/a.dcm", qc_pack.Disposition.RELEASED, output=_output(position)
    )


def _output(position):
    return output_names.instance_path(
        patient_id="DEID-" + "A" * 16,
        study_instance_uid=replacement_uid(KEY, "2.25.1"),
        series_instance_uid=replacement_uid(KEY, "2.25.2"),
        sop_instance_uid=replacement_uid(KEY, f"2.25.{position + 3}"),
    )


def test_the_qc_pack_lists_each_instances_gaps_by_place_and_type():
    pack = qc_pack.QcPack(
        qc_pack.new_reference(),
        (_instance(0), _instance(1)),
        source_gaps=(
            qc_pack.SourceGapEntry(1, (_gap(), _gap(items=((SOURCE_SERIES, 0),)))),
        ),
    )

    assert qc_pack.pack_document(pack)["source_gaps"] == [
        {
            "position": 1,
            "gaps": [
                {"element": "(0008,0060)", "type": "1"},
                {"element": "(3006,004C)[0] > (0008,0060)", "type": "1"},
            ],
        }
    ]
    assert "source_gaps=1" in repr(pack)


@pytest.mark.parametrize(
    "entries",
    [
        (qc_pack.SourceGapEntry(1, (_gap(),)), qc_pack.SourceGapEntry(0, (_gap(),))),
        (qc_pack.SourceGapEntry(0, (_gap(),)), qc_pack.SourceGapEntry(0, (_gap(),))),
        (qc_pack.SourceGapEntry(2, (_gap(),)),),
    ],
)
def test_the_qc_pack_lists_each_instance_once_in_order(entries):
    with pytest.raises(qc_pack.QcPackError, match="source_gaps"):
        qc_pack.QcPack(
            qc_pack.new_reference(), (_instance(0), _instance(1)), source_gaps=entries
        )


@pytest.mark.parametrize("gaps", [(), [_gap()], ("(0008,0060)",)])
def test_a_qc_pack_entry_needs_its_gaps(gaps):
    with pytest.raises(qc_pack.QcPackError, match="source gaps"):
        qc_pack.SourceGapEntry(0, gaps)


def test_the_transform_gives_each_in_scope_instance_its_gaps_as_qc_material():
    data = synthetic.written(synthetic.ct_slice(0))
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = transform(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed)
    given = tuple(item for item in result.qc if isinstance(item, SourceGap))
    assert given == _gaps(synthetic.ct_slice(0), "CT Image")
    assert given


def test_a_run_reports_its_source_gaps_in_the_report_and_the_qc_pack():
    gap = _gap()
    material = {0: (gap,), 1: ()}
    outcomes = (_released(0), _released(1))

    pack = run_qc.qc_pack_of((Path("in/a.dcm"), Path("in/b.dcm")), outcomes, material)
    text = run_report.ReleaseReporter(
        compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
    )(outcomes, material, pack.reference)

    assert pack.source_gaps == (qc_pack.SourceGapEntry(0, (gap,)),)
    assert json.loads(text)["source_gaps"] == [
        {"attribute": "(0008,0060)", "type": "1", "count": 1}
    ]


def _released(position):
    return run.Outcome(
        position=position, status=run.Status.RELEASED, output=_output(position)
    )
