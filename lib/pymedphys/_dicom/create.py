# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
from copy import deepcopy

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom


@functools.lru_cache(maxsize=1)
def get_dicom_names():
    DICOM_NAMES = [item[-1] for _, item in pydicom.datadict.DicomDictionary.items()]

    return DICOM_NAMES


def add_array_to_dataset(dataset, key, value):
    if isinstance(value, np.ndarray):
        value = value.tolist()
    setattr(dataset, key, value)


def set_default_transfer_syntax(dataset):
    if dataset.is_little_endian is None:
        dataset.is_little_endian = True

    if dataset.is_implicit_VR is None:
        dataset.is_implicit_VR = True


def dicom_dataset_from_dict(input_dict: dict, template_ds=None):
    """Create a pydicom DICOM object from a dictionary"""
    if template_ds is None:
        dataset = pydicom.Dataset()
    else:
        dataset = deepcopy(template_ds)

    for key, value in input_dict.items():
        if key not in get_dicom_names():
            raise ValueError("{} is not within the DICOM dictionary.".format(key))

        if isinstance(value, dict):
            setattr(dataset, key, dicom_dataset_from_dict(value))
        elif isinstance(value, list):
            # TODO: Check for DICOM SQ type on this attribute
            if np.all([not isinstance(item, dict) for item in value]):
                add_array_to_dataset(dataset, key, value)
            elif np.all([isinstance(item, dict) for item in value]):
                setattr(dataset, key, [dicom_dataset_from_dict(item) for item in value])
            else:
                raise ValueError(
                    "{} should contain either only dictionaries, or no "
                    "dictionaries".format(key)
                )
        else:
            add_array_to_dataset(dataset, key, value)

    set_default_transfer_syntax(dataset)

    return dataset


# def structure
