# Copyright (C) 2018-2021, 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import copy

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom import coords, create


@pytest.mark.pydicom
def test_coords_in_datasets_are_equal():
    bits_allocated = 32

    ds1 = create.dicom_dataset_from_dict(
        {
            "ImagePositionPatient": [-1.0, -1.0, -1.0],
            "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
            "BitsAllocated": bits_allocated,
            "BitsStored": bits_allocated,
            "Rows": 3,
            "Columns": 3,
            "NumberOfFrames": 3,
            "PixelRepresentation": 0,
            "SamplesPerPixel": 1,
            "PhotometricInterpretation": "MONOCHROME2",
            "PixelSpacing": [1.0, 1.0],
            "GridFrameOffsetVector": [0.0, 1.0, 2.0],
            "PixelData": np.ones((3, 3, 3), dtype="<u4").tobytes(),
        }
    )

    ds2 = copy.deepcopy(ds1)
    assert coords.coords_in_datasets_are_equal([ds1, ds2])

    # The transfer syntax declared by dicom_dataset_from_dict survives the copy
    assert ds2.file_meta.TransferSyntaxUID == ds1.file_meta.TransferSyntaxUID

    # only one coords supplied:
    assert coords.coords_in_datasets_are_equal([ds1])

    # y-shift (for DICOM HFS)
    ds2.ImagePositionPatient = [-1.0, -1.1, -1.0]
    with pytest.warns(UserWarning, match="0.1 mm acceptance limit"):
        assert coords.coords_in_datasets_are_equal([ds1, ds2])
    ds2.ImagePositionPatient = [-1.0, -1.11, -1.0]
    assert not coords.coords_in_datasets_are_equal([ds1, ds2])

    # same coords but rotated using IOP
    # (so mapping to PixelData would be incorrect)
    ds2.ImagePositionPatient = [-1.0, 1.0, 1.0]
    ds2.ImageOrientationPatient = [1.0, 0, 0, 0, -1, 0]
    assert not coords.coords_in_datasets_are_equal([ds1, ds2])

    # same coords but rotated using GFOV
    # (so mapping to PixelData would be incorrect)
    ds2.ImagePositionPatient = [-1.0, -1.0, 1.0]
    ds2.ImageOrientationPatient = [1.0, 0, 0, 0, 1, 0]
    ds2.GridFrameOffsetVector = [0, -1, -2]
    assert not coords.coords_in_datasets_are_equal([ds1, ds2])
