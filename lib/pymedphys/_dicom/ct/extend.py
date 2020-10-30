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


import datetime
import os
import random
from collections import deque
from copy import deepcopy
from glob import glob

from pymedphys._imports import pydicom

from pymedphys._dicom.constants.uuid import PYMEDPHYS_ROOT_UID


def extend_in_both_directions(input_dir, output_dir, number_of_slices=20):
    filepaths = glob(os.path.join(input_dir, "*"))
    dicom_datasets = load_dicom_into_deque(filepaths)
    extend_datasets(dicom_datasets, 0, number_of_slices)
    extend_datasets(dicom_datasets, -1, number_of_slices)

    common_prefix = get_common_prefix(filepaths)
    save_files(dicom_datasets, common_prefix, output_dir)


def save_files(dicom_datasets, common_prefix, output_dir):
    number_of_digits = len(str(len(dicom_datasets)))
    new_filenames = [
        "{}{}.dcm".format(
            common_prefix, str(dicom_dataset.InstanceNumber).zfill(number_of_digits)
        )
        for dicom_dataset in dicom_datasets
    ]

    new_filepaths = [os.path.join(output_dir, filename) for filename in new_filenames]

    for dicom_dataset, filepath in zip(dicom_datasets, new_filepaths):
        dicom_dataset.save_as(filepath)


def get_common_prefix(filepaths):
    filenames = [os.path.basename(filepath) for filepath in filepaths]
    common_prefix = os.path.commonprefix(filenames)

    return common_prefix


def extend(input_dir, output_dir, index_to_copy, number_of_slices):
    filepaths = glob(os.path.join(input_dir, "*"))
    dicom_datasets = load_dicom_into_deque(filepaths)
    extend_datasets(dicom_datasets, index_to_copy, number_of_slices)

    common_prefix = get_common_prefix(filepaths)
    save_files(dicom_datasets, common_prefix, output_dir)


def extend_datasets(dicom_datasets, index_to_copy, number_of_slices, uids=None):
    copy_slices_and_append(dicom_datasets, index_to_copy, number_of_slices)
    refresh_instance_numbers(dicom_datasets)
    generate_new_uids(dicom_datasets, uids=uids)


def load_dicom_into_deque(filepaths):
    dicom_datasets_initial_read = [
        pydicom.dcmread(filepath, force=True) for filepath in filepaths
    ]

    dicom_datasets = convert_datasets_to_deque(dicom_datasets_initial_read)

    return dicom_datasets


def convert_datasets_to_deque(datasets):
    dicom_datasets = deque()

    for dicom_dataset in sorted(datasets, key=slice_location):
        dicom_datasets.append(dicom_dataset)

    return dicom_datasets


def instance_number(dicom_dataset):
    return dicom_dataset.InstanceNumber


def slice_location(dicom_dataset):
    return float(dicom_dataset.SliceLocation)


def copy_slices_and_append(dicom_datasets, index_to_copy, number_of_slices):
    append_method = get_append_method(dicom_datasets, index_to_copy)
    new_slice_locations = generate_new_slice_locations(
        dicom_datasets, index_to_copy, number_of_slices
    )

    dataset_to_copy = deepcopy(dicom_datasets[index_to_copy])

    append = getattr(dicom_datasets, append_method)

    for a_slice_location in new_slice_locations:
        new_slice = deepcopy(dataset_to_copy)

        new_slice.SliceLocation = str(a_slice_location)

        image_position_patient_to_copy = deepcopy(
            dicom_datasets[index_to_copy].ImagePositionPatient
        )
        image_position_patient_to_copy[-1] = str(a_slice_location)
        new_slice.ImagePositionPatient = image_position_patient_to_copy

        append(new_slice)


def refresh_instance_numbers(dicom_datasets):
    for i, dicom_dataset in enumerate(dicom_datasets):
        dicom_dataset.InstanceNumber = str(i)


def generate_new_uids(dicom_datasets, uids=None):
    if uids is None:
        uids = generate_uids(len(dicom_datasets))

    for dicom_dataset, uid in zip(dicom_datasets, uids):
        dicom_dataset.SOPInstanceUID = uid


def generate_new_slice_locations(dicom_datasets, index_to_copy, number_of_slices):
    if index_to_copy == 0:
        slice_diff = dicom_datasets[0].SliceLocation - dicom_datasets[1].SliceLocation
    elif index_to_copy == len(dicom_datasets) or index_to_copy == -1:
        slice_diff = dicom_datasets[-1].SliceLocation - dicom_datasets[-2].SliceLocation
    else:
        raise ValueError("index_to_copy must be first or last slice")

    new_slice_locations = [dicom_datasets[index_to_copy].SliceLocation + slice_diff]
    for _ in range(number_of_slices - 1):
        new_slice_locations.append(new_slice_locations[-1] + slice_diff)

    return new_slice_locations


def get_append_method(dicom_datasets, index_to_copy):
    if index_to_copy == 0:
        return "appendleft"

    if index_to_copy == len(dicom_datasets) or index_to_copy == -1:
        return "append"

    raise ValueError("index_to_copy must be first or last slice")


def generate_uids(number_of_uids, randomisation_length=10, root=PYMEDPHYS_ROOT_UID):
    num_of_digits = len(str(number_of_uids))

    middle_item = str(random.randint(0, 10 ** randomisation_length)).zfill(
        randomisation_length
    )
    time_stamp_item = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")

    last_item = [str(i).zfill(num_of_digits) for i in range(number_of_uids)]

    uids = [".".join([root, middle_item, time_stamp_item, item]) for item in last_item]

    return uids
