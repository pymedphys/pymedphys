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

# pylint: disable = protected-access
"""Tests that a face verdict releases a Segmentation only where its segments
sheet, which alone shows the surfaces that its segments trace, showed every
frame of it, counted in the run that the verdict releases.

Every name, UID, and image here is synthetic.
"""

from __future__ import annotations

import hashlib
import io
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_review
from pymedphys._dicom.deidentify.face_review import FaceReview, pixel_data_sha256
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
)
from pymedphys._dicom.deidentify.qc_pack import (
    NO_CONTOURS_SHA256,
    NO_PIXELS_SHA256,
    NotPreviewedEntry,
    NotPreviewedReason,
    QcPackError,
)
from pymedphys._dicom.deidentify.reasons import (
    HeldVisualFeatures,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.run_results import Transformed
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_qc_face_verdicts import REFERENCE
from .test_deidentify_qc_pixel_digests import (
    _SCAN,
    _frames,
    _Given,
    _relabelled,
    _shown,
    _Unreadable,
    _verdict_run,
)
from .test_deidentify_visual_features_option import KEY, _policy


@pytest.mark.parametrize("modality", ["SEG", "seg", "Seg "])
def test_an_image_labelled_seg_is_not_shown(modality):
    # Its Modality makes it a Segmentation, which only a segments sheet
    # shows, and only a Segmentation by its functional groups has one.
    found, framed = _shown({0: _relabelled(_frames(12), modality)})
    assert framed[0] == set(range(12))
    assert found.pixels_shown == frozenset()
    assert found.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.SEGMENTS_NOT_SHOWN),
    )


def _segmentation(kind="BINARY", scan=_SCAN):
    """A Segmentation of the head's body on ``scan``, a frame a slice, which
    traces the face."""
    body = np.stack(
        [
            head.hounsfield(scan.points(index)) > head.AIR
            for index in range(len(scan.positions))
        ]
    )
    return files.segmentation(scan, [body], kind=kind, keep_empty=True)


def test_a_segmentation_is_known_by_its_class_or_a_modality_that_may_be_seg():
    def instance(modality=None, sop_class=files.CT_IMAGE_STORAGE, kind=pydicom.Dataset):
        dataset = kind()
        dataset.SOPClassUID = sop_class
        if modality is not None:
            dataset.Modality = modality
        return dataset

    for sop_class in (
        files.SEGMENTATION_STORAGE,
        files.LABEL_MAP_SEGMENTATION_STORAGE,
        files.SEGMENTATION_STORAGE + "\0",
    ):
        assert face_review.is_segmentation(instance(sop_class=sop_class)), sop_class
        assert face_review.is_segmentation(instance("CT", sop_class)), sop_class
    # Any spelling that may be SEG: another case, several values, a
    # character outside printable ASCII, padding aside, or none readable.
    for modality in (
        "SEG",
        "seg",
        "Seg ",
        ["SEG", "CT"],
        ["CT", "MR"],
        "SÉG",
        "ＳＥＧ",
        "\0SEG",
        "S\x01EG",
    ):
        assert face_review.is_segmentation(instance(modality)), modality
    assert face_review.is_segmentation(instance("CT", kind=_Unreadable))
    for given in (b"SEG", b"CT", 7, "SEG\\CT", "CT\\MR"):
        dataset = instance(kind=_Given)
        dataset.given = given
        assert face_review.is_segmentation(dataset), given
    # A missing or empty Modality says nothing, and another modality,
    # padded or not, is not SEG; nor are the other segmentation IODs'
    # classes, which name IODs of their own.
    for modality in (None, "", "CT", "CT ", "RTDOSE", "SEGM", "SR"):
        assert not face_review.is_segmentation(instance(modality)), modality
    for sop_class in ("1.2.840.10008.5.1.4.1.1.66.5", "1.2.840.10008.5.1.4.1.1.66.8"):
        assert not face_review.is_segmentation(instance(sop_class=sop_class))


def test_the_reader_counts_a_segments_sheet_s_frames_for_its_segmentation_alone():
    document = {
        "instances": [
            {
                "position": position,
                "source_sha256": f"{position:02x}" * 32,
                "pixel_sha256": "1e" * 32,
                "contour_sha256": None,
                "reasons": [],
            }
            for position in (0, 1)
        ],
        "series": [{"positions": [0]}, {"positions": [1]}],
        "previews": [
            {
                "kind": "series-cine",
                "frames": [{"position": 0, "frame": f} for f in range(3)]
                + [{"position": 1, "frame": 0}],
            },
            {
                "kind": "segmentation-segments",
                "frames": [{"position": 0, "frame": f} for f in range(2)]
                + [{"position": 1, "frame": 0}],
            },
        ],
        "not_previewed": [],
    }
    files_of = face_review._series_files(json.dumps(document).encode("ascii"))
    ((segmentation,), (guide,)) = files_of[0], files_of[1]
    # The sheet showed two of the Segmentation's frames, and the volume
    # that it was drawn with only as a surface, so not as its own.
    assert segmentation[4:] == (3, None, 2)
    assert guide[4:] == (1, None, None)
    _attested = FaceReview(
        REFERENCE,
        frozenset({segmentation[0]}),
        frozenset(),
        frozenset({segmentation[:2]}),
        absent_segment_frames=frozenset({(*segmentation[:2], 2)}),
    )
    assert _attested.absent_segment_frames == {(*segmentation[:2], 2)}


def test_a_review_holds_a_segmentation_unless_its_segments_sheet_showed_every_frame():
    source, pixels = hashlib.sha256(b"source").digest(), hashlib.sha256(b"x").digest()
    contours = bytes.fromhex(NO_CONTOURS_SHA256)

    def review(segment_frames, dose_frames=None):
        return FaceReview(
            REFERENCE,
            frozenset({source}),
            frozenset(),
            frozenset({(source, pixels), (source, bytes.fromhex(NO_PIXELS_SHA256))}),
            frozenset({(source, contours)}),
            frozenset({(source, pixels, 16)}),
            dose_frames,
            segment_frames,
        )

    held = VisualFeaturesReason.OTHER_PIXEL_DATA
    # Other previews' frames do not count for a Segmentation, so a review
    # without its segments sheet's holds every one with pixel data.
    for segment_frames in (None, frozenset()):
        assert review(segment_frames).hold_reason(source, pixels, contours, 16) is None
        assert (
            review(segment_frames).hold_reason(
                source, pixels, contours, 16, segmentation=True
            )
            is held
        )
    shown = review(frozenset({(source, pixels, 12)}))
    assert shown.hold_reason(source, pixels, contours, 12, segmentation=True) is None
    for frames in (0, 13, None):
        assert (
            shown.hold_reason(source, pixels, contours, frames, segmentation=True)
            is held
        )
    # One that is an RT Dose by one attribute and a Segmentation by another
    # is released only where both its dose levels and its segments sheet
    # showed every frame.
    both = {"dose": True, "segmentation": True}
    assert shown.hold_reason(source, pixels, contours, 12, **both) is held
    dosed = review(None, frozenset({(source, pixels, 12)}))
    assert dosed.hold_reason(source, pixels, contours, 12, **both) is held
    seen = review(frozenset({(source, pixels, 12)}), frozenset({(source, pixels, 12)}))
    assert seen.hold_reason(source, pixels, contours, 12, **both) is None
    # One without pixel data shows no face.
    none = bytes.fromhex(NO_PIXELS_SHA256)
    assert (
        review(None).hold_reason(source, none, contours, None, segmentation=True)
        is None
    )
    with pytest.raises(QcPackError, match="frames shown"):
        FaceReview(
            REFERENCE,
            frozenset({source}),
            frozenset(),
            absent_segment_frames=frozenset({(source, pixels, 16)}),
        )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize(
    "data",
    [
        _segmentation(),
        _segmentation("LABELMAP"),
        _relabelled(_frames(12), "SEG"),
        _relabelled(_frames(12), ["SEG", "CT"]),
    ],
    ids=["binary", "label-map", "ct-seg", "ct-two-values"],
)
def test_a_run_releases_a_segmentation_only_where_its_segments_sheet_showed_every_frame(
    data,
):
    record = InstanceRecord.from_file(data)
    source = hashlib.sha256(data).digest()
    transform = InstanceTransform(
        _policy(),
        KEY,
        face_review=FaceReview(REFERENCE, frozenset({source}), frozenset()),
        unvalidated_policy=True,
    )
    unseen = transform(data, record)
    assert isinstance(unseen, Transformed)
    written = read_source(unseen.data).dataset()
    pixels = pixel_data_sha256(written)
    frames = int(written.NumberOfFrames)

    def transformed(segment_frames):
        return InstanceTransform(
            _policy(),
            KEY,
            face_review=FaceReview(
                REFERENCE,
                frozenset({source}),
                frozenset(),
                frozenset({(source, pixels)}),
                frozenset({(source, face_review.contour_data_sha256(written))}),
                frozenset({(source, pixels, frames)}),
                # Every frame in dose levels, since a Modality of two values
                # may be RTDOSE too.
                frozenset({(source, pixels, frames)}),
                segment_frames,
            ),
            unvalidated_policy=True,
        )(data, record)

    # A review that binds the verdict to every frame through other previews
    # does not release a Segmentation, by its SOP Class or Modality, nor one
    # whose segments sheet showed too few frames.
    for segment_frames in (None, frozenset({(source, pixels, frames - 1)})):
        held = transformed(segment_frames)
        assert isinstance(held, Transformed)
        assert isinstance(held.evidence, HeldEvidence)
        assert getattr(held.evidence, "held") == (
            HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA),
        )
    released = transformed(frozenset({(source, pixels, frames)}))
    assert isinstance(released, Transformed)
    assert not isinstance(released.evidence, HeldEvidence)


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize("kind", ["BINARY", "LABELMAP"])
def test_a_verdict_on_a_segments_sheet_releases_its_segmentation(kind):
    data = _segmentation(kind)
    entries, outcomes = _verdict_run(data)
    ((entry,), (outcome,)) = entries, outcomes
    assert entry["pixel_sha256"] is not None
    assert outcome.status.value == "released"


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_verdict_on_a_segmentation_that_no_sheet_shows_holds_it():
    # A FRACTIONAL Segmentation of no more than 16 frames, each of which its
    # cine strip shows, but no segments sheet, so the verdict on its series
    # holds it.
    scan = head.axial(
        spacing=5.0, thickness=10.0, extent=((-100, 100), (-130, 110), (-30, 110))
    )
    data = _segmentation("FRACTIONAL", scan)
    assert int(pydicom.dcmread(io.BytesIO(data)).NumberOfFrames) <= 16
    entries, outcomes = _verdict_run(data)
    ((entry,), (outcome,)) = entries, outcomes
    assert entry["pixel_sha256"] is None
    assert outcome.status.value == "held-for-review"
    assert outcome.reasons == (
        HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA),
    )
