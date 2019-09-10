# Copyright (C) 2019 Cancer Care Associates
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


from copy import deepcopy

from pymedphys_dicom.dicom.create import dicom_dataset_from_dict
from pymedphys_dicom.ct.extend import (
    extend_datasets, generate_uids, convert_datasets_to_deque)


def make_datasets(uuids, slice_locations):
    initial_datasets = [
        dicom_dataset_from_dict({
            'SOPInstanceUID': uuid,
            'InstanceNumber': str(i),
            'SliceLocation': str(float(slice_location)),
            'ImagePositionPatient': ['0.0', '0.0', str(float(slice_location))]
        })
        for i, (uuid, slice_location)
        in enumerate(zip(uuids, slice_locations))
    ]

    return convert_datasets_to_deque(initial_datasets)


def test_extend_datasets():
    initial_uuids = generate_uids(4)
    final_uuids = generate_uids(7)

    number_of_slices_to_add = 3
    initial_slice_locations = [1, 3, 5, 7]
    expected_slice_locations_left = [-5, -3, -1, 1, 3, 5, 7]
    expected_slice_locations_right = [1, 3, 5, 7, 9, 11, 13]

    initial_datasets = make_datasets(initial_uuids, initial_slice_locations)
    expected_datasets_left = make_datasets(
        final_uuids, expected_slice_locations_left)
    expected_datasets_right = make_datasets(
        final_uuids, expected_slice_locations_right)

    resulting_dataset_left = deepcopy(initial_datasets)
    resulting_dataset_right = deepcopy(initial_datasets)

    extend_datasets(
        resulting_dataset_left, 0, number_of_slices_to_add, uids=final_uuids)
    extend_datasets(
        resulting_dataset_right, -1, number_of_slices_to_add, uids=final_uuids)

    assert resulting_dataset_left != initial_datasets
    assert resulting_dataset_left == expected_datasets_left

    assert resulting_dataset_right != initial_datasets
    assert resulting_dataset_right == expected_datasets_right


def test_out_of_order():
    initial_uuids = generate_uids(4)
    final_uuids = generate_uids(7)

    number_of_slices_to_add = 3
    initial_slice_locations = [7, 3, 1, 5]
    expected_slice_locations = [-5, -3, -1, 1, 3, 5, 7]

    initial_datasets = make_datasets(initial_uuids, initial_slice_locations)
    expected_datasets = make_datasets(final_uuids, expected_slice_locations)

    resulting_dataset = deepcopy(initial_datasets)

    extend_datasets(
        resulting_dataset, 0, number_of_slices_to_add, uids=final_uuids)

    assert resulting_dataset != initial_datasets
    assert resulting_dataset == expected_datasets
