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

import pytest

from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.ct.extend import (
    convert_datasets_to_deque,
    extend_datasets,
    generate_uids,
)


def make_datasets(uuids, slice_locations):
    initial_datasets = [
        dicom_dataset_from_dict(
            {
                "SOPInstanceUID": uuid,
                "InstanceNumber": str(i),
                "SliceLocation": str(float(slice_location)),
                "ImagePositionPatient": ["0.0", "0.0", str(float(slice_location))],
            }
        )
        for i, (uuid, slice_location) in enumerate(zip(uuids, slice_locations))
    ]

    return convert_datasets_to_deque(initial_datasets)


@pytest.mark.pydicom
def test_extend_datasets():
    initial_uuids = generate_uids(4)
    final_uuids = generate_uids(7)

    number_of_slices_to_add = 3
    initial_slice_locations = [1, 3, 5, 7]
    expected_slice_locations_left = [-5, -3, -1, 1, 3, 5, 7]
    expected_slice_locations_right = [1, 3, 5, 7, 9, 11, 13]

    initial_datasets = make_datasets(initial_uuids, initial_slice_locations)
    expected_datasets_left = make_datasets(final_uuids, expected_slice_locations_left)
    expected_datasets_right = make_datasets(final_uuids, expected_slice_locations_right)

    resulting_dataset_left = deepcopy(initial_datasets)
    resulting_dataset_right = deepcopy(initial_datasets)

    extend_datasets(
        resulting_dataset_left, 0, number_of_slices_to_add, uids=final_uuids
    )
    extend_datasets(
        resulting_dataset_right, -1, number_of_slices_to_add, uids=final_uuids
    )

    assert resulting_dataset_left != initial_datasets
    assert resulting_dataset_left == expected_datasets_left

    assert resulting_dataset_right != initial_datasets
    assert resulting_dataset_right == expected_datasets_right


@pytest.mark.pydicom
def test_out_of_order():
    initial_uuids = generate_uids(4)
    final_uuids = generate_uids(7)

    number_of_slices_to_add = 3
    initial_slice_locations = [7, 3, 1, 5]
    expected_slice_locations = [-5, -3, -1, 1, 3, 5, 7]

    initial_datasets = make_datasets(initial_uuids, initial_slice_locations)
    expected_datasets = make_datasets(final_uuids, expected_slice_locations)

    resulting_dataset = deepcopy(initial_datasets)

    extend_datasets(resulting_dataset, 0, number_of_slices_to_add, uids=final_uuids)

    assert resulting_dataset != initial_datasets
    assert resulting_dataset == expected_datasets
