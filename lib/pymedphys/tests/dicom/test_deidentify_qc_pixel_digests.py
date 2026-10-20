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
"""Tests that the QC pack binds a face verdict only to pixel data that its
previews show.

Every name, UID, and image here is synthetic.
"""

import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_review, qc_previews, run, run_qc
from pymedphys._dicom.deidentify.face_review import (
    FaceReview,
    pixel_data_sha256,
    read_face_review,
)
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.qc_pack import (
    NO_CONTOURS_SHA256,
    NO_PIXELS_SHA256,
    InstanceEntry,
    NotPreviewedEntry,
    NotPreviewedReason,
    Preview,
    PreviewKind,
    QcPack,
    QcPackError,
    pictured_frames,
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
from .test_deidentify_qc_face_verdicts import REFERENCE, _released
from .test_deidentify_visual_features_option import KEY, _attest, _policy

_SCAN = head.axial(
    spacing=5.0, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
)


def _slices():
    return [pydicom.dcmread(io.BytesIO(data)) for data in files.ct_files(_SCAN)]


def _frames(count):
    """One instance of ``count`` copies of a slice's frame, as a cine or a
    multi-frame secondary capture holds."""
    dataset = _slices()[0]
    frame = dataset.pixel_array
    dataset.NumberOfFrames = count
    dataset.PixelData = np.repeat(frame[np.newaxis], count, axis=0).tobytes()
    return files.written(dataset)


def _shown(written, high_risk=()):
    found = qc_previews.previews_of(written, set(high_risk))
    framed = {}
    for preview in found.previews:
        for position, frame in preview.frames:
            framed.setdefault(position, set()).add(frame)
    return found, framed


# Which pixel data the previews show.


@pytest.mark.parametrize("high_risk", [(), (0,)])
def test_an_instance_with_more_frames_than_its_previews_show_is_not_shown(high_risk):
    found, framed = _shown({0: _frames(40)}, high_risk)
    # Its cine strip, and its full-resolution preview where it is high-risk,
    # show 16 of its frames, and it is not listed as not previewed.
    assert len(framed[0]) == qc_previews.CINE_FRAMES
    assert not found.not_previewed
    assert found.pixels_shown == frozenset()


def test_an_instance_whose_every_frame_is_shown_is_shown():
    found, framed = _shown({0: _frames(12)})
    assert framed[0] == set(range(12))
    assert found.pixels_shown == {0}


def test_a_volume_is_shown_by_its_projection_and_surface_render():
    slices = files.ct_files(_SCAN)
    assert len(slices) > qc_previews.CINE_FRAMES
    found, _ = _shown(dict(enumerate(slices)))
    kinds = {preview.kind for preview in found.previews}
    assert {PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE} <= kinds
    assert found.pixels_shown == set(range(len(slices)))


def test_a_series_that_is_not_a_volume_is_shown_only_in_the_frames_of_its_cine():
    # Every slice at one position, so the series forms no volume.
    slices = _slices()
    for dataset in slices:
        dataset.ImagePositionPatient = slices[0].ImagePositionPatient
    written = dict(enumerate(files.written(dataset) for dataset in slices))
    found, framed = _shown(written)
    assert PreviewKind.SERIES_MIP not in {preview.kind for preview in found.previews}
    assert len(found.pixels_shown) == qc_previews.CINE_FRAMES
    assert found.pixels_shown == set(framed)


def test_pixel_data_that_no_preview_shows_are_not_shown():
    dataset = _slices()[0]
    dataset.FloatPixelData = dataset.pixel_array.astype(np.float32).tobytes()
    del dataset.PixelData
    written = files.written(dataset)
    found, _ = _shown({0: written}, (0,))
    assert found.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.UNSUPPORTED),
    )
    assert found.pixels_shown == frozenset()


def _longer(count):
    """One instance of ``count`` frames whose Pixel Data hold one frame more."""
    dataset = pydicom.dcmread(io.BytesIO(_frames(count)))
    frame = len(dataset.PixelData) // count
    dataset.PixelData += dataset.PixelData[:frame]
    return files.written(dataset)


@pytest.mark.parametrize("count", [1, 3])
def test_pixel_data_longer_than_their_frames_are_not_shown(count):
    # The bytes beyond the declared frames are in no frame that a preview
    # decodes.
    found, framed = _shown({0: _longer(count)})
    assert framed[0] == set(range(count))
    assert not found.not_previewed
    assert found.pixels_shown == frozenset()


def _dose(frames):
    stored = np.zeros((frames, 20, 20), np.uint32)
    stored[:, 5:15, 5:15] = 1000
    return files.dose(
        stored,
        position=(-50.0, -50.0, 0.0),
        spacing=(5.0, 5.0),
        offsets=[3.0 * frame for frame in range(frames)],
    )


def test_a_dose_grid_is_shown_only_in_the_frames_of_its_cine():
    # Its isodose render lists every frame, but cannot show a face.
    found, framed = _shown({0: _dose(30)})
    assert PreviewKind.SERIES_SURFACE in {preview.kind for preview in found.previews}
    assert framed[0] == set(range(30))
    assert found.pixels_shown == frozenset()
    found, _ = _shown({0: _dose(12)})
    assert found.pixels_shown == {0}


def test_frames_count_only_from_the_first_with_none_missing():
    cine, surface, contours = (
        PreviewKind.SERIES_CINE.value,
        PreviewKind.SERIES_SURFACE.value,
        PreviewKind.STRUCTURE_SET_CONTOURS.value,
    )
    assert pictured_frames([(cine, [(0, 0), (0, 1), (1, 0)])], ()) == {0: 2, 1: 1}
    assert pictured_frames([(cine, [(0, 0), (0, 2)]), (cine, [(1, 1)])], ()) == {}
    assert pictured_frames([(cine, [(0, 0)])], {0}) == {}
    # A volume's surface render shows each slice's first frame; one that
    # shows a later frame is a dose grid's isodose render, which does not
    # count, nor does a contour sheet.
    assert pictured_frames([(surface, [(0, 0), (1, 0)])], ()) == {0: 1, 1: 1}
    assert pictured_frames([(surface, [(0, 0), (0, 1)])], ()) == {}
    assert pictured_frames([(contours, [(0, 0)])], ()) == {}


# Which pixel data's SHA-256 the pack records.


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_digest_of_pixel_data_that_are_not_shown_is_left_out():
    written = _frames(40)
    shown = run_qc._written_sha256(written, False, True)
    assert shown["pixel_sha256"] not in (None, NO_PIXELS_SHA256)
    assert run_qc._written_sha256(written, False, False) == {
        **shown,
        "pixel_sha256": None,
    }


def test_a_file_without_pixel_data_keeps_the_digest_of_none():
    dataset = _slices()[0]
    del dataset.PixelData
    digests = run_qc._written_sha256(files.written(dataset), False, False)
    assert digests["pixel_sha256"] == NO_PIXELS_SHA256


# What the pack and its reader accept.


def _preview(position, kind=PreviewKind.INSTANCE):
    return Preview(
        "P-0001.png",
        kind,
        ((position, 0),),
        1,
        qc_previews.png(np.zeros((2, 2), np.uint8)),
    )


def _pictured(position, digest="1e" * 32):
    entry = _released(position)
    return InstanceEntry(
        entry.position,
        entry.source,
        entry.disposition,
        output=entry.output,
        source_sha256=entry.source_sha256,
        pixel_sha256=digest,
    )


def test_a_pack_records_pixel_data_s_digest_only_where_a_preview_shows_them():
    QcPack(REFERENCE, (_pictured(0),), previews=(_preview(0),))
    QcPack(REFERENCE, (_pictured(0, NO_PIXELS_SHA256),))
    with pytest.raises(QcPackError, match="preview that shows them"):
        QcPack(REFERENCE, (_pictured(0),))
    # A contour sheet's frames of the volume it is drawn with show only its
    # surface, and an instance listed as not previewed is not shown.
    with pytest.raises(QcPackError, match="preview that shows them"):
        QcPack(
            REFERENCE,
            (_pictured(0), _released(1)),
            previews=(
                Preview(
                    "P-0001.png",
                    PreviewKind.STRUCTURE_SET_CONTOURS,
                    ((1, 0), (0, 0)),
                    2,
                    qc_previews.png(np.zeros((2, 2), np.uint8)),
                ),
            ),
        )
    with pytest.raises(QcPackError, match="preview that shows them"):
        QcPack(
            REFERENCE,
            (_pictured(0),),
            previews=(_preview(0),),
            not_previewed=(NotPreviewedEntry(0, NotPreviewedReason.UNREADABLE),),
        )


def test_a_pack_records_pixel_data_s_digest_only_where_previews_show_its_first_frames():
    gap = Preview(
        "P-0001.png",
        PreviewKind.SERIES_CINE,
        ((0, 0), (0, 2)),
        3,
        qc_previews.png(np.zeros((2, 2), np.uint8)),
    )
    with pytest.raises(QcPackError, match="preview that shows them"):
        QcPack(REFERENCE, (_pictured(0),), previews=(gap,))


def test_the_reader_takes_pixel_data_s_digest_only_where_a_preview_shows_them():
    document = {
        "instances": [
            {
                "position": 0,
                "source_sha256": "0f" * 32,
                "pixel_sha256": "1e" * 32,
                "contour_sha256": None,
                "reasons": [],
            }
        ],
        "series": [{"positions": [0]}],
        "previews": [],
        "not_previewed": [],
    }
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
    document["previews"] = [
        {"kind": "instance", "frames": [{"position": 0, "frame": 0}]}
    ]
    files_of = face_review._series_files(json.dumps(document).encode("ascii"))
    (entry,) = files_of[0]
    assert entry[1] == bytes.fromhex("1e" * 32)
    # It carries how many frames, from the first, the previews showed.
    assert entry[4] == 1
    document["previews"][0]["frames"].append({"position": 0, "frame": 2})
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
    document["previews"][0]["frames"][1]["frame"] = 1
    (entry,) = face_review._series_files(json.dumps(document).encode("ascii"))[0]
    assert entry[4] == 2
    document["not_previewed"] = [{"position": 0, "reason": "unreadable-pixel-data"}]
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))


# What a run under the option releases.


def test_a_review_holds_pixel_data_with_more_frames_than_its_pack_showed():
    source, pixels = hashlib.sha256(b"source").digest(), hashlib.sha256(b"x").digest()
    review = FaceReview(
        REFERENCE,
        frozenset({source}),
        frozenset(),
        frozenset({(source, pixels)}),
        frozenset({(source, bytes.fromhex(NO_CONTOURS_SHA256))}),
        frozenset({(source, pixels, 16)}),
    )
    contours = bytes.fromhex(NO_CONTOURS_SHA256)
    assert review.hold_reason(source, pixels, contours, 16) is None
    for frames in (17, 40, None):
        assert (
            review.hold_reason(source, pixels, contours, frames)
            is VisualFeaturesReason.OTHER_PIXEL_DATA
        )
    with pytest.raises(QcPackError, match="frames shown"):
        FaceReview(
            REFERENCE,
            frozenset({source}),
            frozenset(),
            absent_frames=frozenset({(source, pixels, 16)}),
        )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_run_holds_an_instance_whose_frames_its_pack_did_not_all_show():
    data = _frames(40)
    record = InstanceRecord.from_file(data)
    source = hashlib.sha256(data).digest()

    def transformed(shown):
        unseen = InstanceTransform(
            _policy(),
            KEY,
            face_review=FaceReview(REFERENCE, frozenset({source}), frozenset()),
            unvalidated_policy=True,
        )(data, record)
        assert isinstance(unseen, Transformed)
        written = read_source(unseen.data).dataset()
        pixels = pixel_data_sha256(written)
        contours = face_review.contour_data_sha256(written)
        return InstanceTransform(
            _policy(),
            KEY,
            face_review=FaceReview(
                REFERENCE,
                frozenset({source}),
                frozenset(),
                frozenset({(source, pixels)}),
                frozenset({(source, contours)}),
                frozenset({(source, pixels, shown)}),
            ),
            unvalidated_policy=True,
        )(data, record)

    held = transformed(16)
    assert isinstance(held.evidence, HeldEvidence)
    assert HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA) in getattr(
        held.evidence, "held"
    )
    assert not isinstance(transformed(40).evidence, HeldEvidence)


def _verdict_run(data):
    """Run a file alone under ``basic``, attest its series absent, and run
    it again under the option; return the first pack's entry and the second
    run's outcome."""
    directory = Path(tempfile.mkdtemp(prefix="p"))
    try:
        (directory / "in").mkdir()
        (directory / "in" / "image.dcm").write_bytes(data)
        first = run.run(
            run.discover(directory / "in"),
            directory / "r1",
            InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True),
            ReleaseGate(),
            qc_destination=directory / "qc1",
        )
        pack = json.loads(first.qc_pack.read_text("utf-8"))
        _attest(first.qc_pack.parent, {pack["series"][0]["positions"][0]: Face.ABSENT})
        transform = InstanceTransform(
            _policy(),
            KEY,
            face_review=read_face_review(first.qc_pack.parent),
            unvalidated_policy=True,
        )
        second = run.run(
            run.discover(directory / "in"),
            directory / "r2",
            transform,
            ReleaseGate(),
            qc_destination=directory / "qc2",
            reporter=transform.reporter,
        )
        return pack["instances"][0], second.outcomes[0]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize("make, count", [(_frames, 40), (_longer, 1), (_dose, 30)])
def test_a_verdict_of_absent_holds_pixel_data_that_the_pack_did_not_show(make, count):
    # Frames beyond the cine, bytes beyond the frames, and a dose grid that
    # only its isodose render shows in full.
    entry, outcome = _verdict_run(make(count))
    assert entry["pixel_sha256"] is None
    assert outcome.status.value == "held-for-review"
    # Its verdict was on a series whose pixel data the pack has no digest
    # of, so it is held as pixel data other than those reviewed.
    assert outcome.reasons == (
        HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA),
    )


def test_a_verdict_of_absent_releases_pixel_data_whose_every_frame_was_shown():
    for data in (_frames(12), _dose(12)):
        entry, outcome = _verdict_run(data)
        assert entry["pixel_sha256"] is not None
        assert outcome.status.value == "released"
