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


import pytest

import numpy as np

from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.structure import (
    Structure,
    create_contour_sequence_dict,
    pull_structure,
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


@pytest.mark.pydicom
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
