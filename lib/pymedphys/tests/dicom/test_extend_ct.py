# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from copy import deepcopy

from pymedphys._imports import pytest

from pymedphys._dicom import uid as _uid
from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.ct.extend import (
    _convert_datasets_to_deque,
    _extend_datasets,
    _generate_uids,
)


@pytest.mark.pydicom
def test_out_of_order():
    initial_sop_instance_uids = _generate_uids(4)
    final_sop_instance_uids = _generate_uids(7)

    initial_series_uid = _uid.generate_uid()
    final_series_uid = _uid.generate_uid()

    number_of_slices_to_add = 3
    initial_slice_locations = [7, 3, 1, 5]
    expected_slice_locations = [-5, -3, -1, 1, 3, 5, 7]

    initial_datasets = _make_datasets(
        initial_series_uid, initial_sop_instance_uids, initial_slice_locations
    )
    expected_datasets = _make_datasets(
        final_series_uid, final_sop_instance_uids, expected_slice_locations
    )

    resulting_datasets = deepcopy(initial_datasets)

    _extend_datasets(
        resulting_datasets,
        0,
        number_of_slices_to_add,
        series_instance_uid=final_series_uid,
        sop_instance_uids=final_sop_instance_uids,
    )

    assert resulting_datasets != initial_datasets

    sorted_expected_slice_locations = sorted(expected_slice_locations)

    for eval_ds, ref_ds, slice_loc in zip(
        resulting_datasets, expected_datasets, sorted_expected_slice_locations
    ):
        assert eval_ds.ImagePositionPatient == ref_ds.ImagePositionPatient
        assert eval_ds.ImagePositionPatient[-1] == slice_loc

    assert resulting_datasets == expected_datasets


@pytest.mark.pydicom
def test_extend_datasets():
    initial_sop_instance_uids = _generate_uids(4)
    final_sop_instance_uids = _generate_uids(7)

    initial_series_uid = _uid.generate_uid()
    final_series_uid = _uid.generate_uid()

    number_of_slices_to_add = 3
    initial_slice_locations = [1, 3, 5, 7]
    expected_slice_locations_left = [-5, -3, -1, 1, 3, 5, 7]
    expected_slice_locations_right = [1, 3, 5, 7, 9, 11, 13]

    initial_datasets = _make_datasets(
        initial_series_uid, initial_sop_instance_uids, initial_slice_locations
    )
    expected_datasets_left = _make_datasets(
        final_series_uid, final_sop_instance_uids, expected_slice_locations_left
    )
    expected_datasets_right = _make_datasets(
        final_series_uid, final_sop_instance_uids, expected_slice_locations_right
    )

    resulting_datasets_left = deepcopy(initial_datasets)
    resulting_datasets_right = deepcopy(initial_datasets)

    _extend_datasets(
        resulting_datasets_left,
        0,
        number_of_slices_to_add,
        series_instance_uid=final_series_uid,
        sop_instance_uids=final_sop_instance_uids,
    )
    _extend_datasets(
        resulting_datasets_right,
        -1,
        number_of_slices_to_add,
        series_instance_uid=final_series_uid,
        sop_instance_uids=final_sop_instance_uids,
    )

    assert resulting_datasets_left != initial_datasets
    assert resulting_datasets_left == expected_datasets_left

    assert resulting_datasets_right != initial_datasets
    assert resulting_datasets_right == expected_datasets_right


def _make_datasets(series_instance_uid, sop_instance_uids, slice_locations):
    initial_datasets = [
        dicom_dataset_from_dict(
            {
                "SeriesInstanceUID": series_instance_uid,
                "SOPInstanceUID": sop_instance_uid,
                "InstanceNumber": str(i),
                "SliceLocation": str(float(slice_location)),
                "ImagePositionPatient": ["0.0", "0.0", str(float(slice_location))],
                "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
                "PatientPosition": "HFS",
            }
        )
        for i, (sop_instance_uid, slice_location) in enumerate(
            zip(sop_instance_uids, slice_locations)
        )
    ]

    return _convert_datasets_to_deque(initial_datasets)
