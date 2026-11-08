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

"""Previews of floating-point pixel data: values that are not a number,
infinities, padding, and windows that keep a pattern apart from the values
around it.

Every image is synthetic.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_previews
from pymedphys._dicom.deidentify.qc_pack import NotPreviewedEntry, NotPreviewedReason

from .test_deidentify_qc_previews import FLOAT_KEYWORDS, _decoded, _floated, _image


def _float_frame(rows=4, columns=8):
    """Not a number in the left half; 0 to 100, with each infinity, in the
    right."""
    pixels = np.full((rows, columns), np.nan)
    pixels[:, 4:] = 0
    pixels[0, 4] = 100
    pixels[2, 5] = np.inf
    pixels[3, 5] = -np.inf
    return pixels


@pytest.mark.pydicom
@FLOAT_KEYWORDS
def test_not_a_number_is_shown_black_and_infinities_beyond_the_finite_extremes(
    keyword,
):
    data = _image(np.zeros((4, 8)), series=None)
    written = {0: _floated(data, keyword, values=_float_frame())}

    previews = qc_previews.previews_of(written, {0})
    image = _decoded(previews.previews[1].png)

    assert not image[:, :4].any()
    # Positive infinity is drawn as 200 and negative infinity as -100, a
    # range beyond the finite values, 0 to 100, so that each stands apart
    # from the finite value at its end.
    assert image[2, 5] == 255 and image[3, 5] == 0
    assert 0 < image[1, 5] < image[0, 4] < 255
    assert previews.pixels_shown == {0}


_INFINITIES = pytest.mark.parametrize(
    "infinities",
    [(np.inf,), (-np.inf,), (np.inf, -np.inf)],
    ids=["positive", "negative", "both"],
)


def _infinite_pattern(infinities, value=0.0):
    """A frame of ``value`` with a block of each of ``infinities``, row by
    row, and the block's mask."""
    pixels = np.full((4, 8), value)
    for row, infinity in enumerate(infinities, start=1):
        pixels[row, 2:6] = infinity
    return pixels, np.isinf(pixels)


@pytest.mark.pydicom
@FLOAT_KEYWORDS
@_INFINITIES
@pytest.mark.parametrize("value", [0.0, -7.5, 3e4])
def test_infinities_among_finite_values_all_alike_are_drawn_apart(
    keyword, infinities, value
):
    # Drawn as the finite extremes, a pattern of infinity among finite values
    # that are all one value would be one grey in every preview, while the
    # instance counted as shown whole; so each infinity is drawn beyond
    # that value, and the pattern shows.
    pixels, pattern = _infinite_pattern(infinities, value)
    data = _image(np.zeros((4, 8)), series=None)
    written = {0: _floated(data, keyword, values=pixels)}

    previews = qc_previews.previews_of(written, {0})

    assert previews.pixels_shown == {0}
    full = [_decoded(preview.png) for preview in previews.previews]
    full = [image for image in full if image.shape == pixels.shape]
    assert full
    for image in full:
        background = set(np.unique(image[~pattern]).tolist())
        assert len(background) == 1
        levels = {
            infinity: np.unique(image[pixels == infinity]) for infinity in infinities
        }
        for infinity, level in levels.items():
            assert len(level) == 1 and level[0] not in background
            assert (level[0] > min(background)) == (infinity > 0)
        assert len({int(level[0]) for level in levels.values()}) == len(infinities)


@pytest.mark.pydicom
@FLOAT_KEYWORDS
@pytest.mark.parametrize(
    "pattern, background",
    [
        (-np.inf, 1e20),
        (np.inf, 1e20),
        (-np.inf, -3e30),
        (1e20 * (1 + 2.0**-6), 1e20),
        (1e-10, 0.0),
    ],
    ids=[
        "negative-infinity-on-1e20",
        "positive-infinity-on-1e20",
        "negative-infinity-on-minus-3e30",
        "a-close-value-on-1e20",
        "1e-10-on-0",
    ],
)
def test_a_sparse_pattern_on_one_value_is_drawn_apart_in_every_preview(
    keyword, pattern, background
):
    # Ten pixels of 64 by 64, fewer than the 0.5% that the percentile window
    # leaves out at each end, so both its percentiles are the background; a
    # window of fixed width about it would draw the pattern as the
    # background, so each preview is drawn over the full range instead.
    pixels = np.full((64, 64), background)
    pixels[20:22, 20:25] = pattern
    data = _image(np.zeros((64, 64)), series=None)
    written = {0: _floated(data, keyword, values=pixels)}

    previews = qc_previews.previews_of(written, {0})

    assert previews.pixels_shown == {0}
    assert previews.previews
    for preview in previews.previews:
        image = _decoded(preview.png)
        assert len(np.unique(image)) > 1, preview.kind
    (full,) = [
        _decoded(preview.png)
        for preview in previews.previews
        if _decoded(preview.png).shape == pixels.shape
    ]
    (inside,) = np.unique(full[20:22, 20:25])
    (outside,) = np.unique(full[pixels != pattern])
    assert inside != outside


@pytest.mark.parametrize(
    "values",
    [np.full(8, 1e20), np.full(8, -7.5), np.zeros(8)],
    ids=["1e20", "minus-7.5", "zero"],
)
def test_a_uniform_image_is_drawn_mid_grey_at_any_magnitude(values):
    # pylint: disable-next=protected-access
    for window in (qc_previews._window(values), qc_previews._full_range(values)):
        # pylint: disable-next=protected-access
        grey = qc_previews._grey(values.astype(np.float32), window, False)
        assert np.all(np.abs(grey.astype(int) - 128) <= 1)


@_INFINITIES
@pytest.mark.parametrize("dtype", ["<f4", "<f8"])
def test_a_review_frame_draws_infinities_among_finite_values_all_alike_apart(
    infinities, dtype
):
    pixels, pattern = _infinite_pattern(infinities)
    # pylint: disable-next=protected-access
    shown, undrawn, kinds = qc_previews._drawn_floats(pixels.astype(dtype), None)

    frame = qc_previews.review_frame(shown.astype(np.float32))

    assert not undrawn.any() and kinds == 0
    assert len(np.unique(frame[~pattern])) == 1
    assert len(np.unique(frame)) == 1 + len(infinities)


@pytest.mark.pydicom
def test_a_float_frame_whose_infinities_float32_cannot_hold_is_not_previewed():
    # Positive infinity beside the largest double that float32 holds as
    # finite would be drawn beyond float32, so the frame is not previewed.
    pixels = np.zeros((4, 8))
    pixels[0, 0] = -3e38
    pixels[0, 1] = 3e38
    pixels[1, 2] = np.inf
    data = _image(np.zeros((4, 8)), series=None)
    written = {0: _floated(data, "DoubleFloatPixelData", values=pixels)}

    previews = qc_previews.previews_of(written, {0})

    assert previews.pixels_shown == set()
    assert [entry.reason for entry in previews.not_previewed] == [
        NotPreviewedReason.UNSUPPORTED
    ]


@pytest.mark.pydicom
@FLOAT_KEYWORDS
@pytest.mark.parametrize("limit", [None, -1e30])
def test_floating_point_padding_is_left_out_of_the_window_and_shown_black(
    keyword, limit
):
    pixels = np.full((4, 8), -3e38)
    if limit is not None:
        pixels[:, 1] = -2e30  # within the range limit
    pixels[:, 4:] = 0
    pixels[0, 4] = 100
    data = _image(np.zeros((4, 8)), series=None)
    written = {0: _floated(data, keyword, values=pixels, padding=(-3e38, limit))}

    previews = qc_previews.previews_of(written, {0})
    image = _decoded(previews.previews[1].png)

    assert not image[:, :4].any()
    assert image[1, 5] == 0 and image[0, 4] == 255
    # The range holds two padding values, which no preview tells apart.
    assert previews.pixels_shown == (set() if limit is not None else {0})


def _payload(pixels, dtype):
    """``pixels`` with their values that are not a number of two payloads."""
    values = np.asarray(pixels, dtype=dtype)
    words = values.view(dtype.replace("f", "u"))
    words[0, 0] |= 1
    return values


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "change, shown",
    [
        (lambda pixels: pixels, True),
        (lambda pixels: _payload(pixels, "<f4"), True),
        (lambda pixels: np.where(np.isnan(pixels), -3e38, pixels), True),
        (lambda pixels: np.where(pixels == 0, -3e38, pixels), False),
        (lambda pixels: np.where(np.isfinite(pixels), np.nan, pixels), False),
        (lambda pixels: np.where(np.isnan(pixels), np.inf, np.nan), False),
    ],
    ids=[
        "not-a-number",
        "two-payloads",
        "padding",
        "not-a-number-and-padding",
        "not-a-number-and-infinities",
        "infinity-and-not-a-number",
    ],
)
def test_values_not_drawn_of_more_than_one_kind_are_not_shown_whole(change, shown):
    # Not a number, whatever its bits, each infinity in a frame without a
    # finite value to draw it as, and each padding value are drawn alike,
    # so a frame that holds more than one could hold a face in their
    # pattern that no preview shows.
    data = _image(np.zeros((4, 8)), series=None)
    pixels = change(_float_frame())
    written = {0: _floated(data, values=pixels, padding=(-3e38, None))}

    previews = qc_previews.previews_of(written, {0})

    assert previews.previews
    assert previews.pixels_shown == ({0} if shown else set())


@pytest.mark.pydicom
def test_a_double_that_float32_cannot_hold_is_listed_as_not_previewed():
    pixels = np.zeros((4, 8))
    pixels[0, 0] = 1e300
    data = _image(np.zeros((4, 8)), series=None)
    written = {0: _floated(data, "DoubleFloatPixelData", values=pixels)}

    previews = qc_previews.previews_of(written, {0})

    assert previews.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.UNSUPPORTED),
    )
    assert not previews.pixels_shown


@pytest.mark.pydicom
@FLOAT_KEYWORDS
@pytest.mark.parametrize(
    "background, pattern",
    [(-3e38, 3e38), (3e38, -3e38)],
    ids=["high-on-low", "low-on-high"],
)
def test_values_further_apart_than_float32_holds_are_drawn_apart(
    keyword, background, pattern
):
    # Each value fits float32, but their difference does not; drawn in
    # float32 without care, the window's width would overflow and the image
    # be black.
    pixels = np.full((64, 64), background)
    pixels[20:22, 20:25] = pattern
    data = _image(np.zeros((64, 64)), series=None)
    written = {0: _floated(data, keyword, values=pixels)}

    previews = qc_previews.previews_of(written, {0})

    assert previews.pixels_shown == {0}
    full = [
        image
        for image in (_decoded(preview.png) for preview in previews.previews)
        if image.shape == pixels.shape
    ]
    assert full
    for image in full:
        assert set(np.unique(image[20:22, 20:25]).tolist()) == {
            255 if pattern > 0 else 0
        }
        assert set(np.unique(image[pixels != pattern]).tolist()) == {
            0 if pattern > 0 else 255
        }
    for preview in previews.previews:
        assert len(np.unique(_decoded(preview.png))) > 1, preview.kind


@pytest.mark.pydicom
@FLOAT_KEYWORDS
def test_an_infinity_beyond_a_wide_finite_range_is_drawn_apart(keyword):
    pixels = np.full((4, 8), -2e38)
    pixels[:, 4:] = -1e37
    pixels[1:3, 5:7] = np.inf
    data = _image(np.zeros((4, 8)), series=None)
    written = {0: _floated(data, keyword, values=pixels)}

    previews = qc_previews.previews_of(written, {0})

    assert previews.pixels_shown == {0}
    image = _decoded(previews.previews[1].png)
    levels = [int(np.unique(image[pixels == value])[0]) for value in (-2e38, -1e37)]
    (infinity,) = np.unique(image[np.isinf(pixels)])
    assert len(np.unique(image[pixels == -2e38])) == 1
    assert levels[0] < levels[1] < infinity


def test_the_grey_of_a_window_wider_than_float32_holds_is_not_black():
    image = np.array([[-3e38, 0.0, 3e38]], dtype=np.float32)

    # pylint: disable-next=protected-access
    grey = qc_previews._grey(image, (-3e38, 3e38), False)

    assert grey.tolist() == [[0, 128, 255]]
