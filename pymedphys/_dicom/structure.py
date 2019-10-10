# Copyright (C) 2018 Cancer Care Associates

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


import operator
from collections import namedtuple
from functools import reduce

import numpy as np

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


def pull_structure(structure_name, dcm_struct):
    ROI_name_to_number_map = {
        structure_set.ROIName: structure_set.ROINumber
        for structure_set in dcm_struct.StructureSetROISequence
    }

    ROI_number_to_contour_map = {
        contour.ReferencedROINumber: contour.ContourSequence
        for contour in dcm_struct.ROIContourSequence
    }

    try:
        ROI_number = ROI_name_to_number_map[structure_name]
    except KeyError:
        raise ValueError("Structure name not found (case sensitive)")

    contour_sequence = ROI_number_to_contour_map[ROI_number]
    x, y, z = pull_coords_from_contour_sequence(contour_sequence)

    return x, y, z


def list_structures(dcm_struct):
    return [item.ROIName for item in dcm_struct.StructureSetROISequence]
