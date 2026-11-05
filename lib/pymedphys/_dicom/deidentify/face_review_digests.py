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

"""Byte layouts for reviewed pixel, contour and deformation-grid digests.

The face-review entry points pass their existing DICOM tags to these
helpers. Digest bytes, padding, ordering and error handling stay together
here; verdict and release decisions remain in the face review.
"""

from __future__ import annotations

import hashlib
import struct

from pymedphys._imports import pydicom


def pixel_data_sha256(
    dataset: pydicom.Dataset, pixel_data_tags: tuple[int, ...]
) -> bytes:
    """Return the SHA-256 of a data set's top-level pixel data.

    The digest is of the value field of each of Float Pixel Data
    (7FE0,0008), Double Float Pixel Data (7FE0,0009), and Pixel Data
    (7FE0,0010) that the data set holds, in that order, each after its tag
    and the value's length, so that the same bytes under another of these
    tags differ. A value of odd length is taken with the trailing null byte
    that a file writes to make it even. Encapsulated Pixel Data is taken as
    its items. A data set with none of them, such as an RT Structure Set's,
    gives the digest of no pixel data, which is the same for each.

    Raises
    ------
    ValueError
        If a value is not bytes.
    """
    digest = hashlib.sha256()
    for tag in pixel_data_tags:
        if tag not in dataset:
            continue
        value = dataset[tag].value
        value = b"" if value is None else value
        if not isinstance(value, bytes):
            raise ValueError("pixel data are not bytes")
        if len(value) % 2:
            value += b"\0"
        digest.update(tag.to_bytes(4, "big"))
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.digest()


def contour_data_sha256(dataset: pydicom.Dataset) -> bytes:
    """Return the SHA-256 of the contours of a data set's ROI Contour
    Sequence (3006,0039).

    The digest is of each item's contours, in order: each contour's Contour
    Geometric Type, as its text, and the values of its Contour Data,
    Contour Offset Vector, and Contour Slab Thickness, as 64-bit
    floating-point numbers, each item, contour, type, and list of values
    after its count, so that the same contours under another ROI, split
    otherwise, moved, or given depth differ. A data set without a contour,
    as every one but an RT Structure Set's is, gives the digest of no
    contours, which is the same for each, however many items it has.

    Raises
    ------
    ValueError
        If a contour cannot be read, without a message that quotes it.
    """
    digest = hashlib.sha256()
    try:
        items = dataset.get("ROIContourSequence") or []
        if not any(len(item.get("ContourSequence") or []) for item in items):
            items = []
        digest.update(struct.pack(">Q", len(items)))
        for item in items:
            contours = item.get("ContourSequence") or []
            digest.update(struct.pack(">Q", len(contours)))
            for contour in contours:
                kind = str(contour.get("ContourGeometricType") or "").encode(
                    "utf-8", "surrogateescape"
                )
                data = contour.get("ContourData")
                values = (
                    []
                    if data is None
                    else [float(each) for each in data]
                    if isinstance(data, (list, tuple, pydicom.multival.MultiValue))
                    else [float(data)]
                )
                digest.update(struct.pack(">Q", len(kind)) + kind)
                digest.update(struct.pack(f">Q{len(values)}d", len(values), *values))
                # Each places or gives depth to the contour, so is part of it.
                for keyword in ("ContourOffsetVector", "ContourSlabThickness"):
                    extra = _floats(contour.get(keyword))
                    digest.update(struct.pack(f">Q{len(extra)}d", len(extra), *extra))
    # pydicom raises many types for a value it cannot read, and a message
    # can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise ValueError("contours cannot be read") from None
    return digest.digest()


def grid_data_sha256(
    dataset: pydicom.Dataset,
    registration_sequence: int,
    grid_sequence: int,
    grid_tags: tuple[int, ...],
) -> bytes:
    """Return the SHA-256 of a data set's deformation grids.

    Each grid is an item of a Deformable Registration Grid Sequence
    (0064,0005) in an item of the Deformable Registration Sequence
    (0064,0002), in the order of the items. The digest is of how many grids
    there are, then, for each in order, the values of its Image Orientation
    (Patient), Image Position (Patient), Grid Dimensions, and Grid
    Resolution, each as 64-bit floating-point numbers after their count,
    which place it, and the value field of its Vector Grid Data, after its
    length, with the trailing null byte that a file writes to make a value
    of odd length even, so that the same displacements placed otherwise,
    split otherwise, or changed in any byte differ. A data set without a
    grid, as every one but a deformable registration's is, gives the digest
    of no grids, which is the same for each.

    Raises
    ------
    ValueError
        If a grid cannot be read, without a message that quotes it.
    """
    grids = []
    try:
        if registration_sequence in dataset:
            for item in dataset[registration_sequence].value:
                if grid_sequence in item:
                    grids.extend(item[grid_sequence].value or ())
        digest = hashlib.sha256(struct.pack(">Q", len(grids)))
        for grid in grids:
            *placing, vectors = grid_tags
            for tag in placing:
                values = _floats(grid[tag].value if tag in grid else None)
                digest.update(struct.pack(f">Q{len(values)}d", len(values), *values))
            data = grid[vectors].value if vectors in grid else b""
            data = b"" if data is None else data
            if not isinstance(data, bytes):
                raise ValueError
            if len(data) % 2:
                data += b"\0"
            digest.update(struct.pack(">Q", len(data)) + data)
    # pydicom raises many types for a value it cannot read, and a message
    # can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise ValueError("deformation grids cannot be read") from None
    return digest.digest()


def _floats(value: object) -> list[float]:
    """A value's numbers, none where it is absent or empty."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return [float(each) for each in value]
    return [float(value)]
