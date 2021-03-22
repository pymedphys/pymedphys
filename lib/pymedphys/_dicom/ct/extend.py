# Copyright (C) 2019,2021 Cancer Care Associates
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import collections
import copy
from typing import Deque, List

from pymedphys._imports import pydicom  # pylint: disable = unused-import

from pymedphys._dicom import orientation, uid


def extend(
    ct_series: List["pydicom.Dataset"], number_of_slices: int
) -> Deque["pydicom.Dataset"]:
    """Duplicates the superior and inferior slices of a CT Series.

    Only HFS orientations are currently supported.

    Parameters
    ----------
    ct_series : List[pydicom.Dataset]
        The CT series to be extended.
    number_of_slices : int
        The number of slices to append onto both the superior and
        inferior end of the Series.

    Returns
    -------
    Deque[pydicom.Dataset]
        The extended CT series.
    """

    for ds in ct_series:
        orientation.require_patient_orientation(ds, "HFS")

    sorted_ct_series = _convert_datasets_to_deque(ct_series)
    _extend_datasets(sorted_ct_series, 0, number_of_slices)
    _extend_datasets(sorted_ct_series, -1, number_of_slices)

    return sorted_ct_series


def _extend_datasets(dicom_datasets, index_to_copy, number_of_slices, uids=None):
    _copy_slices_and_append(dicom_datasets, index_to_copy, number_of_slices)
    _refresh_instance_numbers(dicom_datasets)
    _generate_new_uids(dicom_datasets, uids=uids)


def _convert_datasets_to_deque(datasets) -> Deque["pydicom.Dataset"]:
    dicom_datasets: Deque[pydicom.Dataset] = collections.deque()

    for dicom_dataset in sorted(datasets, key=_slice_location):
        dicom_datasets.append(dicom_dataset)

    return dicom_datasets


def _slice_location(dicom_dataset):
    return float(dicom_dataset.ImagePositionPatient[-1])


def _copy_slices_and_append(dicom_datasets, index_to_copy, number_of_slices):
    append_method = _get_append_method(dicom_datasets, index_to_copy)
    new_slice_locations = _generate_new_slice_locations(
        dicom_datasets, index_to_copy, number_of_slices
    )

    dataset_to_copy = copy.deepcopy(dicom_datasets[index_to_copy])

    append = getattr(dicom_datasets, append_method)

    for a_slice_location in new_slice_locations:
        new_slice = copy.deepcopy(dataset_to_copy)

        new_slice.SliceLocation = str(a_slice_location)

        image_position_patient_to_copy = copy.deepcopy(
            dicom_datasets[index_to_copy].ImagePositionPatient
        )
        image_position_patient_to_copy[-1] = str(a_slice_location)
        new_slice.ImagePositionPatient = image_position_patient_to_copy

        append(new_slice)


def _refresh_instance_numbers(dicom_datasets):
    for i, dicom_dataset in enumerate(dicom_datasets):
        dicom_dataset.InstanceNumber = str(i)


def _generate_new_uids(dicom_datasets, uids=None):
    if uids is None:
        uids = _generate_uids(len(dicom_datasets))

    for dicom_dataset, uid in zip(dicom_datasets, uids):
        dicom_dataset.SOPInstanceUID = uid


def _generate_new_slice_locations(dicom_datasets, index_to_copy, number_of_slices):
    if index_to_copy == 0:
        slice_diff = (
            dicom_datasets[0].ImagePositionPatient[-1]
            - dicom_datasets[1].ImagePositionPatient[-1]
        )
    elif index_to_copy == len(dicom_datasets) or index_to_copy == -1:
        slice_diff = (
            dicom_datasets[-1].ImagePositionPatient[-1]
            - dicom_datasets[-2].ImagePositionPatient[-1]
        )
    else:
        raise ValueError("index_to_copy must be first or last slice")

    new_slice_locations = [
        dicom_datasets[index_to_copy].ImagePositionPatient[-1] + slice_diff
    ]
    for _ in range(number_of_slices - 1):
        new_slice_locations.append(new_slice_locations[-1] + slice_diff)

    return new_slice_locations


def _get_append_method(dicom_datasets, index_to_copy):
    if index_to_copy == 0:
        return "appendleft"

    if index_to_copy == len(dicom_datasets) or index_to_copy == -1:
        return "append"

    raise ValueError("index_to_copy must be first or last slice")


def _generate_uids(number_of_uids):
    uids = [uid.generate_uid() for _ in range(number_of_uids)]

    return uids
