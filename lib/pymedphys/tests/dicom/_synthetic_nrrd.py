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

"""NRRD files of the analytic head and of masks of its organs, and ZIP
files of them laid out as HaN-Seg's, for the face block check's tests.
Every value here is invented."""

from __future__ import annotations

import bz2
import dataclasses
import gzip
import zipfile
from collections.abc import Mapping, Sequence

from pymedphys._imports import numpy as np

from . import _synthetic_head as head

LPS = "left-posterior-superior"
RAS = "right-anterior-superior"
# The NRRD type of each NumPy type.
TYPES = {
    "int8": "int8",
    "uint8": "uchar",
    "int16": "short",
    "uint16": "ushort",
    "int32": "int",
    "uint32": "uint",
    "int64": "int64",
    "uint64": "uint64",
    "float32": "float",
    "float64": "double",
}
# Coarser than the finder's own tests, as the face block tests' scan is.
SCAN = head.axial(
    spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (-60, 120))
)
# Where each eye's anterior segment ends, in y: its part in front of this.
EYE_FRONT = head.GLOBE_Y - 6.0


@dataclasses.dataclass(frozen=True)
class Grid:
    """Where a volume's voxels lie, in DICOM's patient coordinates.

    ``axes`` are three rows, one step along the columns, the rows, and the
    slices, so that the voxel at slice ``k``, row ``j``, and column ``i``
    is at ``origin + i * axes[0] + j * axes[1] + k * axes[2]``.
    """

    origin: tuple[float, float, float]
    axes: tuple[tuple[float, float, float], ...]
    shape: tuple[int, int, int]  # slices, rows, columns

    def points(self) -> np.ndarray:
        """The x, y, and z of each voxel, by slice, row, and column."""
        k, j, i = np.indices(self.shape)
        axes = np.asarray(self.axes, dtype=float)
        return (
            np.asarray(self.origin, dtype=float)
            + i[..., np.newaxis] * axes[0]
            + j[..., np.newaxis] * axes[1]
            + k[..., np.newaxis] * axes[2]
        )


def grid_of(scan: head.Scan) -> Grid:
    """The grid of an axial scan's slices, in order."""
    along_row = np.array(scan.orientation[:3]) * scan.spacing[1]
    down_column = np.array(scan.orientation[3:]) * scan.spacing[0]
    across = np.array(scan.positions[1]) - np.array(scan.positions[0])
    return Grid(
        tuple(float(v) for v in scan.positions[0]),
        tuple(
            tuple(float(v) for v in each) for each in (along_row, down_column, across)
        ),
        (len(scan.positions), *scan.shape),
    )


def ct_values(scan: head.Scan, *heads: head.Head) -> np.ndarray:
    """The scan of the heads, in Hounsfield units, rounded, by slice, row,
    and column."""
    return np.rint(np.stack(list(scan.slices(*heads)))).astype(np.int16)


def eye_masks(
    grid: Grid, shift: Sequence[float] = (0.0, 0.0, 0.0)
) -> dict[str, np.ndarray]:
    """The analytic head's eyes, each in two parts, as HaN-Seg names them:
    ``Eye_A`` the part in front of :data:`EYE_FRONT`, and ``Eye_P`` the
    rest, ``R`` the patient's right and ``L`` their left, moved by
    ``shift``."""
    points = grid.points() - np.asarray(shift, dtype=float)
    masks = {}
    for side, name in ((-1, "R"), (1, "L")):
        centre = np.array([side * head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z])
        globe = np.sum((points - centre) ** 2, axis=-1) <= head.GLOBE_RADIUS**2
        front = points[..., 1] < EYE_FRONT
        masks[f"Eye_A{name}"] = globe & front
        masks[f"Eye_P{name}"] = globe & ~front
    return masks


def organ_masks(grid: Grid) -> dict[str, np.ndarray]:
    """Three more organs: the lips, below the block; the brainstem, behind
    it; and the right lacrimal gland, in front of the right globe and above
    it, within the block."""
    points = grid.points()

    def ball(centre: Sequence[float], radius: float) -> np.ndarray:
        return np.sum((points - np.asarray(centre)) ** 2, axis=-1) <= radius**2

    return {
        "Lips": ball((0.0, -84.0, -40.0), 5.0),
        "Brainstem": ball((0.0, 20.0, -10.0), 12.0),
        "Glnd_Lacrimal_R": ball((-45.0, -70.0, 32.0), 4.0),
    }


def nrrd_file(
    values: np.ndarray,
    grid: Grid,
    *,
    space: str = LPS,
    encoding: str = "gzip",
    endian: str = "little",
    key_values: Mapping[str, str] | None = None,
    layered: bool = False,
) -> bytes:
    """An NRRD file of the values, by slice, row, and column, with the
    layers of a segmentation last where ``layered``, on the grid, which is
    in DICOM's patient coordinates; ``space`` is the file's, and the file
    gives the grid's origin and axes in it."""
    values = np.asarray(values)
    signs = np.array({LPS: (1, 1, 1), RAS: (-1, -1, 1)}[space], dtype=float)
    origin = np.asarray(grid.origin) * signs
    axes = np.asarray(grid.axes) * signs
    directions = " ".join(
        f"({','.join(repr(float(v)) for v in each)})" for each in axes
    )
    if layered:
        directions = "none " + directions
    lines = [
        "NRRD0004",
        "# Complete NRRD file format specification at:",
        "# http://teem.sourceforge.net/nrrd/format.html",
        f"type: {TYPES[values.dtype.name]}",
        f"dimension: {values.ndim}",
        f"space: {space}",
        "sizes: " + " ".join(str(size) for size in values.shape[::-1]),
        f"space directions: {directions}",
        "kinds: " + ("list " if layered else "") + "domain domain domain",
        f"endian: {endian}",
        f"encoding: {encoding}",
        f"space origin: ({','.join(repr(float(v)) for v in origin)})",
        *(f"{key}:={value}" for key, value in (key_values or {}).items()),
    ]
    order = "<" if endian == "little" else ">"
    data = values.astype(values.dtype.newbyteorder(order)).tobytes()
    encoded = {
        "raw": lambda: data,
        "gzip": lambda: gzip.compress(data),
        "bzip2": lambda: bz2.compress(data),
    }[encoding]()
    return ("\n".join(lines) + "\n\n").encode("ascii") + encoded


def segment_file(mask: np.ndarray, grid: Grid, **options) -> bytes:
    """An NRRD file of one segment, as 3D Slicer writes one, of label value
    1 in layer 0."""
    key_values = {
        "Segment0_ID": "Segment_1",
        "Segment0_LabelValue": "1",
        "Segment0_Layer": "0",
        "Segment0_Name": "Segment_1",
    }
    return nrrd_file(mask.astype(np.uint8), grid, key_values=key_values, **options)


def cropped(mask: np.ndarray, grid: Grid) -> tuple[np.ndarray, Grid]:
    """A mask cut to the box of its voxels, with that box's grid."""
    present = np.argwhere(mask)
    low, high = present.min(axis=0), present.max(axis=0) + 1
    axes = np.asarray(grid.axes)
    origin = np.asarray(grid.origin) + low[::-1] @ axes
    box = mask[low[0] : high[0], low[1] : high[1], low[2] : high[2]]
    return box, Grid(tuple(float(v) for v in origin), grid.axes, box.shape)


def finer(mask: np.ndarray, grid: Grid) -> tuple[np.ndarray, Grid]:
    """A mask on a grid of twice as many voxels along each axis, each
    voxel's eight centred on its own."""
    axes = np.asarray(grid.axes) / 2
    origin = np.asarray(grid.origin) - axes.sum(axis=0) / 2
    fine = mask.repeat(2, axis=0).repeat(2, axis=1).repeat(2, axis=2)
    return fine, Grid(
        tuple(float(v) for v in origin),
        tuple(tuple(float(v) for v in each) for each in axes),
        fine.shape,
    )


def coronal(values: np.ndarray, grid: Grid) -> tuple[np.ndarray, Grid]:
    """An axial volume stored as coronal slices: columns along x, rows from
    superior down, and slices from anterior back."""
    axes = np.asarray(grid.axes)
    top = np.asarray(grid.origin) + (grid.shape[0] - 1) * axes[2]
    stored = np.transpose(values, (1, 0, 2))[:, ::-1, :]
    return np.ascontiguousarray(stored), Grid(
        tuple(float(v) for v in top),
        tuple(tuple(float(v) for v in each) for each in (axes[0], -axes[2], axes[1])),
        stored.shape,
    )


def hanseg_zip(path, cases: Mapping[str, Mapping[str, bytes]]) -> None:
    """A ZIP file laid out as HaN-Seg's, of each case's files by their name
    after ``case_NN_``, such as ``IMG_CT.nrrd``, under ``HaN-Seg/set_1/``."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("HaN-Seg/README.md", "# HaN-Seg\n")
        for case, files in cases.items():
            for name, data in files.items():
                archive.writestr(f"HaN-Seg/set_1/{case}/{case}_{name}", data)
