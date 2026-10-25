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

"""Segmentations cleaned in a defaced CT series' face block. Every UID and
value here is invented."""

# Segmentation stays out of scope, so the transform's steps for it are
# tested one by one.
# pylint: disable = protected-access

from __future__ import annotations

import functools
import hashlib
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_blocks, instance_transform, scope
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.dose_defacing import DoseBlock
from pymedphys._dicom.deidentify.face_blocks import KeptSlice
from pymedphys._dicom.deidentify.face_review import (
    FaceReview,
    contour_data_sha256,
    pixel_data_sha256,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES,
    compose_custom_policy,
)
from pymedphys._dicom.deidentify.qc_pack import new_reference
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    black_out,
    redaction_problem,
)
from pymedphys._dicom.deidentify.reasons import (
    HeldVisualFeatures,
    TransformReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.scope import classify
from pymedphys._dicom.deidentify.segmentation_defacing import (
    SEGMENTATION,
    SegmentationDefacer,
)
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.4"
LABEL_MAP_SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.7"
# The block holds the points with y below 0 and z above 0: anterior is -y.
_BLOCK = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))
_SIZE = 24
_BITS = {"BINARY": 1, "FRACTIONAL": 8, "LABELMAP": 16}


def _kept_slice(z: float) -> KeptSlice:
    """An axial slice over x and y from -20 to 20 mm at 1 mm, whose kept
    pixels are those in the block with x from -5 to 7 mm and y from -10 to
    -1 mm, above z = 15 mm, so that a mirror image of them is not."""
    x = np.arange(-20, 21)[None, :]
    y = np.arange(-20, 21)[:, None]
    kept = (x >= -5) & (x <= 7) & (y >= -10) & (y <= -1) & (z > 15)
    return KeptSlice((-20.0, -20.0, z), files.AXIAL, (1.0, 1.0), kept)


_REGION = DoseBlock(_BLOCK, tuple(_kept_slice(z) for z in (10.0, 20.0, 30.0)))


def _points():
    """The x and y of each pixel of a frame placed at x and y of -20 mm,
    at 2 mm."""
    x = -20 + 2 * np.arange(_SIZE)[None, :]
    y = -20 + 2 * np.arange(_SIZE)[:, None]
    return np.broadcast_arrays(x, y)


def _cleaned_region():
    """The pixels of a frame at z = 20 mm that defacing writes as air: in
    the block and not kept."""
    x, y = _points()
    kept = (x >= -5) & (x <= 7) & (y >= -10) & (y <= -1)
    return (y < 0) & ~kept


def _item(**attributes):
    item = pydicom.Dataset()
    for keyword, value in attributes.items():
        setattr(item, keyword, value)
    return item


def _groups(position=None, orientation=None, spacing=None):
    """A functional groups item with the plane and pixel measures given."""
    groups = pydicom.Dataset()
    if position is not None:
        groups.PlanePositionSequence = [
            _item(ImagePositionPatient=[str(v) for v in position])
        ]
    if orientation is not None:
        groups.PlaneOrientationSequence = [
            _item(ImageOrientationPatient=[str(v) for v in orientation])
        ]
    if spacing is not None:
        groups.PixelMeasuresSequence = [
            _item(PixelSpacing=[str(v) for v in spacing], SliceThickness="2")
        ]
    return groups


def _segmentation(stored=None, *, kind="BINARY", heights=(20.0, 20.0), **changes):
    """A segmentation of a frame at each of ``heights``, in millimetres,
    over x and y from -20 mm at 2 mm, each frame its own segment, of 1 in
    every pixel by default, placed by a shared orientation and spacing
    and each frame's own position."""
    frames = len(heights)
    if stored is None:
        stored = np.ones((frames, _SIZE, _SIZE), dtype=np.uint16)
    stored = np.asarray(stored)
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = (
        LABEL_MAP_SEGMENTATION_STORAGE if kind == "LABELMAP" else SEGMENTATION_STORAGE
    )
    dataset.FrameOfReferenceUID = files.FRAME
    dataset.NumberOfFrames = frames
    dataset.Rows = dataset.Columns = _SIZE
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = dataset.BitsStored = _BITS[kind]
    dataset.HighBit = _BITS[kind] - 1
    dataset.PixelRepresentation = 0
    dataset.SegmentationType = kind
    if kind == "FRACTIONAL":
        dataset.SegmentationFractionalType = "PROBABILITY"
        dataset.MaximumFractionalValue = 255
    dataset.SharedFunctionalGroupsSequence = [
        _groups(orientation=files.AXIAL, spacing=(2, 2))
    ]
    dataset.PerFrameFunctionalGroupsSequence = [
        _groups(position=(-20, -20, z)) for z in heights
    ]
    for index, groups in enumerate(dataset.PerFrameFunctionalGroupsSequence):
        groups.SegmentIdentificationSequence = [
            _item(ReferencedSegmentNumber=index + 1)
        ]
    if kind == "BINARY":
        data = np.asarray(
            np.packbits(stored.astype(np.uint8).ravel(), bitorder="little")
        )
    elif kind == "FRACTIONAL":
        data = stored.astype(np.uint8)
    else:
        data = stored.astype("<u2")
    dataset.PixelData = data.tobytes()
    meta = pydicom.dataset.FileMetaDataset()
    meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID = files.ROOT + ".9.1"
    meta.TransferSyntaxUID = files.EXPLICIT_VR_LITTLE_ENDIAN
    dataset.file_meta = meta
    for keyword, value in changes.items():
        setattr(dataset, keyword, value)
    return dataset


def _masks(dataset):
    defacer = SegmentationDefacer(_REGION, dataset)
    frames = pydicom.pixels.pixel_array(dataset).reshape(-1, _SIZE, _SIZE)
    return [defacer.mask(index, frame) for index, frame in enumerate(frames)]


@pytest.mark.parametrize("kind", ["BINARY", "FRACTIONAL"])
def test_a_segment_is_cleared_in_the_block_less_the_kept_brain(kind):
    masks = _masks(_segmentation(kind=kind))

    for index, mask in enumerate(masks):
        assert mask.frame == index and mask.value == 0
        assert np.array_equal(mask.mask, _cleaned_region())


def test_only_pixels_in_a_segment_are_cleared():
    stored = np.random.default_rng(0).integers(0, 2, size=(2, _SIZE, _SIZE))

    masks = _masks(_segmentation(stored))

    for mask, frame in zip(masks, stored, strict=True):
        assert np.array_equal(mask.mask, _cleaned_region() & (frame == 1))


def test_a_fractional_segment_is_cleared_whatever_its_value():
    stored = np.zeros((2, _SIZE, _SIZE), dtype=np.uint8)
    stored[0, :4] = 1
    stored[1, :4] = 255

    masks = _masks(_segmentation(stored, kind="FRACTIONAL"))

    for mask in masks:
        expected = np.zeros((_SIZE, _SIZE), dtype=bool)
        expected[:4] = True
        assert np.array_equal(mask.mask, expected & _cleaned_region())


def test_a_label_map_is_cleared_to_its_pixel_padding_value():
    stored = np.full((1, _SIZE, _SIZE), 3, dtype=np.uint16)
    stored[0, 0] = 7
    stored[0, 1] = 0
    dataset = _segmentation(stored, kind="LABELMAP", heights=(20.0,))
    dataset.PixelPaddingValue = 7
    dataset["PixelPaddingValue"].VR = "US"

    (mask,) = _masks(dataset)

    # 0 is a Segment Number like any other, so it is cleared too.
    assert mask.value == 7
    assert not mask.mask[0].any() and mask.mask[1].any()
    assert np.array_equal(mask.mask, _cleaned_region() & (stored[0] != 7))


def test_a_label_map_of_8_bits_is_cleared_to_its_pixel_padding_value():
    dataset = _segmentation(kind="LABELMAP", heights=(20.0,))
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelData = np.full(_SIZE * _SIZE, 2, dtype=np.uint8).tobytes()
    dataset.PixelPaddingValue = 255
    dataset["PixelPaddingValue"].VR = "US"

    (mask,) = _masks(dataset)

    assert mask.value == 255
    assert np.array_equal(mask.mask, _cleaned_region())


def test_a_segmentation_that_the_block_does_not_reach_has_no_mask():
    behind = _segmentation(heights=(20.0,))
    behind.PerFrameFunctionalGroupsSequence[0].PlanePositionSequence[
        0
    ].ImagePositionPatient = ["-20", "1", "20"]
    below = _segmentation(heights=(-5.0, -20.0))
    only_kept = np.zeros((1, _SIZE, _SIZE), dtype=np.uint8)
    x, y = _points()
    only_kept[0] = (x >= -5) & (x <= 7) & (y >= -10) & (y <= -1)
    in_kept_brain = _segmentation(only_kept, heights=(20.0,))
    behind_only = _segmentation(
        np.broadcast_to(y >= 0, (1, _SIZE, _SIZE)), heights=(20.0,)
    )

    for dataset in (behind, below, in_kept_brain, behind_only):
        assert _masks(dataset) == [None] * len(dataset.PerFrameFunctionalGroupsSequence)


def test_each_frame_is_placed_by_its_own_functional_groups():
    dataset = _segmentation(heights=(20.0, -5.0))
    # The first frame's own spacing, a quarter of the shared, puts its
    # pixels within y of -20 to -8.5 mm, all in the block.
    dataset.PerFrameFunctionalGroupsSequence[0].PixelMeasuresSequence = [
        _item(PixelSpacing=["0.5", "0.5"])
    ]

    first, second = _masks(dataset)

    assert first.mask.all()
    assert second is None


def test_a_segmentation_placed_in_its_shared_groups_alone_is_cleaned():
    dataset = _segmentation(heights=(20.0,))
    del dataset.PerFrameFunctionalGroupsSequence[0].PlanePositionSequence
    dataset.SharedFunctionalGroupsSequence[0].PlanePositionSequence = [
        _item(ImagePositionPatient=["-20", "-20", "20"])
    ]

    (mask,) = _masks(dataset)

    assert np.array_equal(mask.mask, _cleaned_region())


def _source(dataset):
    return read_source(files.written(dataset))


@pytest.mark.parametrize("kind", ["BINARY", "FRACTIONAL", "LABELMAP"])
def test_a_segmentation_is_written_cleared_and_checked(kind):
    stored = np.random.default_rng(1).integers(0, 2, size=(2, _SIZE, _SIZE))
    dataset = _segmentation(stored, kind=kind)
    if kind == "LABELMAP":
        dataset.PixelPaddingValue = 0
        dataset["PixelPaddingValue"].VR = "US"
    source = _source(dataset)

    redaction = black_out(
        source,
        source.dataset(),
        None,
        SegmentationDefacer(_REGION, source.dataset()),
    )

    written = source.dataset()
    written.PixelData = redaction.value
    output = read_source(files.written(written))
    pixels = pydicom.pixels.pixel_array(output.dataset())
    expected = np.where(_cleaned_region(), 0, stored)
    assert np.array_equal(pixels, expected)
    assert [mask.frame for mask in redaction.masks] == [0, 1]
    assert not redaction_problem(source, output, redaction)


def _set_position(dataset, value):
    dataset.PerFrameFunctionalGroupsSequence[0].PlanePositionSequence[
        0
    ].ImagePositionPatient = value


def _shared(dataset, keyword, value):
    group = dataset.SharedFunctionalGroupsSequence[0]
    if keyword == "ImageOrientationPatient":
        group.PlaneOrientationSequence[0].ImageOrientationPatient = value
    else:
        group.PixelMeasuresSequence[0].PixelSpacing = value


def _refusals():
    """Each change to a segmentation that refuses it, by name."""

    def labelmap(**attributes):
        def change(dataset):
            dataset.SOPClassUID = LABEL_MAP_SEGMENTATION_STORAGE
            dataset.SegmentationType = "LABELMAP"
            for keyword, value in attributes.items():
                setattr(dataset, keyword, value)

        return change

    def setting(**attributes):
        def change(dataset):
            for keyword, value in attributes.items():
                setattr(dataset, keyword, value)

        return change

    def without_position(dataset):
        del dataset.PerFrameFunctionalGroupsSequence[0].PlanePositionSequence

    def without_spacing(dataset):
        del dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence

    def two_positions(dataset):
        sequence = dataset.PerFrameFunctionalGroupsSequence[0].PlanePositionSequence
        sequence.append(sequence[0])

    def too_few_frames(dataset):
        del dataset.PerFrameFunctionalGroupsSequence[1]

    def two_shared(dataset):
        dataset.SharedFunctionalGroupsSequence.append(
            dataset.SharedFunctionalGroupsSequence[0]
        )

    def compressed(dataset):
        dataset.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.5"

    return {
        "compressed": compressed,
        "unknown-type": setting(SegmentationType="SURFACE"),
        "binary-of-8-bits": setting(
            BitsAllocated=8, BitsStored=8, HighBit=7, PixelData=bytes(2 * 576)
        ),
        "monochrome1": setting(PhotometricInterpretation="MONOCHROME1"),
        "signed": setting(PixelRepresentation=1),
        "palette-color": labelmap(
            BitsAllocated=8,
            BitsStored=8,
            HighBit=7,
            PixelData=bytes(2 * 576),
            PixelPaddingValue=0,
            PhotometricInterpretation="PALETTE COLOR",
        ),
        "label-map-of-1-bit": labelmap(PixelPaddingValue=0),
        "label-map-without-padding": labelmap(
            BitsAllocated=8, BitsStored=8, HighBit=7, PixelData=bytes(2 * 576)
        ),
        "label-map-with-a-range-limit": labelmap(
            BitsAllocated=8,
            BitsStored=8,
            HighBit=7,
            PixelData=bytes(2 * 576),
            PixelPaddingValue=0,
            PixelPaddingRangeLimit=2,
        ),
        "label-map-with-padding-not-stored": labelmap(
            BitsAllocated=8,
            BitsStored=8,
            HighBit=7,
            PixelData=bytes(2 * 576),
            PixelPaddingValue=300,
        ),
        "tiled-full": setting(DimensionOrganizationType="TILED_FULL"),
        "frames-starting-within-a-byte": setting(
            Rows=5, Columns=7, PixelData=bytes(10)
        ),
        "without-a-position": without_position,
        "without-a-spacing": without_spacing,
        "two-positions": two_positions,
        "too-few-per-frame-items": too_few_frames,
        "two-shared-items": two_shared,
        "zero-spacing": lambda d: _shared(d, "PixelSpacing", ["0", "2"]),
        "non-unit-cosines": lambda d: _shared(
            d, "ImageOrientationPatient", ["2", "0", "0", "0", "1", "0"]
        ),
        "five-cosines": lambda d: _shared(
            d, "ImageOrientationPatient", ["1", "0", "0", "0", "1"]
        ),
        "huge-position": lambda d: _set_position(d, ["1e300", "0", "0"]),
        "short-position": lambda d: _set_position(d, ["0", "0"]),
    }


@pytest.mark.parametrize("name", sorted(_refusals()))
def test_a_segmentation_that_cannot_be_placed_or_cleaned_is_refused(name):
    dataset = _segmentation()
    _refusals()[name](dataset)

    with pytest.raises(PixelDataRefused) as refused:
        SegmentationDefacer(_REGION, dataset)
    assert refused.value.reason is TransformReason.UNCLEANABLE_PIXEL_DATA


def test_a_segmentation_defacer_shows_nothing_and_holds_nothing():
    defacer = SegmentationDefacer(_REGION, _segmentation())

    assert repr(defacer) == "SegmentationDefacer()"
    assert defacer.held is None


# In the transform.


def test_the_module_names_the_segmentation_iod_as_the_tables_do():
    for sop_class in (SEGMENTATION_STORAGE, LABEL_MAP_SEGMENTATION_STORAGE):
        assert classify(sop_class, files.EXPLICIT_VR_LITTLE_ENDIAN).iod == SEGMENTATION
    record = InstanceRecord.from_file(files.written(_segmentation()))
    assert record.iod == SEGMENTATION
    assert face_blocks.frames_of(record) == {files.FRAME}
    # Until the run cleans it, a segmentation in a defaced frame is held.
    assert SEGMENTATION in face_blocks.UNDEFACED_IODS


# The analytic head, coarse, whose block a segmentation in its frame is
# cleaned in.
_SCAN = head.axial(
    spacing=2.5, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
)


@functools.cache
def _head_files():
    return tuple(files.ct_files(_SCAN, head.Head(noise=0.0)))


def _head_segmentation(frame=files.FRAME, rows=slice(None)):
    """A BINARY segmentation over the head's whole extent at the globes'
    height, at 8 mm, of 1 in each pixel of ``rows``, from anterior to
    posterior, as a mask of the body could be, and 0 elsewhere."""
    dataset = _segmentation(heights=(head.GLOBE_Z,))
    dataset.PatientName = "Head^Analytic"
    dataset.PatientID = "H1"
    dataset.StudyInstanceUID = files.STUDY
    dataset.SeriesInstanceUID = files.ROOT + ".9"
    dataset.Modality = "SEG"
    dataset.FrameOfReferenceUID = frame
    dataset.Rows = dataset.Columns = 32
    dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing = [
        "8",
        "8",
    ]
    _set_position(dataset, ["-124", "-124", str(head.GLOBE_Z)])
    stored = np.zeros((32, 32), dtype=np.uint8)
    stored[rows] = 1
    dataset.PixelData = np.asarray(
        np.packbits(stored.ravel(), bitorder="little")
    ).tobytes()
    return files.written(dataset)


def _prepared(*data):
    transform = instance_transform.InstanceTransform(
        compose_custom_policy([CLEAN_RECOGNIZABLE_VISUAL_FEATURES]),
        DeidKey(bytes(range(32))),
        face_review=FaceReview(new_reference(), frozenset(), frozenset()),
        unvalidated_policy=True,
    )
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    transform.prepare(records, lambda position: data[position])
    return transform, records


def _iod(transform, name=SEGMENTATION):
    return transform._iods.iods[name]


def test_a_segmentation_in_a_defaced_frame_is_cleaned_in_its_block_and_held():
    slices = _head_files()
    data = _head_segmentation()
    transform, records = _prepared(*slices, data)
    iod = _iod(transform)
    region = transform._region(iod, records[len(slices)])
    source = read_source(data)

    redaction, undefaced, _ = transform._black_out(
        data,
        source,
        source.dataset(),
        None,
        None,
        instance_transform._region_defacing(iod, region),
    )

    assert region is not None and undefaced is None
    (mask,) = redaction.masks
    # The eyes, ahead of the block's plane, are cleared, and the back of
    # the head is kept.
    columns = np.rint((np.array([head.GLOBE_X, 0.0]) + 124) / 8).astype(int)
    rows = np.rint((np.array([head.GLOBE_Y - 5.0, 100.0]) + 124) / 8).astype(int)
    assert mask.mask[rows[0], columns[0]] and not mask.mask[rows[1], columns[1]]
    assert instance_transform._unshown_segments(iod, redaction)


def test_no_block_for_a_segmentation_in_another_frame_so_it_stays_held():
    slices = _head_files()
    transform, records = _prepared(*slices, _head_segmentation(files.ROOT + ".8"))
    iod = _iod(transform)

    assert transform._region(iod, records[len(slices)]) is None
    assert instance_transform._region_defacing(iod, None) is None


class _NoMask:  # pylint: disable = too-few-public-methods
    def mask(self, frame, stored):  # pylint: disable = unused-argument
        return None


def test_only_a_segmentation_given_a_mask_is_held_for_its_segments():
    transform, _ = _prepared()
    unshown = instance_transform._unshown_segments
    source = _source(_segmentation())
    unmasked = black_out(source, source.dataset(), None, _NoMask())
    masked = black_out(
        source,
        source.dataset(),
        None,
        SegmentationDefacer(_REGION, source.dataset()),
    )

    assert unshown(_iod(transform), masked)
    assert not unshown(_iod(transform), unmasked)
    assert not unshown(_iod(transform), None)
    assert not unshown(_iod(transform, "Positron Emission Tomography Image"), masked)


def _reviewed_absent(data, written):
    """A face review that marks a segmentation absent as ``written``."""
    digest = hashlib.sha256(data).digest()
    dataset = pydicom.dcmread(io.BytesIO(written))
    return FaceReview(
        new_reference(),
        frozenset({digest}),
        frozenset(),
        frozenset({(digest, pixel_data_sha256(dataset))}),
        frozenset({(digest, contour_data_sha256(dataset))}),
    )


@pytest.mark.parametrize("reaches", [True, False], ids=["reaches", "behind"])
def test_a_segmentation_that_reaches_the_face_is_held_whatever_its_verdict(
    monkeypatch, reaches
):
    # Segmentation is out of scope until it is supported, so the run would
    # sequester it before cleaning it.
    monkeypatch.setattr(scope, "SUPPORTED_IODS", scope.SUPPORTED_IODS | {SEGMENTATION})
    slices = _head_files()
    # Rows from 16, at y of 4 mm and more, lie well behind the globes, and
    # so behind the block's plane.
    data = _head_segmentation(rows=slice(None) if reaches else slice(16, None))
    transform, records = _prepared(*slices, data)
    record = records[len(slices)]
    first = transform(data, record)
    transform._face_review = _reviewed_absent(data, first.data)

    second = transform(data, record)

    written = pydicom.pixels.pixel_array(pydicom.dcmread(io.BytesIO(second.data)))
    held = getattr(second.evidence, "held", ())
    if reaches:
        # Its eyes' pixels are cleared, and it is held, since the pack does
        # not show segments.
        eyes = round((head.GLOBE_Y - 5.0 + 124) / 8)
        assert written[eyes].sum() < 32 and written[16:].all()
        assert held == (HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT),)
    else:
        assert (
            np.array_equal(written[16:], np.ones((16, 32))) and not written[:16].any()
        )
        assert not held
