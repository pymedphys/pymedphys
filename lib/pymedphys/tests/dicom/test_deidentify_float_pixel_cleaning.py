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

"""Clean Pixel Data's blackout of text in Float Pixel Data and Double Float
Pixel Data, as a Parametric Map can hold its frames (D-037).

Every file is synthetic, and every finder is a stand-in that gives fixed
regions, so no model is downloaded and no network is reached.
"""

import dataclasses

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import pixel_cleaning
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    black_out,
    redaction_problem,
)
from pymedphys._dicom.deidentify.reasons import PixelDataReason, TransformReason
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_references as synthetic
from .test_deidentify_pixel_cleaning import (
    IMPLICIT_VR_LITTLE_ENDIAN,
    Finder,
    _blacked_out,
    _inside,
    _pixels,
    _source,
    _with,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]


# Float Pixel Data and Double Float Pixel Data, with their Bits Allocated
# and the unsigned word that holds each value's bits.
FLOATS = pytest.mark.parametrize(
    "keyword, dtype",
    [("FloatPixelData", "<f4"), ("DoubleFloatPixelData", "<f8")],
    ids=["float", "double"],
)
# Not a number with a payload, which a viewer cannot tell from any other.
_PAYLOAD_NAN = {"<f4": 0x7FC0_1234, "<f8": 0x7FF8_0000_0000_1234}


def _floating(frames, keyword, dtype):
    """A CT slice whose pixel data are ``frames`` of floating-point values,
    in the Floating Point or Double Floating Point Image Pixel Module."""
    values = np.asarray(frames, dtype=dtype)
    if values.ndim == 2:
        values = values[np.newaxis]
    dataset = synthetic.ct_slice(0)
    for attribute in ("PixelData", "BitsStored", "HighBit", "PixelRepresentation"):
        if attribute in dataset:
            delattr(dataset, attribute)
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = values.shape[1:]
    dataset.BitsAllocated = values.dtype.itemsize * 8
    if values.shape[0] > 1:
        dataset.NumberOfFrames = values.shape[0]
    setattr(dataset, keyword, values.tobytes())
    return dataset


def _float_frame(dtype, rows=6, columns=8):
    """A frame of floating-point values with a value that is not a number,
    of a payload, both infinities, and both zeros."""
    frame = (np.arange(rows * columns).reshape(rows, columns) * 12.5 - 40).astype(dtype)
    words = frame.view(f"<u{np.dtype(dtype).itemsize}")
    words[5, 7] = _PAYLOAD_NAN[dtype]
    frame[4, 0], frame[4, 1] = np.inf, -np.inf
    frame[5, 0], frame[5, 1] = 0.0, -0.0
    return frame


def _float_replaced(source, redaction, keyword):
    """The source's file with its floating-point pixel data replaced by the
    redaction's."""
    dataset = source.dataset()
    setattr(dataset, keyword, redaction.value)
    return read_source(synthetic.written(dataset, source.transfer_syntax))


def _words(values, dtype):
    return np.asarray(values, dtype=dtype).view(f"<u{np.dtype(dtype).itemsize}")


@FLOATS
@pytest.mark.parametrize(
    "transfer_syntax", [synthetic.EXPLICIT_VR_LITTLE_ENDIAN, IMPLICIT_VR_LITTLE_ENDIAN]
)
@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_floating_point_text_is_set_to_the_frames_smallest_finite_value(
    keyword, dtype, transfer_syntax
):
    frame = _float_frame(dtype)
    source, redaction = _blacked_out(
        _floating(frame, keyword, dtype), transfer_syntax=transfer_syntax
    )

    assert redaction.layout.floating
    assert (
        redaction.layout.element
        == pixel_cleaning.FLOAT_PIXEL_DATA[keyword == "DoubleFloatPixelData"]
    )
    assert redaction.reason is PixelDataReason.TEXT_BLACKED_OUT
    (regions,) = redaction.regions
    finite = frame[np.isfinite(frame)]
    assert regions.value == (float(finite.min()),)
    output = _float_replaced(source, redaction, keyword)
    assert output.transfer_syntax == transfer_syntax
    pixels = _pixels(output)
    assert pixels.dtype == np.dtype(dtype)
    inside = _inside(frame.shape)
    assert np.all(pixels[inside] == finite.min())
    # Every value outside the region keeps its bits: the payload of the
    # value that is not a number, each infinity, and the sign of each zero.
    assert np.array_equal(_words(pixels, dtype)[~inside], _words(frame, dtype)[~inside])
    assert not redaction_problem(source, output, redaction)


@FLOATS
def test_a_floating_point_frame_without_text_is_written_as_it_was(keyword, dtype):
    frame = _float_frame(dtype)
    source, redaction = _blacked_out(_floating(frame, keyword, dtype), Finder(()))

    assert not redaction.regions and not redaction.changed
    assert redaction.value == source.value_field(redaction.layout.element)
    assert redaction.reason is PixelDataReason.NO_TEXT_FOUND


@FLOATS
def test_each_floating_point_frame_is_searched_as_scaled_finite_values(keyword, dtype):
    frames = np.stack([_float_frame(dtype), _float_frame(dtype) * 4])
    finder = Finder(frames={1})
    source, redaction = _blacked_out(_floating(frames, keyword, dtype), finder)

    for seen, frame in zip(finder.seen, frames, strict=True):
        assert seen.dtype == np.float64 and np.isfinite(seen).all()
        drawn = np.isfinite(frame)
        # Scaled by a power of two, exactly, into -1 to 1.
        nonzero = drawn & (frame != 0)
        ratios = seen[nonzero] / frame[nonzero].astype(np.float64)
        assert len(np.unique(ratios)) == 1
        assert np.log2(ratios[0]).is_integer()
        assert np.abs(seen[drawn]).max() <= 1
        # Each infinity lies beyond the finite values by their range, and
        # not a number below negative infinity by as much again.
        low, high = seen[drawn].min(), seen[drawn].max()
        gap = high - low
        assert seen[4, 0] == high + gap
        assert seen[4, 1] == low - gap
        assert seen[5, 7] == low - gap - gap
    (regions,) = redaction.regions
    assert regions.frame == 1
    assert regions.value == (float(frames[1][np.isfinite(frames[1])].min()),)
    output = _float_replaced(source, redaction, keyword)
    assert not redaction_problem(source, output, redaction)


def test_values_near_the_largest_double_are_searched_without_overflow():
    frame = np.array([[-1.7e308, 1.7e308], [0.0, 1.0]])

    seen = pixel_cleaning.searched_values(frame)

    assert np.isfinite(seen).all()
    assert seen[0, 0] == -seen[0, 1] and seen[0, 1] <= 1
    assert seen[0, 1] - seen[0, 0] > 1


@pytest.mark.parametrize("dtype", ["<f4", "<f8"])
@pytest.mark.parametrize(
    "infinities",
    [(np.inf,), (-np.inf,), (np.inf, -np.inf)],
    ids=["positive", "negative", "both"],
)
@pytest.mark.parametrize("value", [0.0, -7.5, 3e4, np.nan])
def test_text_in_an_infinity_is_searched_apart_from_values_all_alike(
    dtype, infinities, value
):
    # Searched as the finite extremes, a pattern of infinity on finite values
    # that are all one value, or on values that are not a number, would be
    # one value to the finder; each kind of value is searched apart.
    frame = np.full((4, 8), value, dtype=dtype)
    for row, infinity in enumerate(infinities, start=1):
        frame[row, 2:6] = infinity

    seen = pixel_cleaning.searched_values(frame)

    assert np.isfinite(seen).all()
    background = np.unique(seen[~np.isinf(frame)])
    assert len(background) == 1
    for infinity in infinities:
        (level,) = np.unique(seen[frame == infinity])
        # Above or below finite values; not a number is below them all.
        assert (level > background[0]) == (infinity > 0 or np.isnan(value))
    assert len(np.unique(seen)) == 1 + len(infinities)


def test_infinities_are_searched_apart_from_finite_extremes_closer_than_a_gap():
    # The finite range is one step of float64 at 1, too small to move 1 by;
    # each infinity is still searched as a value of its own.
    high = 1.0
    low = float(np.nextafter(high, 0.0))
    frame = np.array([[low, high, np.inf, -np.inf, np.nan]])

    seen = pixel_cleaning.searched_values(frame)

    assert len(np.unique(seen)) == 5
    assert seen[0, 2] > seen[0, 1] > seen[0, 0] > seen[0, 3] > seen[0, 4]


@FLOATS
def test_a_frame_with_no_finite_value_is_searched_apart_and_filled_with_zero(
    keyword, dtype
):
    frame = np.full((6, 8), np.nan, dtype=dtype)
    frame[0, 0] = np.inf
    finder = Finder()
    source, redaction = _blacked_out(_floating(frame, keyword, dtype), finder)

    (seen,) = finder.seen
    # Positive infinity as 1, as though the finite values were all 0, and
    # not a number below the -1 of negative infinity.
    assert seen[0, 0] == 1 and np.all(seen.ravel()[1:] == -2)
    (regions,) = redaction.regions
    assert regions.value == (0.0,)
    output = _float_replaced(source, redaction, keyword)
    assert np.all(_pixels(output)[_inside(frame.shape)] == 0)
    assert not redaction_problem(source, output, redaction)


@FLOATS
def test_a_changed_bit_of_a_value_that_is_not_a_number_is_a_problem(keyword, dtype):
    frame = _float_frame(dtype)
    source, redaction = _blacked_out(_floating(frame, keyword, dtype))
    altered = _words(np.frombuffer(redaction.value, dtype), dtype).copy()
    altered[5 * 8 + 7] ^= 1  # still not a number, with another payload

    output = _float_replaced(
        source, dataclasses.replace(redaction, value=altered.tobytes()), keyword
    )

    assert redaction_problem(source, output, redaction)


@FLOATS
def test_floating_point_pixel_data_moved_to_another_element_is_a_problem(
    keyword, dtype
):
    frame = _float_frame(dtype)
    source, redaction = _blacked_out(_floating(frame, keyword, dtype))
    dataset = source.dataset()
    delattr(dataset, keyword)
    dataset.PixelData = redaction.value
    dataset["PixelData"].VR = "OB"
    output = read_source(synthetic.written(dataset, source.transfer_syntax))

    assert redaction_problem(source, output, redaction)


def _swapped_float(dataset):
    """Double Float Pixel Data under Bits Allocated 32."""
    dataset.DoubleFloatPixelData = dataset.FloatPixelData + dataset.FloatPixelData
    del dataset.FloatPixelData
    return dataset


def _two_floats(dataset):
    dataset.DoubleFloatPixelData = dataset.FloatPixelData + dataset.FloatPixelData
    return dataset


@pytest.mark.parametrize(
    "change",
    [
        _with(BitsAllocated=64),
        _swapped_float,
        _two_floats,
        _with(PhotometricInterpretation="MONOCHROME1"),
        _with(SamplesPerPixel=3),
        _with(Rows=None),
        _with(NumberOfFrames=0),
        _with(FloatPixelData=np.zeros(4, np.float32).tobytes()),
    ],
    ids=[
        "bits-allocated",
        "double-of-32-bits",
        "float-and-double",
        "monochrome1",
        "samples",
        "no-rows",
        "no-frames",
        "short",
    ],
)
def test_floating_point_pixel_data_that_cannot_be_read_as_frames_is_refused(change):
    dataset = change(_floating(_float_frame("<f4"), "FloatPixelData", "<f4"))
    source = _source(dataset)

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder())
    assert refused.value.reason is TransformReason.UNCLEANABLE_PIXEL_DATA


def test_no_overlay_is_cleared_in_floating_point_pixel_data():
    source = _source(_floating(_float_frame("<f4"), "FloatPixelData", "<f4"))

    with pytest.raises(ValueError, match="overlays"):
        black_out(source, source.dataset(), Finder(), overlays=1 << 31)


class _EveryPixel:
    """A defacer whose mask is every pixel of each frame."""

    def mask(self, frame, stored):
        return pixel_cleaning.FrameMask(frame, np.ones(stored.shape, bool), 0)


def test_no_defacers_mask_is_written_into_floating_point_pixel_data():
    source = _source(_floating(_float_frame("<f4"), "FloatPixelData", "<f4"))

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), None, _EveryPixel())
    assert refused.value.reason is TransformReason.UNCLEANABLE_PIXEL_DATA
