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


import numpy as np

from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.structure import (
    pull_structure,
    create_contour_sequence_dict,
    Structure,
)


A_STRUCTURE = Structure(
    "A Structure Name",
    10,
    [
        [[0, 1, 2, 0], [2, 3, 4, 2], [5, 5, 5, 5]],
        [[0, 1, 2, 0], [2, 3, 4, 2], [6, 6, 6, 6]],
        [[0, 1, 2, 0], [2, 3, 4, 2], [7, 7, 7, 7]],
    ],
)

ANOTHER_STRUCTURE = Structure(
    "Another Structure Name",
    1,
    [
        [[5, 6, 3, 5], [7, 7, 5, 7], [1, 1, 1, 1]],
        [[5, 6, 3, 5], [7, 7, 5, 7], [2, 2, 2, 2]],
        [[5, 6, 3, 5], [7, 7, 5, 7], [3, 3, 3, 3]],
    ],
)


def test_pull_structure():
    dicom_structure = dicom_dataset_from_dict(
        {
            "StructureSetROISequence": [
                {"ROIName": A_STRUCTURE.name, "ROINumber": A_STRUCTURE.number},
                {
                    "ROIName": ANOTHER_STRUCTURE.name,
                    "ROINumber": ANOTHER_STRUCTURE.number,
                },
            ],
            "ROIContourSequence": [
                # Sequence purposely placed in reverse order to ensure ROI
                # number is being used and not list order.
                create_contour_sequence_dict(ANOTHER_STRUCTURE),
                create_contour_sequence_dict(A_STRUCTURE),
            ],
        }
    )

    x, y, z = pull_structure(A_STRUCTURE.name, dicom_structure)

    assert np.all(x == np.array(A_STRUCTURE.coords)[:, 0, :])
    assert np.all(y == np.array(A_STRUCTURE.coords)[:, 1, :])
    assert np.all(z == np.array(A_STRUCTURE.coords)[:, 2, :])
