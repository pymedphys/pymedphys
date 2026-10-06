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

"""Image previews for the confidential QC pack's human review (D-016, D-017).

D-017 asks a reviewer to look at every series, by maximum intensity
projection or cine strip, and at every instance in high-risk categories.
:func:`previews_of` makes those images, as PNG files, from the files that a
run wrote, since the engine never changes pixel data:

- a cine strip of each series: up to :data:`CINE_FRAMES` of its frames,
  evenly spaced through the series from its first frame to its last, each
  scaled to fit a square of :data:`TILE_PIXELS` pixels, in rows of
  :data:`CINE_COLUMNS`;
- a frontal maximum intensity projection of each series that forms a
  volume: at least :data:`VOLUME_SLICES` single-frame instances of one size,
  orientation, and pixel spacing, at distinct positions, whose axes lie along
  the patient's anterior-posterior, left-right, and superior-inferior
  directions. It is projected along the anterior-posterior axis and shown
  with the patient's head at the top and right on the viewer's left, sampled
  to square pixels by nearest neighbour, at most :data:`MIP_PIXELS` a side;
- each high-risk instance at full resolution: every frame, or
  :data:`CINE_FRAMES` evenly spaced, unscaled, since burned-in text may be
  small.

A series is the instances that share a Series Instance UID, or an instance
alone without one, in the order of their positions along the normal of their
common orientation, then of Instance Number, then of run position. Each
preview lists the frames it shows, by run position and frame index from 0,
and how many frames its series or instance has.

Monochrome pixel data are rescaled by Rescale Slope and Rescale Intercept,
where given, and windowed from the 0.5th to the 99.5th percentile of what the
preview shows; MONOCHROME1 is inverted so that higher values are darker. RGB
pixel data with 8 bits allocated are shown as they are. An instance whose
pixel data cannot be previewed is reported with why, rather than left out:
pixel data in a compressed transfer syntax, which the engine does not support
yet; a photometric interpretation other than MONOCHROME1, MONOCHROME2, or
RGB, or float pixel data; or pixel data that cannot be decoded. A high-risk
instance without pixel data, such as an RT Structure Set with the patient's
outline, is reported too, so that the reviewer knows there is nothing to see
of it here.

A PNG is written with no ancillary chunks, so it holds no time or text, and
the same pixels always give the same file with the same zlib.
"""

from __future__ import annotations

import dataclasses
import io
import math
import struct
import zlib
from collections.abc import Collection, Iterator, Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .qc_pack import NotPreviewedEntry, NotPreviewedReason, Preview, PreviewKind

CINE_FRAMES = 16
CINE_COLUMNS = 4
TILE_PIXELS = 256
MIP_PIXELS = 1024
VOLUME_SLICES = 3

_PERCENTILES = (0.5, 99.5)
_MONOCHROME = frozenset({"MONOCHROME1", "MONOCHROME2"})
_FLOAT_PIXEL_DATA = ("FloatPixelData", "DoubleFloatPixelData")
# A direction cosine at least this large puts an axis along a patient axis.
_ALONG = 0.7
_ORIENTATION_TOLERANCE = 1e-4
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclasses.dataclass(frozen=True)
class _Plane:
    """The geometry of a single-frame image in the patient's coordinates."""

    row: tuple[float, float, float]  # direction of increasing column index
    column: tuple[float, float, float]  # direction of increasing row index
    spacing: tuple[float, float]  # between rows, then between columns
    shape: tuple[int, int]
    origin: tuple[float, float, float]


@dataclasses.dataclass(frozen=True)
class _Instance:
    position: int
    dataset: pydicom.Dataset
    frames: int
    colour: bool
    inverted: bool
    rescale: tuple[float, float]
    spacing: tuple[float, float] | None
    plane: _Plane | None
    number: int | None


@dataclasses.dataclass(frozen=True)
class PreviewSet:
    """The previews of a run, and the instances that could not be previewed.

    Attributes
    ----------
    previews : tuple of ~pymedphys._dicom.deidentify.qc_pack.Preview
        Each series' cine strip, then its projection if it forms a volume,
        series in the order of their first run position; then each
        high-risk instance, in run position order. Named ``P-0001.png``
        onwards in that order.
    not_previewed : tuple of ~pymedphys._dicom.deidentify.qc_pack.NotPreviewedEntry
        In run position order.
    """

    previews: tuple[Preview, ...]
    not_previewed: tuple[NotPreviewedEntry, ...]


def previews_of(written: Mapping[int, bytes], high_risk: Collection[int]) -> PreviewSet:
    """Return the previews of the files that a run wrote, as the module describes.

    Parameters
    ----------
    written : mapping of int to bytes
        Each file to preview, by its instance's run position.
    high_risk : collection of int
        The run positions of the instances in high-risk categories. A
        position without a file is ignored, since nothing of it is released.

    Returns
    -------
    PreviewSet
    """
    instances: list[_Instance] = []
    refused: dict[int, NotPreviewedReason] = {}
    for position in sorted(written):
        found = _instance(position, written[position])
        if isinstance(found, _Instance):
            instances.append(found)
        elif found is not None:
            refused[position] = found
        elif position in high_risk:
            refused[position] = NotPreviewedReason.NO_PIXEL_DATA
    images: list[tuple[PreviewKind, tuple[tuple[int, int], ...], int, np.ndarray]] = []
    decoded = _Decoder(refused)
    for series in _series(instances):
        images.extend(_series_images(series, decoded))
    for instance in instances:
        if instance.position in high_risk:
            image = _instance_image(instance, decoded)
            if image is not None:
                images.append(image)
    width = max(4, len(str(len(images))))
    previews = tuple(
        Preview(f"P-{number:0{width}d}.png", kind, frames, total, png(image))
        for number, (kind, frames, total, image) in enumerate(images, start=1)
    )
    return PreviewSet(
        previews,
        tuple(
            NotPreviewedEntry(position, reason)
            for position, reason in sorted(refused.items())
        ),
    )


def _instance(position: int, data: bytes) -> _Instance | NotPreviewedReason | None:
    """Read what a preview needs of a file, or why it cannot be previewed.

    ``None`` means the file has no pixel data.
    """
    try:
        dataset = pydicom.dcmread(io.BytesIO(data))
    except Exception:  # pylint: disable = broad-exception-caught
        # Whatever pydicom raises, the reviewer is told, never the error.
        return NotPreviewedReason.UNREADABLE
    if any(keyword in dataset for keyword in _FLOAT_PIXEL_DATA):
        return NotPreviewedReason.UNSUPPORTED
    if "PixelData" not in dataset:
        return None
    return _described(position, dataset)


def _described(
    position: int, dataset: pydicom.Dataset
) -> _Instance | NotPreviewedReason:
    """Describe an image whose pixel data a preview can show, or say why not."""
    try:
        if dataset.file_meta.TransferSyntaxUID.is_compressed:
            return NotPreviewedReason.COMPRESSED
        photometric = str(dataset.PhotometricInterpretation).strip()
        samples = int(dataset.SamplesPerPixel)
        allocated = int(dataset.BitsAllocated)
        frames = int(dataset.get("NumberOfFrames") or 1)
        rows, columns = int(dataset.Rows), int(dataset.Columns)
        rescale = (
            float(dataset.get("RescaleSlope", 1)),
            float(dataset.get("RescaleIntercept", 0)),
        )
        number = dataset.get("InstanceNumber")
        number = None if number in (None, "") else int(number)
    except Exception:  # pylint: disable = broad-exception-caught
        return NotPreviewedReason.UNREADABLE
    colour = photometric == "RGB" and samples == 3 and allocated == 8
    if not colour and not (photometric in _MONOCHROME and samples == 1):
        return NotPreviewedReason.UNSUPPORTED
    if (
        frames < 1
        or rows < 1
        or columns < 1
        or not all(math.isfinite(value) for value in rescale)
    ):
        return NotPreviewedReason.UNREADABLE
    spacing = _spacing(dataset)
    return _Instance(
        position=position,
        dataset=dataset,
        frames=frames,
        colour=colour,
        inverted=photometric == "MONOCHROME1",
        rescale=rescale,
        spacing=spacing,
        plane=_plane(dataset, spacing, (rows, columns)) if frames == 1 else None,
        number=number,
    )


def _floats(dataset: pydicom.Dataset, keyword: str, count: int) -> tuple | None:
    try:
        values = tuple(float(value) for value in dataset[keyword].value)
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    if len(values) != count or not all(math.isfinite(value) for value in values):
        return None
    return values


def _spacing(dataset: pydicom.Dataset) -> tuple[float, float] | None:
    spacing = _floats(dataset, "PixelSpacing", 2)
    if spacing is None or min(spacing) <= 0:
        return None
    return spacing[0], spacing[1]


def _plane(
    dataset: pydicom.Dataset,
    spacing: tuple[float, float] | None,
    shape: tuple[int, int],
) -> _Plane | None:
    orientation = _floats(dataset, "ImageOrientationPatient", 6)
    origin = _floats(dataset, "ImagePositionPatient", 3)
    if orientation is None or origin is None or spacing is None:
        return None
    row = np.array(orientation[:3])
    column = np.array(orientation[3:])
    if (
        abs(np.linalg.norm(row) - 1) > 1e-3
        or abs(np.linalg.norm(column) - 1) > 1e-3
        or abs(float(row @ column)) > 1e-3
    ):
        return None
    return _Plane(
        row=(orientation[0], orientation[1], orientation[2]),
        column=(orientation[3], orientation[4], orientation[5]),
        spacing=spacing,
        shape=shape,
        origin=(origin[0], origin[1], origin[2]),
    )


class _Decoder:
    """Decodes an instance's frames, recording an instance that fails."""

    def __init__(self, refused: dict[int, NotPreviewedReason]) -> None:
        self._refused = refused

    def frames(self, instance: _Instance) -> np.ndarray | None:
        """Return the frames as (frame, row, column[, sample]), or None.

        Monochrome frames are rescaled to float; RGB frames are uint8.
        """
        if instance.position in self._refused:
            return None
        try:
            pixels = np.asarray(instance.dataset.pixel_array)
        except Exception:  # pylint: disable = broad-exception-caught
            self._refused[instance.position] = NotPreviewedReason.UNREADABLE
            return None
        rows, columns = int(instance.dataset.Rows), int(instance.dataset.Columns)
        shape = (instance.frames, rows, columns) + ((3,) if instance.colour else ())
        if pixels.size != math.prod(shape):
            self._refused[instance.position] = NotPreviewedReason.UNREADABLE
            return None
        pixels = pixels.reshape(shape)
        if instance.colour:
            return pixels.astype(np.uint8)
        slope, intercept = instance.rescale
        return pixels.astype(np.float64) * slope + intercept


def _series(instances: Sequence[_Instance]) -> Iterator[list[_Instance]]:
    """Yield each series, in order of its first position, its instances ordered."""
    groups: dict[object, list[_Instance]] = {}
    for instance in instances:
        uid = instance.dataset.get("SeriesInstanceUID")
        key = ("series", str(uid)) if uid else ("instance", instance.position)
        groups.setdefault(key, []).append(instance)
    for group in groups.values():
        yield sorted(group, key=_order_key(group))


def _order_key(group: list[_Instance]):
    normal = _common_normal(group)
    if normal is not None:
        return lambda instance: (
            float(np.dot(normal, instance.plane.origin)),
            instance.position,
        )
    if all(instance.number is not None for instance in group):
        return lambda instance: (instance.number, instance.position)
    return lambda instance: instance.position


def _common_normal(group: list[_Instance]) -> np.ndarray | None:
    """The normal of the group's one orientation, if every instance has one."""
    planes = [instance.plane for instance in group]
    if not all(planes):
        return None
    first = planes[0]
    assert first is not None
    if not all(
        np.allclose(plane.row, first.row, atol=_ORIENTATION_TOLERANCE)
        and np.allclose(plane.column, first.column, atol=_ORIENTATION_TOLERANCE)
        for plane in planes
        if plane is not None
    ):
        return None
    return np.cross(first.row, first.column)


def _evenly(count: int, limit: int) -> list[int]:
    """Up to ``limit`` indices from 0 to ``count - 1``, evenly spaced, each once."""
    if count <= limit:
        return list(range(count))
    return sorted({round(i * (count - 1) / (limit - 1)) for i in range(limit)})


def _series_images(series: list[_Instance], decoder: _Decoder):
    frames = [
        (instance.position, frame)
        for instance in series
        for frame in range(instance.frames)
    ]
    chosen = {frames[i] for i in _evenly(len(frames), CINE_FRAMES)}
    volume = _volume(series)
    tiles: list[tuple[int, int, np.ndarray, _Instance]] = []
    projection = _Projection(volume) if volume is not None else None
    for instance in series:
        pixels = decoder.frames(instance)
        if pixels is None:
            continue
        for frame in range(instance.frames):
            if (instance.position, frame) in chosen:
                tiles.append(
                    (
                        instance.position,
                        frame,
                        _fitted(pixels[frame], instance),
                        instance,
                    )
                )
        if projection is not None:
            projection.add(instance, pixels[0])
    if tiles:
        image = _sheet(
            _windowed_tiles([(tile, instance) for _, _, tile, instance in tiles]),
            TILE_PIXELS,
            TILE_PIXELS,
        )
        yield (
            PreviewKind.SERIES_CINE,
            tuple((position, frame) for position, frame, *_ in tiles),
            len(frames),
            image,
        )
    if projection is not None:
        projected = projection.image()
        if projected is not None:
            yield projected


def _instance_image(instance: _Instance, decoder: _Decoder):
    pixels = decoder.frames(instance)
    if pixels is None:
        return None
    chosen = _evenly(instance.frames, CINE_FRAMES)
    tiles = _windowed_tiles([(pixels[frame], instance) for frame in chosen])
    return (
        PreviewKind.INSTANCE,
        tuple((instance.position, frame) for frame in chosen),
        instance.frames,
        _sheet(tiles, tiles[0].shape[0], tiles[0].shape[1]),
    )


def _fitted(frame: np.ndarray, instance: _Instance) -> np.ndarray:
    """Scale a frame by nearest neighbour to fit the tile, keeping its aspect."""
    rows, columns = frame.shape[:2]
    row_spacing, column_spacing = instance.spacing or (1.0, 1.0)
    height, width = rows * row_spacing, columns * column_spacing
    scale = TILE_PIXELS / max(height, width)
    return _resampled(
        frame,
        max(1, min(TILE_PIXELS, round(height * scale))),
        max(1, min(TILE_PIXELS, round(width * scale))),
    )


def _resampled(image: np.ndarray, rows: int, columns: int) -> np.ndarray:
    """Sample an image by nearest neighbour to the given shape."""
    row_index = np.minimum(
        (np.arange(rows) + 0.5) * image.shape[0] // rows, image.shape[0] - 1
    ).astype(int)
    column_index = np.minimum(
        (np.arange(columns) + 0.5) * image.shape[1] // columns, image.shape[1] - 1
    ).astype(int)
    sampled: np.ndarray = image[row_index][:, column_index]
    return sampled


def _windowed_tiles(tiles: list[tuple[np.ndarray, _Instance]]) -> list[np.ndarray]:
    """Window monochrome tiles together, and give every tile one sample layout.

    If any tile is RGB, every tile is given as RGB.
    """
    monochrome = [tile for tile, instance in tiles if not instance.colour]
    window = (
        _window(np.concatenate([tile.ravel() for tile in monochrome]))
        if monochrome
        else None
    )
    colour = any(instance.colour for _, instance in tiles)
    shown = []
    for tile, instance in tiles:
        if not instance.colour:
            assert window is not None
            tile = _grey(tile, window, instance.inverted)
            if colour:
                tile = np.repeat(tile[..., np.newaxis], 3, axis=2)
        shown.append(tile)
    return shown


def _window(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return -0.5, 0.5
    low, high = (float(value) for value in np.percentile(finite, _PERCENTILES))
    # A uniform image is shown mid-grey, so that it stands out from the
    # black around the tiles.
    return (low, high) if high > low else (low - 0.5, low + 0.5)


def _grey(image: np.ndarray, window: tuple[float, float], inverted: bool) -> np.ndarray:
    low, high = window
    scaled = np.clip((image - low) / (high - low), 0.0, 1.0)
    scaled = np.nan_to_num(scaled, nan=0.0)
    if inverted:
        scaled = 1.0 - scaled
    return np.round(scaled * 255).astype(np.uint8)


def _sheet(tiles: list[np.ndarray], cell_rows: int, cell_columns: int) -> np.ndarray:
    """Lay tiles out in rows of :data:`CINE_COLUMNS`, each centred in its cell."""
    columns = min(CINE_COLUMNS, len(tiles))
    rows = math.ceil(len(tiles) / columns)
    trailing = tiles[0].shape[2:]
    sheet = np.zeros((rows * cell_rows, columns * cell_columns, *trailing), np.uint8)
    for index, tile in enumerate(tiles):
        top = (index // columns) * cell_rows + (cell_rows - tile.shape[0]) // 2
        left = (index % columns) * cell_columns + (cell_columns - tile.shape[1]) // 2
        sheet[top : top + tile.shape[0], left : left + tile.shape[1]] = tile
    return sheet


@dataclasses.dataclass(frozen=True)
class _Volume:
    """A series that forms a volume, and the roles of its three axes.

    Axis 0 runs through the slices along the normal; axis 1 down the rows,
    along the plane's column direction; axis 2 along the columns, along its
    row direction.
    """

    positions: tuple[float, ...]  # along the normal, ascending, one per slice
    directions: tuple[np.ndarray, np.ndarray, np.ndarray]
    spacing: tuple[float, float]  # between rows, then between columns
    shape: tuple[int, int]
    anterior: int  # the axis along the patient's anterior-posterior direction
    vertical: int  # along superior-inferior
    horizontal: int  # along left-right


def _volume(series: list[_Instance]) -> _Volume | None:
    if len(series) < VOLUME_SLICES or any(instance.colour for instance in series):
        return None
    normal = _common_normal(series)
    if normal is None:
        return None
    planes = [instance.plane for instance in series]
    first = planes[0]
    assert first is not None
    if any(
        plane is None
        or plane.shape != first.shape
        or not np.allclose(plane.spacing, first.spacing)
        for plane in planes
    ):
        return None
    positions = tuple(float(np.dot(normal, plane.origin)) for plane in planes if plane)
    if any(later - earlier <= 1e-6 for earlier, later in zip(positions, positions[1:])):
        return None
    directions = (normal, np.array(first.column), np.array(first.row))
    roles = _roles(directions)
    if roles is None:
        return None
    anterior, vertical, horizontal = roles
    return _Volume(
        positions,
        directions,
        first.spacing,
        first.shape,
        anterior=anterior,
        vertical=vertical,
        horizontal=horizontal,
    )


def _roles(directions) -> tuple[int, int, int] | None:
    """The axes along anterior-posterior, superior-inferior, and left-right.

    None unless each lies along a different one of the three.
    """
    roles = []
    # The patient's y (anterior-posterior), z (superior), then x (left).
    for patient_axis in (1, 2, 0):
        components = [abs(float(direction[patient_axis])) for direction in directions]
        axis = int(np.argmax(components))
        if components[axis] < _ALONG:
            return None
        roles.append(axis)
    if len(set(roles)) != 3:
        return None
    return roles[0], roles[1], roles[2]


class _Projection:
    """Accumulates a volume's maximum intensity projection, slice by slice."""

    def __init__(self, volume: _Volume) -> None:
        self._volume = volume
        self._slices: list[np.ndarray] = []
        self._maximum: np.ndarray | None = None
        self._order: list[int] = []
        self._inverted: list[bool] = []

    def add(self, instance: _Instance, frame: np.ndarray) -> None:
        """Add the next slice, in series order."""
        self._order.append(instance.position)
        self._inverted.append(instance.inverted)
        anterior = self._volume.anterior
        if anterior == 0:
            self._maximum = (
                frame.copy()
                if self._maximum is None
                else np.maximum(self._maximum, frame)
            )
        else:
            self._slices.append(frame.max(axis=anterior - 1))

    def image(self):
        volume = self._volume
        if len(self._order) != len(volume.positions):
            return None  # a slice could not be decoded
        coordinates = {
            0: np.array(volume.positions) - volume.positions[0],
            1: np.arange(volume.shape[0]) * volume.spacing[0],
            2: np.arange(volume.shape[1]) * volume.spacing[1],
        }
        if volume.anterior == 0:
            assert self._maximum is not None
            image, axes = self._maximum, (1, 2)
        else:
            image = np.stack(self._slices)
            axes = (0, 3 - volume.anterior)
        if axes.index(volume.vertical) == 1:
            image, axes = image.T, (axes[1], axes[0])
        in_plane = [volume.spacing[axis - 1] for axis in axes if axis != 0]
        step = min(in_plane)
        extents = [float(coordinates[axis][-1]) for axis in axes]
        step = max(step, max(extents) / (MIP_PIXELS - 1))
        for dimension, axis in enumerate(axes):
            wanted = np.arange(int(extents[dimension] / step) + 1) * step
            nearest = _nearest(coordinates[axis], wanted)
            image = np.take(image, nearest, axis=dimension)
        vertical, horizontal = (volume.directions[axis] for axis in axes)
        if vertical[2] > 0:  # increasing index runs superior, so flip
            image = image[::-1]
        if horizontal[0] < 0:  # increasing index runs to the patient's right
            image = image[:, ::-1]
        shown = _grey(image, _window(image.ravel()), all(self._inverted))
        frames = tuple((position, 0) for position in self._order)
        return PreviewKind.SERIES_MIP, frames, len(volume.positions), shown


def _nearest(coordinates: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """The index of the coordinate nearest each wanted one; coordinates ascend."""
    right = np.clip(np.searchsorted(coordinates, wanted), 1, len(coordinates) - 1)
    left = right - 1
    closer_left = (wanted - coordinates[left]) <= (coordinates[right] - wanted)
    return np.where(closer_left, left, right)


def png(image: np.ndarray) -> bytes:
    """Return an 8-bit greyscale or RGB image as a PNG file.

    Parameters
    ----------
    image : numpy.ndarray
        uint8, of shape (rows, columns) or (rows, columns, 3).

    Returns
    -------
    bytes
        A PNG with only its IHDR, IDAT, and IEND chunks, each row filtered
        with filter type 0.

    Examples
    --------
    >>> import numpy as np
    >>> png(np.zeros((2, 3), np.uint8))[:8]
    b'\\x89PNG\\r\\n\\x1a\\n'
    """
    if image.dtype != np.uint8 or not (
        image.ndim == 2 or (image.ndim == 3 and image.shape[2] == 3)
    ):
        raise ValueError("a PNG needs a uint8 image of grey or RGB samples")
    rows, columns = image.shape[:2]
    if rows < 1 or columns < 1:
        raise ValueError("a PNG needs at least one pixel")
    colour_type = 0 if image.ndim == 2 else 2
    header = struct.pack(">IIBBBBB", columns, rows, 8, colour_type, 0, 0, 0)
    raw = np.ascontiguousarray(image).reshape(rows, -1)
    filtered = np.concatenate([np.zeros((rows, 1), np.uint8), raw], axis=1)
    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(filtered.tobytes(), 6))
        + _chunk(b"IEND", b"")
    )


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )
