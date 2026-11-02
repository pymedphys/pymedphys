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

"""NRRD volumes, read for checking the face block against public data (D-054).

NRRD (https://teem.sourceforge.net/nrrd/format.html) holds a header of
text, then the data. :func:`read_nrrd` reads one file with its data
attached: three spatial axes, each with its space direction, and, for a
segmentation with layers, one axis before them without one; of an integer
or floating point type; raw, gzip, or bzip2 encoded; in the space
``left-posterior-superior``, ``right-anterior-superior``, or
``left-anterior-superior``, or their abbreviations, in millimetres where
the header gives units. It places each voxel in DICOM's patient
coordinates, x towards the patient's left, y towards posterior, and z
towards superior, so that a volume gives the same positions in each of
those spaces.

A file that it cannot read is refused with a :class:`NrrdProblem`, whose
message quotes nothing of the file, since a header can hold text from a
patient's record. Its data is read into memory once, without a copy where
it is raw and of this machine's byte order, and never written anywhere.
"""

from __future__ import annotations

import bz2
import dataclasses
import enum
import math
import re
import types
import zlib
from collections.abc import Callable, Mapping
from typing import IO, Protocol

from pymedphys._imports import numpy as np

# The most bytes of data that a volume may hold, so that a header cannot
# ask for more memory than a CT volume needs: 2 GiB.
MAXIMUM_BYTES = 1 << 31
# The most bytes that a header may hold, and one of its lines.
_MAXIMUM_HEADER = 1 << 20
_MAXIMUM_LINE = 1 << 16
# How much encoded data is read at a time.
_CHUNK = 1 << 20
_MAGIC = re.compile(r"NRRD000[1-5]")
_VECTOR = re.compile(r"\(([^()]*)\)")
_DIRECTIONS = re.compile(r"\s*(?:(?:\([^()]*\)|none)\s*)+")

# Each type's NumPy code, by its spellings in a header.
_TYPES = {
    **dict.fromkeys(("signed char", "int8", "int8_t"), "i1"),
    **dict.fromkeys(("uchar", "unsigned char", "uint8", "uint8_t"), "u1"),
    **dict.fromkeys(
        ("short", "short int", "signed short", "signed short int", "int16", "int16_t"),
        "i2",
    ),
    **dict.fromkeys(
        ("ushort", "unsigned short", "unsigned short int", "uint16", "uint16_t"), "u2"
    ),
    **dict.fromkeys(("int", "signed int", "int32", "int32_t"), "i4"),
    **dict.fromkeys(("uint", "unsigned int", "uint32", "uint32_t"), "u4"),
    **dict.fromkeys(
        (
            "longlong",
            "long long",
            "long long int",
            "signed long long",
            "signed long long int",
            "int64",
            "int64_t",
        ),
        "i8",
    ),
    **dict.fromkeys(
        (
            "ulonglong",
            "unsigned long long",
            "unsigned long long int",
            "uint64",
            "uint64_t",
        ),
        "u8",
    ),
    "float": "f4",
    "double": "f8",
}
_ENCODINGS = {
    "raw": "raw",
    "gzip": "gzip",
    "gz": "gzip",
    "bzip2": "bzip2",
    "bz2": "bzip2",
}
# Each space's name, by its spellings, and the sign that takes each of its
# axes to DICOM's patient coordinates, x towards the patient's left, y
# towards posterior, and z towards superior.
_SPACES = {
    **dict.fromkeys(("left-posterior-superior", "lps"), "left-posterior-superior"),
    **dict.fromkeys(("right-anterior-superior", "ras"), "right-anterior-superior"),
    **dict.fromkeys(("left-anterior-superior", "las"), "left-anterior-superior"),
}
_SIGNS = {
    "left-posterior-superior": (1.0, 1.0, 1.0),
    "right-anterior-superior": (-1.0, -1.0, 1.0),
    "left-anterior-superior": (1.0, -1.0, 1.0),
}


class NrrdProblem(enum.Enum):
    """Why an NRRD file is not read."""

    # no NRRD magic, or a header that does not end
    NOT_NRRD = "not-nrrd"
    # a field that is missing, repeated, or cannot be read
    MALFORMED = "malformed-header"
    # data in another file
    DETACHED = "detached-data"
    UNSUPPORTED_TYPE = "unsupported-type"
    UNSUPPORTED_ENCODING = "unsupported-encoding"
    # no patient space, or units other than millimetres
    UNSUPPORTED_SPACE = "unsupported-space"
    # other than three spatial axes, with a fourth for layers, a space
    # origin, and no bytes or lines to skip
    UNSUPPORTED_GEOMETRY = "unsupported-geometry"
    # more data than MAXIMUM_BYTES
    TOO_LARGE = "too-large"
    # data that cannot be decoded, or that holds fewer or more bytes than
    # the sizes and type give
    DATA_LENGTH = "data-length"


class NrrdRefused(Exception):
    """An NRRD file was not read, for :attr:`problem`."""

    def __init__(self, problem: NrrdProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


@dataclasses.dataclass(frozen=True)
class NrrdFormat:
    """How a volume was stored, which can be counted: never a value.

    Attributes
    ----------
    type : str
        The NumPy name of its type, such as ``"int16"``.
    encoding : str
        ``"raw"``, ``"gzip"``, or ``"bzip2"``.
    space : str
        Its space's name in full, such as ``"left-posterior-superior"``.
    """

    type: str
    encoding: str
    space: str

    def __str__(self) -> str:
        return f"{self.type} {self.encoding} {self.space}"


@dataclasses.dataclass(frozen=True, repr=False)
class Volume:
    """One NRRD volume, in DICOM's patient coordinates.

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    values : numpy.ndarray
        The voxels, by slice, row, and column: the NRRD's spatial axes in
        reverse, its fastest last, so that ``values[k, j, i]`` is the voxel
        whose centre is at ``origin + i * axes[0] + j * axes[1] + k *
        axes[2]``. A segmentation with layers has them along a fourth axis,
        last.
    origin : numpy.ndarray
        The x, y, and z of the centre of the voxel at index 0 along each
        axis, in millimetres.
    axes : numpy.ndarray
        Three rows: the x, y, and z of one step along each spatial axis,
        the NRRD's first, fastest, axis first, in millimetres.
    key_values : mapping of str to str
        The header's key/value pairs, such as a 3D Slicer segmentation's
        ``Segment0_LabelValue``.
    format : NrrdFormat
    """

    values: np.ndarray
    origin: np.ndarray
    axes: np.ndarray
    key_values: Mapping[str, str]
    format: NrrdFormat

    def __repr__(self) -> str:
        return "Volume()"

    @property
    def shape(self) -> tuple[int, int, int]:
        """The slices, rows, and columns of its spatial axes."""
        slices, rows, columns = self.values.shape[:3]
        return int(slices), int(rows), int(columns)

    def positions(self, indices: np.ndarray) -> np.ndarray:
        """The x, y, and z of each voxel's centre, in millimetres.

        Parameters
        ----------
        indices : numpy.ndarray
            The slice, row, and column of each voxel along the last axis.
        """
        steps = np.asarray(indices, dtype=float)[..., ::-1]
        positions: np.ndarray = self.origin + steps @ self.axes
        return positions

    def indices(self, points: np.ndarray) -> np.ndarray:
        """The slice, row, and column, not rounded, at each point.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point along the last axis, in
            millimetres.
        """
        offsets = np.asarray(points, dtype=float) - self.origin
        steps = np.linalg.solve(self.axes.T, offsets.reshape(-1, 3).T).T
        return steps[:, ::-1].reshape(offsets.shape)


def read_nrrd(stream: IO[bytes], maximum_bytes: int = MAXIMUM_BYTES) -> Volume:
    """Read an NRRD volume from a stream, positioned at its start.

    Parameters
    ----------
    stream : binary file
        Read to the end of the data, as from :meth:`zipfile.ZipFile.open`.
    maximum_bytes : int
        The most bytes of data that the volume may hold.

    Raises
    ------
    NrrdRefused
        For a file that this module does not read, as it describes.
    """
    fields, key_values = _header(stream)
    if "datafile" in fields:
        raise NrrdRefused(NrrdProblem.DETACHED)
    for required in ("type", "dimension", "sizes", "encoding"):
        if required not in fields:
            raise NrrdRefused(NrrdProblem.MALFORMED)
    code = _TYPES.get(" ".join(fields["type"].lower().split()))
    if code is None:
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_TYPE)
    encoding = _ENCODINGS.get(fields["encoding"].strip().lower())
    if encoding is None:
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_ENCODING)
    sizes = _sizes(fields)
    space = _space(fields)
    origin, axes = _geometry(fields, len(sizes), space)
    for skip in ("byteskip", "lineskip"):
        if fields.get(skip, "0").strip() != "0":
            raise NrrdRefused(NrrdProblem.UNSUPPORTED_GEOMETRY)
    dtype = np.dtype(code)
    if dtype.itemsize > 1:
        endian = fields.get("endian", "").strip().lower()
        if endian not in ("little", "big"):
            raise NrrdRefused(NrrdProblem.MALFORMED)
        dtype = dtype.newbyteorder("<" if endian == "little" else ">")
    count = math.prod(sizes)
    size = count * dtype.itemsize
    if size > maximum_bytes:
        raise NrrdRefused(NrrdProblem.TOO_LARGE)
    data = {"raw": _raw, "gzip": _gunzipped, "bzip2": _bunzipped}[encoding](
        stream, size
    )
    # The NRRD's first axis is its fastest, so the array's last: for a
    # segmentation with layers, its layers, after the spatial axes.
    values = np.frombuffer(data, dtype=dtype).reshape(sizes[::-1])
    values = values.astype(dtype.newbyteorder("="), copy=False)
    return Volume(
        values=values,
        origin=origin,
        axes=axes,
        key_values=types.MappingProxyType(key_values),
        format=NrrdFormat(dtype.newbyteorder("=").name, encoding, space),
    )


def _header(stream: IO[bytes]) -> tuple[dict[str, str], dict[str, str]]:
    """Return a header's fields, by name without case or spaces, and its
    key/value pairs, leaving the stream at the data."""
    magic = stream.readline(_MAXIMUM_LINE)
    if not _MAGIC.fullmatch(magic.decode("latin-1").rstrip("\r\n")):
        raise NrrdRefused(NrrdProblem.NOT_NRRD)
    fields: dict[str, str] = {}
    key_values: dict[str, str] = {}
    read = len(magic)
    while True:
        line = stream.readline(_MAXIMUM_LINE + 1)
        read += len(line)
        if not line.endswith(b"\n") or read > _MAXIMUM_HEADER:
            raise NrrdRefused(NrrdProblem.NOT_NRRD)
        text = line.decode("latin-1").rstrip("\r\n")
        if not text:
            return fields, key_values
        if text.startswith("#"):
            continue
        pair = re.fullmatch(r"([^:]+):=(.*)", text)
        field = re.fullmatch(r"([^:]+): (.*)", text)
        if pair is not None:
            name, value, into = pair[1], pair[2], key_values
        elif field is not None:
            name, value, into = "".join(field[1].lower().split()), field[2], fields
        else:
            raise NrrdRefused(NrrdProblem.MALFORMED)
        if name in into:
            raise NrrdRefused(NrrdProblem.MALFORMED)
        into[name] = value


def _sizes(fields: Mapping[str, str]) -> tuple[int, ...]:
    """The sizes of a volume's axes, fastest first: three, or four for a
    segmentation with layers."""
    dimension = fields["dimension"].strip()
    sizes = fields["sizes"].split()
    if not dimension.isdigit() or not all(each.isdigit() for each in sizes):
        raise NrrdRefused(NrrdProblem.MALFORMED)
    if int(dimension) != len(sizes) or not all(int(each) > 0 for each in sizes):
        raise NrrdRefused(NrrdProblem.MALFORMED)
    if len(sizes) not in (3, 4):
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_GEOMETRY)
    return tuple(int(each) for each in sizes)


def _space(fields: Mapping[str, str]) -> str:
    """A volume's space's name in full, where it is one of the patient
    spaces that this module reads, in millimetres."""
    space = _SPACES.get(fields.get("space", "").strip().lower())
    if space is None:
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_SPACE)
    units = fields.get("spaceunits")
    if units is not None and re.findall(r'"([^"]*)"', units) != ["mm"] * 3:
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_SPACE)
    return space


def _geometry(
    fields: Mapping[str, str], dimension: int, space: str
) -> tuple[np.ndarray, np.ndarray]:
    """A volume's origin and spatial axes in DICOM's patient coordinates.

    Its axes are spatial, but for a segmentation's layers, along a fourth
    axis before them, without a space direction.
    """
    directions = fields.get("spacedirections")
    origin = fields.get("spaceorigin")
    if directions is None or origin is None:
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_GEOMETRY)
    if not _DIRECTIONS.fullmatch(directions):
        raise NrrdRefused(NrrdProblem.MALFORMED)
    entries = re.findall(r"\([^()]*\)|none", directions)
    spatial = [entry for entry in entries if entry != "none"]
    if len(entries) != dimension or len(spatial) != 3:
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_GEOMETRY)
    if dimension == 4 and entries[0] != "none":
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_GEOMETRY)
    signs = np.array(_SIGNS[space])
    axes = np.array([_vector(entry) for entry in spatial]) * signs
    # Steps of less than a micrometre, or along one plane, place nothing.
    if abs(float(np.linalg.det(axes))) < 1e-9:
        raise NrrdRefused(NrrdProblem.UNSUPPORTED_GEOMETRY)
    return _vector(origin.strip()) * signs, axes


def _vector(text: str) -> np.ndarray:
    """Three finite numbers in parentheses."""
    match = _VECTOR.fullmatch(text)
    if match is None:
        raise NrrdRefused(NrrdProblem.MALFORMED)
    try:
        values = [float(each) for each in match[1].split(",")]
    except ValueError:
        raise NrrdRefused(NrrdProblem.MALFORMED) from None
    if len(values) != 3 or not all(math.isfinite(each) for each in values):
        raise NrrdRefused(NrrdProblem.MALFORMED)
    return np.array(values)


def _raw(stream: IO[bytes], size: int) -> bytearray:
    """Exactly ``size`` bytes, the rest of the stream."""
    data = bytearray(size)
    filled = 0
    while filled < size:
        chunk = stream.read(min(_CHUNK, size - filled))
        if not chunk:
            raise NrrdRefused(NrrdProblem.DATA_LENGTH)
        data[filled : filled + len(chunk)] = chunk
        filled += len(chunk)
    if stream.read(1):
        raise NrrdRefused(NrrdProblem.DATA_LENGTH)
    return data


def _gunzipped(stream: IO[bytes], size: int) -> bytearray:
    """Exactly ``size`` bytes, the rest of the stream decompressed from one
    or more gzip members, or zlib streams."""
    return _decompressed(stream, size, lambda: zlib.decompressobj(zlib.MAX_WBITS | 32))


def _bunzipped(stream: IO[bytes], size: int) -> bytearray:
    """Exactly ``size`` bytes, the rest of the stream decompressed from one
    or more bzip2 streams."""
    return _decompressed(stream, size, bz2.BZ2Decompressor)


class _Decompressor(Protocol):
    """What :func:`_decompressed` needs of a zlib or bz2 decompressor."""

    @property
    def eof(self) -> bool: ...

    @property
    def unused_data(self) -> bytes: ...

    def decompress(self, data: bytes, max_length: int, /) -> bytes: ...


def _decompressed(
    stream: IO[bytes], size: int, start: Callable[[], _Decompressor]
) -> bytearray:
    """Exactly ``size`` bytes, the rest of the stream decompressed from one
    or more streams, one after another, each begun by ``start``."""
    data = bytearray(size)
    filled = 0
    decompressor = start()
    encoded = stream.read(_CHUNK)
    while encoded:
        try:
            # One byte more than is left, so that too much data is found
            # without decompressing all of it.
            decoded = decompressor.decompress(encoded, size - filled + 1)
        # zlib raises zlib.error, and bz2 OSError, for data of another
        # kind.
        except (zlib.error, OSError, EOFError):
            raise NrrdRefused(NrrdProblem.DATA_LENGTH) from None
        if len(decoded) > size - filled:
            raise NrrdRefused(NrrdProblem.DATA_LENGTH)
        data[filled : filled + len(decoded)] = decoded
        filled += len(decoded)
        # Output short of the limit took all of the input up to the end of
        # a stream, if it reached one, so what follows is another stream, or
        # still to be read.
        if decompressor.eof:
            encoded = decompressor.unused_data or stream.read(_CHUNK)
            if encoded:
                decompressor = start()
        else:
            encoded = stream.read(_CHUNK)
    if not decompressor.eof or filled != size:
        raise NrrdRefused(NrrdProblem.DATA_LENGTH)
    return data
