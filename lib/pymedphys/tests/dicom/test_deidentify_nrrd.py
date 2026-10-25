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

"""Reading NRRD volumes for the face block check. Every value here is
invented."""

from __future__ import annotations

import bz2
import gzip
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import nrrd
from pymedphys._dicom.deidentify.nrrd import NrrdProblem, NrrdRefused, read_nrrd

from . import _synthetic_nrrd as files

# Off centre, oblique, and of a different spacing along each axis.
_GRID = files.Grid(
    origin=(-123.25, 45.5, 678.0),
    axes=((0.8, 0.1, 0.0), (-0.15, 1.2, 0.05), (0.0, 0.2, 2.5)),
    shape=(4, 3, 5),
)
_VALUES = (np.arange(60, dtype=np.int16) - 30).reshape(_GRID.shape)


def _read(data: bytes, **options) -> nrrd.Volume:
    return read_nrrd(io.BytesIO(data), **options)


def _header(**changes: str | None) -> list[str]:
    """The header lines of an NRRD file of _VALUES, with fields changed, or
    left out where None."""
    fields: dict[str, str | None] = {
        "type": "short",
        "dimension": "3",
        "space": "left-posterior-superior",
        "sizes": "5 3 4",
        "space directions": "(1,0,0) (0,1,0) (0,0,1)",
        "kinds": "domain domain domain",
        "endian": "little",
        "encoding": "raw",
        "space origin": "(0,0,0)",
    }
    fields.update(changes)
    return [f"{name}: {value}" for name, value in fields.items() if value is not None]


def _file(lines: list[str], data: bytes | None = None) -> bytes:
    data = _VALUES.astype("<i2").tobytes() if data is None else data
    return ("\n".join(["NRRD0004", *lines]) + "\n\n").encode("ascii") + data


@pytest.mark.parametrize("encoding", ["raw", "gzip", "bzip2"])
@pytest.mark.parametrize("endian", ["little", "big"])
@pytest.mark.parametrize("kind", sorted(files.TYPES))
def test_each_type_encoding_and_byte_order_gives_the_values(kind, endian, encoding):
    values = (np.arange(60) - 25).astype(kind).reshape(_GRID.shape)

    volume = _read(files.nrrd_file(values, _GRID, encoding=encoding, endian=endian))

    np.testing.assert_array_equal(volume.values, values)
    assert volume.values.dtype == np.dtype(kind)
    assert volume.values.dtype.isnative
    assert volume.shape == _GRID.shape
    assert str(volume.format) == f"{kind} {encoding} left-posterior-superior"


@pytest.mark.parametrize("space", [files.LPS, files.RAS])
def test_each_voxel_is_placed_by_the_space_directions_in_patient_coordinates(space):
    volume = _read(files.nrrd_file(_VALUES, _GRID, space=space))

    # Written in the file's space, read in DICOM's: x towards the patient's
    # left, y towards posterior, z towards superior.
    origin = np.array(_GRID.origin)
    axes = np.array(_GRID.axes)
    for k, j, i in [(0, 0, 0), (3, 2, 4), (1, 2, 0), (2, 0, 3)]:
        expected = origin + i * axes[0] + j * axes[1] + k * axes[2]
        np.testing.assert_allclose(volume.positions(np.array([k, j, i])), expected)
    np.testing.assert_allclose(volume.origin, origin)
    np.testing.assert_allclose(volume.axes, axes)
    assert volume.format.space == space


def test_a_left_anterior_superior_volume_turns_its_y_axis():
    lines = _header(
        space="LAS",
        **{"space directions": "(1,0,0) (0,2,0) (0,0,3)", "space origin": "(4,5,6)"},
    )

    volume = _read(_file(lines))

    np.testing.assert_allclose(volume.origin, (4, -5, 6))
    np.testing.assert_allclose(volume.axes, [(1, 0, 0), (0, -2, 0), (0, 0, 3)])
    assert volume.format.space == "left-anterior-superior"


def test_indices_are_the_inverse_of_positions():
    volume = _read(files.nrrd_file(_VALUES, _GRID))
    indices = np.array([(0, 0, 0), (3, 2, 4), (1.5, 0.25, 2.75)])

    np.testing.assert_allclose(volume.indices(volume.positions(indices)), indices)


def test_a_segmentation_with_layers_has_them_last():
    layers = np.zeros((*_GRID.shape, 2), dtype=np.uint8)
    layers[1, 2, 3, 1] = 4
    data = files.nrrd_file(
        layers, _GRID, layered=True, key_values={"Segment0_Layer": "1"}
    )

    volume = _read(data)

    assert volume.values.shape == (*_GRID.shape, 2)
    assert volume.shape == _GRID.shape
    np.testing.assert_array_equal(np.argwhere(volume.values), [(1, 2, 3, 1)])
    np.testing.assert_allclose(volume.axes, _GRID.axes)
    assert volume.key_values == {"Segment0_Layer": "1"}


def test_other_spellings_of_fields_types_encodings_and_spaces_are_read():
    lines = [
        "type: signed short int",
        "dimension: 3",
        "space: LPS",
        "sizes: 5 3 4",
        "space directions: ( 1, 0, 0 ) (0,1,0) (0,0,1)",
        "endian: little",
        "encoding: gz",
        "byteskip: 0",
        "line skip: 0",
        "space origin: (0, 0, 0)",
        'space units: "mm" "mm" "mm"',
        "# a comment",
    ]

    volume = _read(_file(lines, gzip.compress(_VALUES.astype("<i2").tobytes())))

    np.testing.assert_array_equal(volume.values, _VALUES)


@pytest.mark.parametrize(
    "compress", [gzip.compress, bz2.compress], ids=["gzip", "bzip2"]
)
def test_data_in_several_compressed_streams_is_read_as_one(compress):
    data = _VALUES.astype("<i2").tobytes()
    encoding = "gzip" if compress is gzip.compress else "bzip2"

    volume = _read(
        _file(_header(encoding=encoding), compress(data[:50]) + compress(data[50:]))
    )

    np.testing.assert_array_equal(volume.values, _VALUES)


def _truncated(encoding: str) -> bytes:
    return files.nrrd_file(_VALUES, _GRID, encoding=encoding)[:-3]


def _extended(encoding: str) -> bytes:
    return files.nrrd_file(_VALUES, _GRID, encoding=encoding) + b"\x00"


@pytest.mark.parametrize(
    "data, problem",
    [
        (b"NRRD0006\n\n", NrrdProblem.NOT_NRRD),
        (b"P5 5 3 255\n", NrrdProblem.NOT_NRRD),
        (b"NRRD0004\ntype: short\n", NrrdProblem.NOT_NRRD),
        (b"NRRD0004\ntype: short\ndimension: 3" + b"x" * 70000, NrrdProblem.NOT_NRRD),
        (_file(_header(type=None)), NrrdProblem.MALFORMED),
        (_file([*_header(), "type: short"]), NrrdProblem.MALFORMED),
        (_file([*_header(), "no colon here"]), NrrdProblem.MALFORMED),
        (_file(_header(endian=None)), NrrdProblem.MALFORMED),
        (_file(_header(sizes="5 3")), NrrdProblem.MALFORMED),
        (_file(_header(sizes="5 0 4")), NrrdProblem.MALFORMED),
        (_file(_header(sizes="5 -3 4")), NrrdProblem.MALFORMED),
        (_file(_header(**{"space origin": "(0,nan,0)"})), NrrdProblem.MALFORMED),
        (_file(_header(**{"space origin": "(0,0)"})), NrrdProblem.MALFORMED),
        (
            _file(_header(**{"space directions": "(1,0,0) (0,1,0) [0,0,1]"})),
            NrrdProblem.MALFORMED,
        ),
        (_file([*_header(), "data file: values.raw"]), NrrdProblem.DETACHED),
        (_file(_header(type="block")), NrrdProblem.UNSUPPORTED_TYPE),
        (_file(_header(encoding="txt")), NrrdProblem.UNSUPPORTED_ENCODING),
        (_file(_header(space="scanner-xyz")), NrrdProblem.UNSUPPORTED_SPACE),
        (_file(_header(space="3D-right-handed")), NrrdProblem.UNSUPPORTED_SPACE),
        (_file(_header(space=None)), NrrdProblem.UNSUPPORTED_SPACE),
        (
            _file([*_header(), 'space units: "mm" "cm" "mm"']),
            NrrdProblem.UNSUPPORTED_SPACE,
        ),
        (
            _file(
                _header(
                    dimension="2",
                    sizes="15 4",
                    **{"space directions": "(1,0,0) (0,1,0)"},
                )
            ),
            NrrdProblem.UNSUPPORTED_GEOMETRY,
        ),
        (
            _file(_header(**{"space directions": "(1,0,0) (0,1,0) none"})),
            NrrdProblem.UNSUPPORTED_GEOMETRY,
        ),
        (
            _file(_header(**{"space directions": "(1,0,0) (2,0,0) (0,0,1)"})),
            NrrdProblem.UNSUPPORTED_GEOMETRY,
        ),
        (_file(_header(**{"space origin": None})), NrrdProblem.UNSUPPORTED_GEOMETRY),
        (
            _file(_header(**{"space directions": None})),
            NrrdProblem.UNSUPPORTED_GEOMETRY,
        ),
        (_file([*_header(), "byte skip: -1"]), NrrdProblem.UNSUPPORTED_GEOMETRY),
        (_file([*_header(), "line skip: 1"]), NrrdProblem.UNSUPPORTED_GEOMETRY),
        (
            _file(
                _header(
                    dimension="4",
                    sizes="5 3 4 2",
                    **{"space directions": "(1,0,0) (0,1,0) (0,0,1) none"},
                )
            ),
            NrrdProblem.UNSUPPORTED_GEOMETRY,
        ),
        (_truncated("raw"), NrrdProblem.DATA_LENGTH),
        (_truncated("gzip"), NrrdProblem.DATA_LENGTH),
        (_truncated("bzip2"), NrrdProblem.DATA_LENGTH),
        (_extended("raw"), NrrdProblem.DATA_LENGTH),
        (_extended("gzip"), NrrdProblem.DATA_LENGTH),
        (_extended("bzip2"), NrrdProblem.DATA_LENGTH),
        (_file(_header(encoding="gzip"), b"not gzip at all"), NrrdProblem.DATA_LENGTH),
        (
            _file(_header(encoding="bzip2"), b"not bzip2 at all"),
            NrrdProblem.DATA_LENGTH,
        ),
        (
            _file(_header(encoding="gzip"), gzip.compress(bytes(240))),
            NrrdProblem.DATA_LENGTH,
        ),
    ],
    ids=lambda value: value.value if isinstance(value, NrrdProblem) else None,
)
def test_a_file_this_module_does_not_read_is_refused_by_why(data, problem):
    with pytest.raises(NrrdRefused) as refused:
        _read(data)

    assert refused.value.problem is problem


def test_a_volume_larger_than_the_limit_is_refused_before_its_data_is_read():
    data = files.nrrd_file(_VALUES, _GRID)

    with pytest.raises(NrrdRefused) as refused:
        _read(data, maximum_bytes=_VALUES.nbytes - 1)

    assert refused.value.problem is NrrdProblem.TOO_LARGE
    assert _read(data, maximum_bytes=_VALUES.nbytes).shape == _GRID.shape


def test_a_refusal_quotes_nothing_of_the_file_and_a_volume_shows_nothing():
    secret = "SYNTHETIC-PATIENT-NAME"
    data = _file([*_header(type=secret), f"{secret}:={secret}"])

    with pytest.raises(NrrdRefused) as refused:
        _read(data)

    assert str(refused.value) == "unsupported-type"
    volume = _read(_file([*_header(), f"Segment0_Name:={secret}"]))
    assert secret not in repr(volume)
    assert secret not in repr(volume.format)
