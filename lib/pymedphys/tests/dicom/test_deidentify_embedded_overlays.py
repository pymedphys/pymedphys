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

"""Overlays in unused bits of Pixel Data, cleared under Clean Graphics and
Clean Pixel Data (D-041, D-037).

PS3.3 before 2004 let an overlay lie in an unused bit plane of Pixel Data
(Section C.9.2): its group has no Overlay Data (60xx,3000), its Overlay
Bits Allocated (60xx,0100) is Bits Allocated, and its Overlay Bit Position
(60xx,0102) is the bit that holds it. Every file is synthetic, and every
finder is a stand-in that gives fixed regions.
"""

import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import clean_graphics, policy, run
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.pixel_cleaning import (
    black_out,
    overlay_planes,
    redaction_problem,
)
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    PixelDataReason,
    TransformReason,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.run_qc import PixelRiskMaterial
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_compressed as compressed
from . import _synthetic_references as synthetic
from .test_deidentify_clean_graphics import _with_overlay
from .test_deidentify_pixel_cleaning import BOX, Finder, _ct, _frame, _inside

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CLEAN_GRAPHICS = clean_graphics.CLEAN_GRAPHICS
CLEAN_PIXEL_DATA = policy.CLEAN_PIXEL_DATA
BASIC_PROFILE_CODE = "113100"
CLEAN_PIXEL_DATA_CODE = "113101"
CLEAN_GRAPHICS_CODE = "113103"
# Bits Stored is 12 in every image here, so bits 12 to 15 are unused.
OVERLAY_BIT = 13


def _embedded(dataset, bit=OVERLAY_BIT, group=0x6000, every=3):
    """Add an overlay group without Overlay Data that places its overlay in
    ``bit`` of Pixel Data, and set that bit in every ``every``-th word."""
    _with_overlay(dataset, group=group, data=False)
    dataset[group << 16 | 0x0100].value = dataset.BitsAllocated
    dataset[group << 16 | 0x0102].value = bit
    words = np.frombuffer(dataset.PixelData, "<u2").copy()
    words[::every] |= 1 << bit
    dataset.PixelData = words.tobytes()
    return dataset


def _signed_values():
    """Stored values from -24 to 23, so that half are negative."""
    return _frame(start=0) - 24


def _signed_frame():
    """:func:`_signed_values` as signed 12-bit words with the unused bits
    giving each value's sign."""
    return _signed_values().astype(np.int16).view(np.uint16)


def _transform(options, finder=None):
    return InstanceTransform(
        policy.compose_custom_policy(options),
        KEY,
        finder=finder,
        unvalidated_policy=True,
    )


def _transformed(
    transform, dataset, transfer_syntax=synthetic.EXPLICIT_VR_LITTLE_ENDIAN
):
    data = synthetic.written(dataset, transfer_syntax)
    return transform(data, InstanceRecord.from_file(data))


def _words(data):
    return np.frombuffer(pydicom.dcmread(io.BytesIO(data)).PixelData, "<u2")


def _codes(data):
    written = pydicom.dcmread(io.BytesIO(data))
    return [item.CodeValue for item in written.DeidentificationMethodCodeSequence]


def _source(dataset):
    return read_source(synthetic.written(dataset))


def _overlay_groups(data):
    """The overlay groups of a written file."""
    written = pydicom.dcmread(io.BytesIO(data))
    return sorted(
        {tag.group for tag in written.keys() if 0x6000 <= tag.group <= 0x601E}
    )


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_clean_graphics_clears_an_overlay_in_unused_bits_and_claims_the_option():
    source = _embedded(_ct(_frame()))
    before = np.frombuffer(source.PixelData, "<u2").copy()

    result = _transformed(_transform([CLEAN_GRAPHICS]), source)

    assert isinstance(result, run.Transformed), result
    after = _words(result.data)
    # Only the overlay's bit changed, and it is clear in every word.
    assert set(np.unique(before ^ after)) == {0, 1 << OVERLAY_BIT}
    assert not np.any(after & (1 << OVERLAY_BIT))
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert np.array_equal(pydicom.pixels.pixel_array(written), _frame())
    assert _codes(result.data) == [BASIC_PROFILE_CODE, CLEAN_GRAPHICS_CODE]
    assert not isinstance(result.evidence, HeldEvidence)
    # The group goes with its overlay, so nothing describes the cleared bit
    # as an overlay.
    assert not _overlay_groups(result.data)
    # The source's indicator is still reported for review.
    assert any(isinstance(material, PixelRiskMaterial) for material in result.qc)


def test_a_mixed_sign_image_keeps_its_signs_and_describes_no_overlay():
    source = _embedded(_ct(_signed_frame(), signed=True), every=1)
    before = np.frombuffer(source.PixelData, "<u2").copy()

    result = _transformed(_transform([CLEAN_GRAPHICS]), source)

    assert isinstance(result, run.Transformed), result
    after = _words(result.data)
    negative = (before & 0x0800).astype(bool)
    # Every unused bit gives the value's sign again: all one where it is
    # negative, and all zero where it is not.
    assert np.all(after[negative] >> 12 == 0xF)
    assert np.all(after[~negative] >> 12 == 0)
    assert np.array_equal(after & 0x0FFF, before & 0x0FFF)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert np.array_equal(pydicom.pixels.pixel_array(written), _signed_values())
    # The overlay's bit now draws the negative values, so no overlay group
    # may describe it as graphics.
    assert np.any(negative) and not np.all(negative)
    assert not _overlay_groups(result.data)


def test_every_overlay_group_without_overlay_data_has_its_bit_cleared():
    source = _embedded(_embedded(_ct(_frame())), bit=15, group=0x6002, every=2)

    assert overlay_planes(_source(source), source) == (1 << 13) | (1 << 15)
    result = _transformed(_transform([CLEAN_GRAPHICS]), source)

    assert isinstance(result, run.Transformed), result
    assert not np.any(_words(result.data) >> 12)
    assert not _overlay_groups(result.data)


def test_an_instance_without_an_embedded_overlay_has_no_planes_to_clear():
    source = _with_overlay(_ct(_frame()))

    assert overlay_planes(_source(source), source) == 0


def _bit_inside_bits_stored(dataset):
    return _embedded(dataset, bit=11)


def _bits_allocated_one(dataset):
    _embedded(dataset)
    dataset[0x60000100].value = 1
    return dataset


def _no_bit_position(dataset):
    _embedded(dataset)
    del dataset[0x60000102]
    return dataset


def _bit_position_of_two_values(dataset):
    _embedded(dataset)
    dataset[0x60000102].value = [13, 14]
    return dataset


def _another_unused_bit_set(dataset):
    # Bit 14 holds a plane that no overlay group describes.
    _embedded(dataset)
    words = np.frombuffer(dataset.PixelData, "<u2").copy()
    words[1] |= 1 << 14
    dataset.PixelData = words.tobytes()
    return dataset


def _not_whole_frames(dataset):
    _embedded(dataset)
    dataset.PixelData = dataset.PixelData[:-4]
    return dataset


def _no_pixel_data(dataset):
    _embedded(dataset)
    del dataset.PixelData
    return dataset


@pytest.mark.parametrize(
    "change",
    [
        _bit_inside_bits_stored,
        _bits_allocated_one,
        _no_bit_position,
        _bit_position_of_two_values,
        _another_unused_bit_set,
        _not_whole_frames,
        _no_pixel_data,
    ],
    ids=[
        "inside-bits-stored",
        "bits-allocated-one",
        "no-bit-position",
        "two-bit-positions",
        "another-unused-bit",
        "not-whole-frames",
        "no-pixel-data",
    ],
)
@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_an_overlay_that_cannot_be_cleared_sequesters_the_instance(change):
    source = change(_ct(_frame()))

    assert overlay_planes(_source(source), source) is None
    result = _transformed(_transform([CLEAN_GRAPHICS]), source)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.OVERLAY_IN_PIXEL_DATA,)


def _rle_with_overlay():
    """An RLE Lossless CT image, 12 bits stored, whose overlay group places
    its overlay in bit 13."""
    frame = (_frame() | np.where(np.arange(48).reshape(6, 8) % 3, 0, 1 << 13)).astype(
        "<u2"
    )
    data = compressed.ct_image(
        compressed.RLE_LOSSLESS,
        [compressed.rle_lossless(frame)],
        rows=6,
        columns=8,
        bits=12,
    )
    dataset = _with_overlay(pydicom.dcmread(io.BytesIO(data)), data=False)
    dataset[0x60000100].value = 16
    dataset[0x60000102].value = OVERLAY_BIT
    return dataset


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_an_overlay_in_compressed_pixel_data_sequesters_the_instance():
    dataset = _rle_with_overlay()
    data = synthetic.written(dataset, compressed.RLE_LOSSLESS)
    source = read_source(data)

    assert overlay_planes(source, source.dataset()) is None
    result = _transform([CLEAN_GRAPHICS])(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.OVERLAY_IN_PIXEL_DATA,)


def test_overlays_are_cleared_only_above_high_bit_and_in_native_pixel_data():
    source = _source(_ct(_frame()))
    with pytest.raises(ValueError):
        black_out(source, source.dataset(), None, overlays=1 << 11)

    data = synthetic.written(_rle_with_overlay(), compressed.RLE_LOSSLESS)
    encapsulated = read_source(data)
    with pytest.raises(ValueError):
        black_out(encapsulated, encapsulated.dataset(), None, overlays=1 << OVERLAY_BIT)


def _cleared():
    dataset = _embedded(_ct(_frame()))
    source = _source(dataset)
    planes = overlay_planes(source, source.dataset())
    return source, black_out(source, source.dataset(), None, overlays=planes)


def _written_with(source, value):
    dataset = source.dataset()
    dataset.PixelData = value
    return read_source(synthetic.written(dataset))


def test_a_cleared_overlay_is_written_as_planned():
    source, redaction = _cleared()

    assert redaction.overlays == 1 << OVERLAY_BIT
    assert redaction.changed and not redaction.regions
    assert not redaction_problem(
        source, _written_with(source, redaction.value), redaction
    )


@pytest.mark.parametrize(
    "flipped", [OVERLAY_BIT, 14, 0], ids=["overlay-kept", "another-unused-bit", "value"]
)
def test_written_pixel_data_that_differs_in_any_other_bit_is_found(flipped):
    source, redaction = _cleared()
    words = np.frombuffer(redaction.value, "<u2").copy()
    # The first word's overlay bit was set in the source, so flipping it
    # back keeps the overlay there.
    words[0] ^= 1 << flipped

    assert redaction_problem(source, _written_with(source, words.tobytes()), redaction)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_clean_pixel_data_clears_the_overlay_and_blacks_out_the_text():
    source = _embedded(_ct(_frame()))
    before = np.frombuffer(source.PixelData, "<u2").copy()

    result = _transformed(_transform([CLEAN_PIXEL_DATA], Finder()), source)

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    held = result.evidence.held  # pylint: disable=no-member
    assert held == (HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),)
    after = _words(result.data)
    inside = _inside(_frame().shape).ravel()
    assert set(np.unique(before[~inside] ^ after[~inside])) == {0, 1 << OVERLAY_BIT}
    assert np.all(after[inside] == _frame().min())
    assert _codes(result.data) == [BASIC_PROFILE_CODE]
    assert not _overlay_groups(result.data)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_an_overlay_that_clean_pixel_data_cannot_clear_leaves_it_uncleanable():
    source = _another_unused_bit_set(_ct(_frame()))

    result = _transformed(_transform([CLEAN_PIXEL_DATA], Finder()), source)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.UNCLEANABLE_PIXEL_DATA,)


def test_both_options_clear_the_overlay_in_the_write_that_blacks_out_the_text():
    source = _embedded(_ct(_frame()))

    result = _transformed(
        _transform([CLEAN_PIXEL_DATA, CLEAN_GRAPHICS], Finder(boxes=(BOX,))), source
    )

    assert isinstance(result, run.Transformed), result
    after = _words(result.data)
    assert not np.any(after >> 12)
    inside = _inside(_frame().shape).ravel()
    assert np.all(after[inside] == _frame().min())
    # Clean Pixel Data waits for review; Clean Graphics is claimed now.
    assert _codes(result.data) == [BASIC_PROFILE_CODE, CLEAN_GRAPHICS_CODE]
    assert CLEAN_PIXEL_DATA_CODE not in _codes(result.data)


def test_without_either_option_the_overlay_is_written_as_received():
    source = _embedded(_ct(_frame()))
    before = np.frombuffer(source.PixelData, "<u2").copy()

    result = _transformed(_transform([]), source)

    assert isinstance(result, run.Transformed), result
    assert np.array_equal(_words(result.data), before)
    assert _overlay_groups(result.data) == [0x6000]
