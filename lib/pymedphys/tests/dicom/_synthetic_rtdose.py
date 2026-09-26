# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Synthetic RT Dose datasets with independently known geometry.

The expected coordinates come straight from the DICOM definition of a voxel's
position (PS3.3 C.7.6.2.1.1 and C.8.8.3.2), not from the code under test:

    position(k, i, j) = IPP + j * column_spacing * r + i * row_spacing * c
                        + offset[k] * (r x c)

where ``r`` and ``c`` are the row and column direction cosines of Image
Orientation (Patient), ``j`` indexes columns, ``i`` rows and ``k`` slices.
"""

from pymedphys._imports import numpy as np

from pymedphys._dicom import create

ORIENTATIONS = {
    "FFDL": (0, 1, 0, 1, 0, 0),
    "FFDR": (0, -1, 0, -1, 0, 0),
    "FFP": (1, 0, 0, 0, -1, 0),
    "FFS": (-1, 0, 0, 0, 1, 0),
    "HFDL": (0, -1, 0, 1, 0, 0),
    "HFDR": (0, 1, 0, -1, 0, 0),
    "HFP": (-1, 0, 0, 0, -1, 0),
    "HFS": (1, 0, 0, 0, 1, 0),
}

DOSE_GRID_SCALING = 1e-4


def rtdose(
    orientation,
    *,
    position=(100.0, -200.0, 300.0),
    shape=(3, 4, 5),
    pixel_spacing=(2.0, 3.0),
    slice_offsets=None,
    pixel_values=None,
):
    """Build an RT Dose dataset.

    ``shape`` is (slices, rows, columns) and ``pixel_spacing`` is the DICOM
    (row spacing, column spacing) pair. By default every voxel holds a
    distinct value, so a test can tell which voxel ended up where.
    """
    slices, rows, columns = shape
    if slice_offsets is None:
        slice_offsets = [2.5 * k for k in range(slices)]
    if pixel_values is None:
        pixel_values = np.arange(slices * rows * columns).reshape(shape)
    pixel_values = np.asarray(pixel_values, dtype=np.uint32)

    return create.dicom_dataset_from_dict(
        {
            "Modality": "RTDOSE",
            "ImagePositionPatient": list(position),
            "ImageOrientationPatient": list(ORIENTATIONS[orientation]),
            "PixelSpacing": list(pixel_spacing),
            "GridFrameOffsetVector": list(slice_offsets),
            "Rows": rows,
            "Columns": columns,
            "NumberOfFrames": slices,
            "BitsAllocated": 32,
            "BitsStored": 32,
            "HighBit": 31,
            "PixelRepresentation": 0,
            "SamplesPerPixel": 1,
            "PhotometricInterpretation": "MONOCHROME2",
            "DoseGridScaling": DOSE_GRID_SCALING,
            "DoseUnits": "GY",
            "DoseType": "PHYSICAL",
            "DoseSummationType": "PLAN",
            "PixelData": pixel_values.tobytes(),
        }
    )


def voxel_positions(ds):
    """Return the (slices, rows, columns, 3) DICOM position of every voxel."""
    position = np.array(ds.ImagePositionPatient, dtype=float)
    orientation = np.array(ds.ImageOrientationPatient, dtype=float)
    r, c = orientation[:3], orientation[3:]
    n = np.cross(r, c)
    row_spacing, column_spacing = (float(s) for s in ds.PixelSpacing)

    # A single-valued element reads as a scalar.
    offsets = np.atleast_1d(np.array(ds.GridFrameOffsetVector, dtype=float))
    if offsets[0] != 0:
        # Absolute slice positions (PS3.3 C.8.8.3.2), only valid for n = +z
        offsets = offsets - position[2]

    # Independent homogeneous matrix implementation of the standard. The
    # third input is the actual slice displacement, so uneven spacing works.
    transform = np.eye(4)
    transform[:3, 0] = column_spacing * r
    transform[:3, 1] = row_spacing * c
    transform[:3, 2] = n
    transform[:3, 3] = position
    # Apply the matrix one plane at a time to keep temporary allocations
    # small for the real-file tests that also use this reference calculation.
    indices = np.ones((ds.Rows, ds.Columns, 4))
    indices[..., 0] = np.arange(ds.Columns)
    indices[..., 1] = np.arange(ds.Rows)[:, None]
    positions = np.empty((len(offsets), ds.Rows, ds.Columns, 3))
    for slice_index, offset in enumerate(offsets):
        indices[..., 2] = offset
        positions[slice_index] = (indices @ transform.T)[..., :3]
    return positions
