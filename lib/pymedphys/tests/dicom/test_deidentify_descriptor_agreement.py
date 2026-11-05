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

"""Clean Descriptors writes a series', study's, patient's, or frame's descriptor alike.

A descriptor of an information entity that spans instances, such as Series
Description (0008,103E) of the General Series module, has one value for
every instance of the entity. Descriptor cleaning decides on each instance's
values, so instances of one series whose values differ, or whose own person
identifiers differ, could otherwise write the attribute in some instances
and remove it from others, which dcentvfy reports as an attribute present in
one instance of the series but not another.
"""

import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    ReviewedDescriptor,
    ReviewedDescriptors,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review, ReviewedNames

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
SERIES_DESCRIPTION = "(0008,103E)"
STUDY_DESCRIPTION = "(0008,1030)"
OTHER_SERIES = "2.25.210"
OTHER_SLICE = "2.25.211"


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _transform(*decisions, preset="basic-clean-descriptors"):
    reviewed = ReviewedDescriptors.empty()
    for tag, value, review in decisions:
        reviewed.record(tag, value, ReviewedDescriptor(review))
    return InstanceTransform(
        compose_policy(preset),
        KEY,
        cleaning=DescriptorCleaning(
            None, ReviewedNames.empty(), reviewed_descriptors=reviewed
        ),
        unvalidated_policy=True,
    )


def _slice(number, **attributes):
    dataset = synthetic.ct_slice(number)
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    return dataset


def _other_series(**attributes):
    other = _slice(0, **attributes)
    synthetic.uid(other, "SeriesInstanceUID", OTHER_SERIES)
    synthetic.uid(other, "SOPInstanceUID", OTHER_SLICE)
    return other


def _run(tmp_path, datasets, transform=None):
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    result = run.run(
        run.discover(source),
        tmp_path / "release",
        _transform() if transform is None else transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )
    return result


def _released(result):
    """Return each released file's data set, by its input's position."""
    return {
        outcome.position: pydicom.dcmread(result.release / outcome.output)
        for outcome in result.outcomes
        if outcome.status is run.Status.RELEASED
    }


def _values(released, keyword):
    return [dataset.get(keyword) for _, dataset in sorted(released.items())]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "added",
    [
        # The vocabulary keeps the first two values but not the third,
        # which takes its action without the option, X.
        "AXIAL CHEST SENTINEL",
        # It keeps all three, since GRAY is a common name that it keeps as
        # a reviewed exception, but the third differs from the others.
        "AXIAL CHEST GRAY",
    ],
)
def test_a_series_whose_values_differ_takes_the_action_without_the_option(
    tmp_path, added
):
    result = _run(
        tmp_path,
        [
            _slice(0, SeriesDescription="AXIAL CHEST"),
            _slice(1, SeriesDescription="AXIAL CHEST"),
            _slice(2, SeriesDescription=added),
        ],
    )

    released = _released(result)
    assert sorted(released) == [0, 1, 2]
    assert _values(released, "SeriesDescription") == [None, None, None]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_series_whose_values_agree_writes_them_in_every_instance(tmp_path):
    result = _run(
        tmp_path,
        [_slice(number, SeriesDescription="AXIAL CHEST") for number in range(3)],
    )

    released = _released(result)
    assert _values(released, "SeriesDescription") == ["AXIAL CHEST"] * 3


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_an_identifier_of_one_instance_takes_its_series_value_out_of_all(
    tmp_path,
):
    # The same value in every instance, but one instance names a person
    # whose name is a word of it, so the echo check holds it there.
    result = _run(
        tmp_path,
        [
            _slice(0, SeriesDescription="AXIAL CHEST"),
            _slice(1, SeriesDescription="AXIAL CHEST", OperatorsName="CHEST^ROLE"),
            _slice(2, SeriesDescription="AXIAL CHEST"),
        ],
    )

    released = _released(result)
    assert _values(released, "SeriesDescription") == [None, None, None]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_an_instance_without_the_attribute_takes_it_out_of_its_series(tmp_path):
    result = _run(
        tmp_path,
        [
            _slice(0, SeriesDescription="AXIAL CHEST"),
            _slice(1),
            _slice(2, SeriesDescription="AXIAL CHEST"),
        ],
    )

    released = _released(result)
    assert _values(released, "SeriesDescription") == [None, None, None]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_disagreement_in_one_series_leaves_another_series_alone(tmp_path):
    other = _other_series(SeriesDescription="AXIAL CHEST")
    result = _run(
        tmp_path,
        [
            _slice(0, SeriesDescription="AXIAL CHEST"),
            _slice(1, SeriesDescription="AXIAL CHEST SENTINEL"),
            other,
        ],
    )

    released = _released(result)
    assert _values(released, "SeriesDescription") == [None, None, "AXIAL CHEST"]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_value_that_echoes_a_person_is_still_searched_for(tmp_path):
    # The value that the second instance holds names its operator, so the
    # other series, which writes the same value, is not released.
    result = _run(
        tmp_path,
        [
            _slice(0, SeriesDescription="AXIAL CHEST"),
            _slice(1, SeriesDescription="AXIAL CHEST", OperatorsName="CHEST^ROLE"),
            _other_series(SeriesDescription="AXIAL CHEST"),
        ],
    )

    *released, other = result.outcomes
    assert [outcome.status for outcome in released] == [run.Status.RELEASED] * 2
    assert other.status is not run.Status.RELEASED
    assert any(
        reason.code.value == "residual-text" and reason.path.tag == SERIES_DESCRIPTION
        for reason in other.reasons
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_study_descriptor_is_written_alike_across_its_series(tmp_path):
    # A reviewer keeps the study's value; one instance, of another series,
    # names a person whose name is a word of it.
    other = _other_series(StudyDescription="STUDY FICTITIOUS")
    other.PatientName = "SYNTHETIC^PERSON"
    keep = (STUDY_DESCRIPTION, "STUDY FICTITIOUS", Review.KEEP)
    datasets = [
        _slice(0, StudyDescription="STUDY FICTITIOUS"),
        _slice(1, StudyDescription="STUDY FICTITIOUS"),
        other,
    ]
    for dataset in datasets[:2]:
        dataset.PatientName = "SYNTHETIC^PERSON"
    datasets[1].OperatorsName = "FICTITIOUS^ROLE"

    result = _run(tmp_path, datasets, _transform(keep))

    released = _released(result)
    assert _values(released, "StudyDescription") == [None, None, None]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_qc_pack_shows_a_disagreeing_value_was_not_applied(tmp_path):
    result = _run(
        tmp_path,
        [
            _slice(0, SeriesDescription="AXIAL CHEST"),
            _slice(1, SeriesDescription="AXIAL CHEST SENTINEL"),
        ],
    )

    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    listed = {
        (entry["position"], entry["applied"]): [
            value["outcome"] for value in entry["values"]
        ]
        for entry in pack["descriptors"]
    }
    assert listed == {(0, False): ["kept by vocabulary"], (1, False): ["held"]}
    # Not written, so not retained.
    assert not any(
        string["value"] == "AXIAL CHEST" for string in pack["retained_strings"]
    )


def _withheld_slice(number, **attributes):
    """A slice that the run sequesters before cleaning its descriptors.

    Responsible Person and Responsible Organization are required where
    present, and the profile removes them.
    """
    dataset = _slice(number, **attributes)
    dataset.ResponsiblePerson = "ROLE^PERSON"
    dataset.ResponsibleOrganization = "SENTINEL ORGANISATION"
    return dataset


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _prepared(transform, datasets):
    data = [synthetic.written(dataset) for dataset in datasets]
    records = {
        position: InstanceRecord.from_file(item) for position, item in enumerate(data)
    }
    transform.prepare(records, lambda position: data[position])
    return [(item, records[position]) for position, item in enumerate(data)]


def _collected(result, tag):
    return [value for value in result.evidence.collected if value.source.tag == tag]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize("other", ["AXIAL CHEST", "AXIAL CHEST SENTINEL"])
def test_a_withheld_instance_leaves_out_a_kept_value_whatever_its_series(other):
    transform = _transform()
    (withheld, record), _ = _prepared(
        transform,
        [
            _withheld_slice(0, SeriesDescription="AXIAL CHEST"),
            _slice(1, SeriesDescription=other),
        ],
    )

    result = transform(withheld, record)

    assert isinstance(result, run.Sequestered)
    assert not _collected(result, SERIES_DESCRIPTION)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_an_instance_of_a_series_that_was_not_prepared_decides_alone():
    transform = _transform()

    result = _transformed(transform, _slice(0, SeriesDescription="AXIAL CHEST"))

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.SeriesDescription == "AXIAL CHEST"


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_an_unprepared_instance_of_a_prepared_series_must_agree():
    transform = _transform()
    _prepared(
        transform,
        [_slice(number, SeriesDescription="AXIAL CHEST") for number in range(2)],
    )

    agrees = _transformed(transform, _slice(2, SeriesDescription="AXIAL CHEST"))
    differs = _transformed(transform, _slice(2, SeriesDescription="AXIAL HEAD"))

    assert pydicom.dcmread(io.BytesIO(agrees.data)).SeriesDescription == ("AXIAL CHEST")
    assert "SeriesDescription" not in pydicom.dcmread(io.BytesIO(differs.data))
