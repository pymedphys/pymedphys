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

"""Tests of the QC pack's image previews, as they are made.

Every image is synthetic.
"""

import io
import math
import struct
import zlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import qc_previews
from pymedphys._dicom.deidentify.qc_pack import (
    NotPreviewedEntry,
    NotPreviewedReason,
    PreviewKind,
)

CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
RT_STRUCTURE_SET = "1.2.840.10008.5.1.4.1.1.481.3"
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"
RLE_LOSSLESS = "1.2.840.10008.1.2.5"
SERIES = "2.25.7001"
AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
CORONAL = (1.0, 0.0, 0.0, 0.0, 0.0, -1.0)


def _file(dataset, transfer_syntax=EXPLICIT_VR_LITTLE_ENDIAN):
    meta = pydicom.dataset.FileMetaDataset()
    meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    meta.TransferSyntaxUID = transfer_syntax
    dataset.file_meta = meta
    buffer = io.BytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def _image(
    pixels,
    *,
    number=1,
    series=SERIES,
    z=None,
    orientation=AXIAL,
    origin=None,
    spacing=(1.0, 1.0),
    photometric="MONOCHROME2",
    rescale=None,
    sop_class=CT_IMAGE_STORAGE,
):
    """A written image file; pixels are (rows, columns) or (frames, rows, columns)."""
    pixels = np.asarray(pixels)
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = f"2.25.8{number:04d}"
    if series is not None:
        dataset.SeriesInstanceUID = series
    dataset.InstanceNumber = number
    colour = photometric == "RGB"
    frames = pixels.shape[0] if pixels.ndim == (4 if colour else 3) else 1
    rows, columns = pixels.shape[-3:-1] if colour else pixels.shape[-2:]
    if frames > 1:
        dataset.NumberOfFrames = frames
    dataset.Rows, dataset.Columns = rows, columns
    dataset.SamplesPerPixel = 3 if colour else 1
    dataset.PhotometricInterpretation = photometric
    if colour:
        dataset.PlanarConfiguration = 0
        dataset.BitsAllocated = dataset.BitsStored = 8
        dataset.HighBit = 7
        dataset.PixelRepresentation = 0
        dataset.PixelData = pixels.astype(np.uint8).tobytes()
    else:
        dataset.BitsAllocated = dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 1
        dataset.PixelData = pixels.astype("<i2").tobytes()
    if spacing is not None:
        dataset.PixelSpacing = list(spacing)
    if z is not None or origin is not None:
        dataset.ImageOrientationPatient = list(orientation)
        dataset.ImagePositionPatient = list(origin if origin is not None else (0, 0, z))
    if rescale is not None:
        dataset.RescaleSlope, dataset.RescaleIntercept = rescale
    return _file(dataset)


def _decoded(data):
    """Read a PNG back as an array, checking its structure and every CRC."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, chunks = 8, []
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        (crc,) = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])
        assert crc == zlib.crc32(kind + body) & 0xFFFFFFFF
        chunks.append((kind, body))
        offset += 12 + length
    assert [kind for kind, _ in chunks] == [b"IHDR", b"IDAT", b"IEND"]
    columns, rows, depth, colour_type, *_ = struct.unpack(">IIBBBBB", chunks[0][1])
    assert depth == 8
    samples = {0: 1, 2: 3}[colour_type]
    raw = np.frombuffer(zlib.decompress(chunks[1][1]), np.uint8)
    raw = raw.reshape(rows, 1 + columns * samples)
    assert not raw[:, 0].any()
    image = raw[:, 1:]
    return image.reshape(rows, columns, 3) if samples == 3 else image


def _slices(count, rows=4, columns=5, spacing_z=1.0):
    return {
        position: _image(
            np.full((rows, columns), 100 * position),
            number=position + 1,
            z=position * spacing_z,
        )
        for position in range(count)
    }


@pytest.mark.pydicom
def test_a_png_holds_only_its_pixels():
    grey = np.arange(12, dtype=np.uint8).reshape(3, 4)
    colour = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)

    assert (_decoded(qc_previews.png(grey)) == grey).all()
    assert (_decoded(qc_previews.png(colour)) == colour).all()
    assert qc_previews.png(grey) == qc_previews.png(grey.copy())
    for refused in (
        grey.astype(np.int16),
        np.zeros((2, 2, 4), np.uint8),
        np.zeros((0, 3), np.uint8),
    ):
        with pytest.raises(ValueError):
            qc_previews.png(refused)


@pytest.mark.pydicom
def test_a_series_gets_a_cine_strip_in_slice_order():
    # Given out of order, and with Instance Numbers that disagree with the
    # positions, which come first.
    written = {
        0: _image(np.full((4, 5), 300), number=1, z=20.0),
        1: _image(np.full((4, 5), 100), number=3, z=0.0),
        2: _image(np.full((4, 5), 200), number=2, z=10.0),
    }

    previews = qc_previews.previews_of(written, ())

    cine = previews.previews[0]
    assert cine.name == "P-0001.png" and cine.kind is PreviewKind.SERIES_CINE
    assert cine.frames == ((1, 0), (2, 0), (0, 0))
    assert cine.total_frames == 3
    image = _decoded(cine.png)
    assert image.shape == (qc_previews.TILE_PIXELS, 3 * qc_previews.TILE_PIXELS)
    # Each tile is centred in its cell, scaled to fit, and windowed together.
    centre = qc_previews.TILE_PIXELS // 2
    tiles = [image[centre, centre + i * qc_previews.TILE_PIXELS] for i in range(3)]
    assert tiles[0] < tiles[1] < tiles[2]
    assert tiles[0] == 0 and tiles[2] == 255
    assert not previews.not_previewed


@pytest.mark.pydicom
def test_a_long_series_shows_frames_evenly_spaced_from_first_to_last():
    previews = qc_previews.previews_of(_slices(40), ())

    cine = previews.previews[0]
    positions = [position for position, _ in cine.frames]
    assert len(positions) == qc_previews.CINE_FRAMES
    assert positions[0] == 0 and positions[-1] == 39
    assert positions == sorted(set(positions))
    assert max(np.diff(positions)) - min(np.diff(positions)) <= 1
    assert cine.total_frames == 40
    image = _decoded(cine.png)
    rows = qc_previews.CINE_FRAMES // qc_previews.CINE_COLUMNS
    assert image.shape == (
        rows * qc_previews.TILE_PIXELS,
        qc_previews.CINE_COLUMNS * qc_previews.TILE_PIXELS,
    )


@pytest.mark.pydicom
def test_a_tile_keeps_the_aspect_of_its_pixel_spacing():
    written = {0: _image(np.ones((10, 10)), spacing=(2.0, 1.0), series=None)}

    image = _decoded(qc_previews.previews_of(written, ()).previews[0].png)

    lit = np.argwhere(image > 0)
    height = lit[:, 0].max() - lit[:, 0].min() + 1
    width = lit[:, 1].max() - lit[:, 1].min() + 1
    assert (height, width) == (qc_previews.TILE_PIXELS, qc_previews.TILE_PIXELS // 2)


@pytest.mark.pydicom
def test_monochrome1_is_inverted_and_rescale_is_applied():
    low, high = np.zeros((4, 4)), np.full((4, 4), 10)
    inverted = {
        0: _image(low, number=1, series="2.25.1", photometric="MONOCHROME1"),
        1: _image(high, number=2, series="2.25.1", photometric="MONOCHROME1"),
    }
    # A negative slope turns the order of the stored values around.
    rescaled = {
        0: _image(low, number=1, series="2.25.2", rescale=(-1, 0)),
        1: _image(high, number=2, series="2.25.2", rescale=(-1, 0)),
    }
    centre = qc_previews.TILE_PIXELS // 2

    for written in (inverted, rescaled):
        image = _decoded(qc_previews.previews_of(written, ()).previews[0].png)
        assert image[centre, centre] == 255
        assert image[centre, centre + qc_previews.TILE_PIXELS] == 0


@pytest.mark.pydicom
def test_a_volume_gets_a_frontal_projection_head_up_and_right_on_the_left():
    # Axial slices 3 mm apart, 1 mm pixels. One bright voxel, in the most
    # superior slice, at the patient's right (column 0, as the row direction
    # is towards the patient's left) and the most posterior row.
    count, rows, columns = 4, 6, 5
    written = {}
    for position in range(count):
        pixels = np.zeros((rows, columns))
        if position == count - 1:
            pixels[rows - 1, 0] = 1000
        written[position] = _image(pixels, number=position + 1, z=3.0 * position)

    previews = qc_previews.previews_of(written, ())

    mip = previews.previews[1]
    assert mip.name == "P-0002.png" and mip.kind is PreviewKind.SERIES_MIP
    assert mip.frames == tuple((position, 0) for position in range(count))
    assert mip.total_frames == count
    image = _decoded(mip.png)
    # Superior-inferior is 9 mm at 1 mm a pixel; left-right 5 columns. The
    # rows nearest the superior slice, 8 and 9 mm up, show it.
    assert image.shape == (10, columns)
    assert (image[:2, 0] == 255).all()
    assert image.sum() == 2 * 255


@pytest.mark.pydicom
def test_the_projection_follows_the_direction_cosines():
    # The row direction runs to the patient's right, and the slices are given
    # from superior to inferior: the bright voxel is still at top left.
    count, rows, columns = 3, 4, 5
    flipped = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    written = {}
    for position in range(count):
        pixels = np.zeros((rows, columns))
        if position == 0:
            pixels[0, columns - 1] = 1000
        written[position] = _image(
            pixels,
            number=position + 1,
            origin=(0, 0, 10.0 - position),
            orientation=flipped,
        )
    coronal = {}
    for position in range(count):
        # A coronal plane: rows run inferior, so row 0 is the most superior.
        pixels = np.zeros((rows, columns))
        if position == 0:
            pixels[0, 0] = 1000
        coronal[position] = _image(
            pixels,
            number=position + 1,
            series="2.25.9",
            origin=(0, position, 0),
            orientation=CORONAL,
        )

    for each in (written, coronal):
        mip = qc_previews.previews_of(each, ()).previews[1]
        image = _decoded(mip.png)
        assert image[0, 0] == 255
        assert image.sum() == 255


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "case",
    [
        "two slices",
        "rotated about z",
        "tilted",
        "oblique",
        "mixed sizes",
        "repeated position",
        "no spacing",
    ],
)
def test_a_series_that_is_not_a_volume_gets_no_projection(case):
    # Each oblique stack is stacked along its normal, so only the alignment of
    # its axes with the patient's refuses it: a projection along an oblique
    # column would superimpose what a frontal view keeps apart.
    angle = math.radians(30 if case == "rotated about z" else 0.1)
    cosine, sine = round(math.cos(angle), 6), round(math.sin(angle), 6)
    rotated = (cosine, sine, 0.0, -sine, cosine, 0.0)
    orientation = {
        "rotated about z": rotated,
        "tilted": rotated,
        "oblique": (0.6, 0.64, 0.48, 0.0, 0.6, -0.8),
    }.get(case, AXIAL)
    normal = np.cross(orientation[:3], orientation[3:])
    written = {
        position: _image(
            np.ones((5, 6) if case == "mixed sizes" and position == 1 else (4, 6)),
            number=position + 1,
            origin=tuple(
                round(float(component), 6)
                for component in normal
                * (0.0 if case == "repeated position" and position == 1 else position)
            ),
            orientation=orientation,
            spacing=None if case == "no spacing" else (1.0, 1.0),
        )
        for position in range(2 if case == "two slices" else 3)
    }

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [PreviewKind.SERIES_CINE]


@pytest.mark.pydicom
def test_axes_within_the_alignment_tolerance_still_get_a_projection():
    # Direction cosines written to six decimal places are aligned.
    nearly = (1.0, 0.00001, 0.0, -0.00001, 1.0, 0.0)
    written = {
        position: _image(
            np.ones((4, 6)), number=position + 1, z=float(position), orientation=nearly
        )
        for position in range(3)
    }

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
    ]


@pytest.mark.pydicom
def test_a_high_risk_instance_is_previewed_at_full_resolution():
    frames = np.arange(20 * 30 * 40).reshape(20, 30, 40) % 1000
    written = {
        0: _image(np.ones((4, 4)), number=1, series="2.25.1"),
        1: _image(frames, number=2, series="2.25.2", sop_class=SECONDARY_CAPTURE),
    }

    previews = qc_previews.previews_of(written, {1, 5})

    assert [preview.kind for preview in previews.previews] == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_CINE,
        PreviewKind.INSTANCE,
    ]
    instance = previews.previews[2]
    assert instance.name == "P-0003.png"
    assert len(instance.frames) == qc_previews.CINE_FRAMES
    assert instance.frames[0] == (1, 0) and instance.frames[-1] == (1, 19)
    assert instance.total_frames == 20
    image = _decoded(instance.png)
    rows = qc_previews.CINE_FRAMES // qc_previews.CINE_COLUMNS
    assert image.shape == (rows * 30, qc_previews.CINE_COLUMNS * 40)


@pytest.mark.pydicom
def test_an_rgb_capture_is_shown_in_colour():
    pixels = np.zeros((3, 4, 3), np.uint8)
    pixels[..., 0] = 200
    written = {
        0: _image(pixels, photometric="RGB", series=None, sop_class=SECONDARY_CAPTURE)
    }

    previews = qc_previews.previews_of(written, {0})

    image = _decoded(previews.previews[1].png)
    assert image.shape == (3, 4, 3)
    assert (image[..., 0] == 200).all() and not image[..., 1:].any()


def _encapsulated():
    dataset = pydicom.dcmread(io.BytesIO(_image(np.ones((4, 4)), series=None)))
    dataset.PixelData = pydicom.encaps.encapsulate([b"\x00" * 32])
    dataset["PixelData"].VR = "OB"
    return _file(dataset, RLE_LOSSLESS)


def _palette():
    dataset = pydicom.dcmread(io.BytesIO(_image(np.ones((4, 4)), series=None)))
    dataset.PhotometricInterpretation = "PALETTE COLOR"
    return _file(dataset)


def _float_pixels():
    dataset = pydicom.dcmread(io.BytesIO(_image(np.ones((4, 4)), series=None)))
    del dataset.PixelData
    dataset.FloatPixelData = np.ones(16, "<f4").tobytes()
    return _file(dataset)


def _short_pixels():
    dataset = pydicom.dcmread(io.BytesIO(_image(np.ones((4, 4)), series=None)))
    dataset.PixelData = b"\x00\x00"
    return _file(dataset)


def _structure_set():
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = RT_STRUCTURE_SET
    dataset.SOPInstanceUID = "2.25.9999"
    return _file(dataset)


@pytest.mark.pydicom
def test_an_instance_that_cannot_be_previewed_is_listed_with_why():
    written = {
        0: _encapsulated(),
        1: _palette(),
        2: _float_pixels(),
        3: _short_pixels(),
        4: b"not a DICOM file",
        5: _structure_set(),
        6: _structure_set(),
    }

    previews = qc_previews.previews_of(written, {5})

    assert not previews.previews
    assert previews.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.COMPRESSED),
        NotPreviewedEntry(1, NotPreviewedReason.UNSUPPORTED),
        NotPreviewedEntry(2, NotPreviewedReason.UNSUPPORTED),
        NotPreviewedEntry(3, NotPreviewedReason.UNREADABLE),
        NotPreviewedEntry(4, NotPreviewedReason.UNREADABLE),
        NotPreviewedEntry(5, NotPreviewedReason.NO_PIXEL_DATA),
    )


@pytest.mark.pydicom
def test_a_slice_that_cannot_be_decoded_leaves_its_series_without_a_projection():
    written = _slices(4)
    dataset = pydicom.dcmread(io.BytesIO(written[2]))
    dataset.PixelData = b"\x00\x00"
    written[2] = _file(dataset)

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [PreviewKind.SERIES_CINE]
    assert [position for position, _ in previews.previews[0].frames] == [0, 1, 3]
    assert previews.previews[0].total_frames == 4
    assert previews.not_previewed == (
        NotPreviewedEntry(2, NotPreviewedReason.UNREADABLE),
    )


@pytest.mark.pydicom
def test_series_come_in_order_of_their_first_instance():
    written = {
        0: _image(np.ones((4, 4)), number=1, series="2.25.2"),
        1: _image(np.ones((4, 4)), number=1, series=None),
        2: _image(np.ones((4, 4)), number=2, series="2.25.1"),
        3: _image(np.ones((4, 4)), number=3, series="2.25.2"),
    }

    previews = qc_previews.previews_of(written, ())

    assert [preview.frames for preview in previews.previews] == [
        ((0, 0), (3, 0)),
        ((1, 0),),
        ((2, 0),),
    ]


@pytest.mark.pydicom
def test_padding_is_left_out_of_the_window_and_shown_black():
    pixels = np.full((4, 8), -32768)
    pixels[:, 4:] = 0
    pixels[0, 4] = 100
    dataset = pydicom.dcmread(io.BytesIO(_image(pixels, series=None)))
    dataset.add_new(0x00280120, "SS", -32768)  # Pixel Padding Value
    written = {0: _file(dataset)}

    image = _decoded(qc_previews.previews_of(written, {0}).previews[1].png)

    assert not image[:, :4].any()
    # Windowed from what is not padding: 0 to 100, not -32768 to 100.
    assert image[1, 5] == 0 and image[0, 4] == 255


@pytest.mark.pydicom
def test_padding_is_shown_black_when_monochrome1_is_inverted():
    pixels = np.full((4, 8), -32768)
    pixels[:, 4:] = 0
    pixels[0, 4] = 100
    dataset = pydicom.dcmread(
        io.BytesIO(_image(pixels, series=None, photometric="MONOCHROME1"))
    )
    dataset.add_new(0x00280120, "SS", -32768)  # Pixel Padding Value
    written = {0: _file(dataset)}

    image = _decoded(qc_previews.previews_of(written, {0}).previews[1].png)

    assert not image[:, :4].any()
    # Inverted: the lowest value is white and the highest black.
    assert image[1, 5] == 255 and image[0, 4] == 0


@pytest.mark.pydicom
def test_a_projection_keeps_its_last_column_and_slice():
    # 0.7 mm pixels: 3 * 0.7 / 0.7 falls just short of 3 in floating point.
    count, rows, columns = 4, 4, 4
    written = {}
    for position in range(count):
        pixels = np.zeros((rows, columns))
        if position == 0:
            pixels[0, columns - 1] = 1000
        written[position] = _image(
            pixels, number=position + 1, z=0.7 * position, spacing=(0.7, 0.7)
        )

    image = _decoded(qc_previews.previews_of(written, ()).previews[1].png)

    assert image.shape == (count, columns)
    assert image[count - 1, columns - 1] == 255


@pytest.mark.pydicom
@pytest.mark.parametrize("shift", [(5.0, 0.0, 0.0), (0.0, 0.5, 0.0)])
def test_slices_that_do_not_stack_along_the_normal_get_no_projection(shift):
    # Offset within the plane, or sheared as by a gantry tilt.
    written = {
        position: _image(
            np.ones((4, 4)),
            number=position + 1,
            origin=tuple(
                position * (axis + (1.0 if i == 2 else 0.0))
                for i, axis in enumerate(shift)
            ),
        )
        for position in range(3)
    }

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [PreviewKind.SERIES_CINE]


@pytest.mark.pydicom
def test_attributes_that_only_adjust_a_preview_are_read_tolerantly():
    dataset = pydicom.dcmread(io.BytesIO(_image(np.ones((4, 4)), series=None)))
    dataset.RescaleSlope = ["1", "2"]
    dataset.InstanceNumber = None
    written = {0: _file(dataset)}

    previews = qc_previews.previews_of(written, ())

    assert len(previews.previews) == 1 and not previews.not_previewed


@pytest.mark.pydicom
def test_only_the_frames_shown_are_decoded(monkeypatch):
    decode = pydicom.pixels.pixel_array
    calls = []

    def counted(source, **kwargs):
        calls.append(kwargs.get("index"))
        return decode(source, **kwargs)

    monkeypatch.setattr(pydicom.pixels, "pixel_array", counted)
    frames = np.arange(40 * 4 * 4).reshape(40, 4, 4)
    written = {0: _image(frames, series=None, sop_class=SECONDARY_CAPTURE)}

    qc_previews.previews_of(written, {0})

    # Sixteen frames for the cine strip, and the same again for the instance.
    assert None not in calls and len(calls) == 2 * qc_previews.CINE_FRAMES


@pytest.mark.pydicom
def test_the_same_files_give_the_same_previews():
    first = qc_previews.previews_of(_slices(5), {2})
    second = qc_previews.previews_of(_slices(5), {2})

    assert [preview.png for preview in first.previews] == [
        preview.png for preview in second.previews
    ]
