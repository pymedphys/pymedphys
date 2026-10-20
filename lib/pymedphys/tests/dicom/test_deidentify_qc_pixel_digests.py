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

import io
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_review, qc_previews, run_qc
from pymedphys._dicom.deidentify.qc_pack import (
    NO_PIXELS_SHA256,
    InstanceEntry,
    NotPreviewedEntry,
    NotPreviewedReason,
    Preview,
    PreviewKind,
    QcPack,
    QcPackError,
)

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_qc_face_verdicts import REFERENCE, _released

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
    document["not_previewed"] = [{"position": 0, "reason": "unreadable-pixel-data"}]
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
