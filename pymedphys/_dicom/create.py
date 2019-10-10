# Copyright (C) 2019 Simon Biggs

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

import numpy as np

import pydicom

DICOM_NAMES = [item[-1] for _, item in pydicom.datadict.DicomDictionary.items()]


def add_array_to_dataset(dataset, key, value):
    if isinstance(value, np.ndarray):
        value = value.tolist()
    setattr(dataset, key, value)


def dicom_dataset_from_dict(input_dict: dict, template_ds=None):
    """Create a pydicom DICOM object from a dictionary"""
    if template_ds is None:
        dataset = pydicom.Dataset()
    else:
        dataset = deepcopy(template_ds)

    for key, value in input_dict.items():
        if key not in DICOM_NAMES:
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

    return dataset


# def structure
