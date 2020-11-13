# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import operator
from collections import namedtuple
from functools import reduce

from pymedphys._imports import numpy as np

# pylint: disable=C0103


Structure = namedtuple("Structure", ["name", "number", "coords"])


def concatenate_a_contour_slice(x, y, z):
    return reduce(
        operator.add, [[str(x_i), str(y_i), str(z_i)] for x_i, y_i, z_i in zip(x, y, z)]
    )


def create_contour_sequence_dict(structure: Structure):
    merged_contours = [
        concatenate_a_contour_slice(x, y, z) for x, y, z in structure.coords
    ]

    return {
        "ReferencedROINumber": structure.number,
        "ContourSequence": [
            {"ContourData": merged_contour} for merged_contour in merged_contours
        ],
    }


def pull_coords_from_contour_sequence(contour_sequence):
    contours_by_slice_raw = [item.ContourData for item in contour_sequence]

    x = [np.array(item[0::3]) for item in contours_by_slice_raw]
    y = [np.array(item[1::3]) for item in contours_by_slice_raw]
    z = [np.array(item[2::3]) for item in contours_by_slice_raw]

    return x, y, z


def get_roi_contour_sequence_by_name(structure_name, dcm_struct):
    ROI_name_to_number_map = {
        structure_set.ROIName: structure_set.ROINumber
        for structure_set in dcm_struct.StructureSetROISequence
    }

    ROI_number_to_contour_map = {
        contour.ReferencedROINumber: contour
        for contour in dcm_struct.ROIContourSequence
    }

    try:
        ROI_number = ROI_name_to_number_map[structure_name]
    except KeyError:
        raise ValueError("Structure name not found (case sensitive)")

    roi_contour_sequence = ROI_number_to_contour_map[ROI_number]

    return roi_contour_sequence


def pull_structure(structure_name, dcm_struct):
    roi_contour_sequence = get_roi_contour_sequence_by_name(structure_name, dcm_struct)
    contour_sequence = roi_contour_sequence.ContourSequence

    x, y, z = pull_coords_from_contour_sequence(contour_sequence)

    return x, y, z


def list_structures(dcm_struct):
    return [item.ROIName for item in dcm_struct.StructureSetROISequence]
