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
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    face_review,
    qc_previews,
    qc_surfaces,
    run,
    run_qc,
)
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


def _dose_planes(count=4):
    """A series of single-frame RT Dose planes, 3 mm apart."""
    stored = np.zeros((1, 20, 20), np.uint32)
    stored[:, 5:15, 5:15] = 1000
    return [
        files.dose(
            stored,
            position=(-50.0, -50.0, 3.0 * index),
            spacing=(5.0, 5.0),
            offsets=[0.0],
            instance=f"{files.ROOT}.6.{index + 1}",
        )
        for index in range(count)
    ]


def _relabelled(data, modality):
    """A file with its Modality replaced."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.Modality = modality
    return files.written(dataset)


class _Unreadable(pydicom.Dataset):
    """A data set whose Modality cannot be read."""

    def get(self, key, default=None):
        if key == "Modality":
            raise ValueError("unreadable")
        return super().get(key, default)


class _Given(pydicom.Dataset):
    """A data set whose Modality reads as a value no file passing run 1 gives."""

    given: Any = None

    def get(self, key, default=None):
        if key == "Modality":
            return self.given
        return super().get(key, default)


def test_an_rt_dose_is_known_by_its_class_or_a_modality_that_may_be_rtdose():
    def instance(modality=None, sop_class=files.CT_IMAGE_STORAGE, kind=pydicom.Dataset):
        dataset = kind()
        dataset.SOPClassUID = sop_class
        if modality is not None:
            dataset.Modality = modality
        return dataset

    assert face_review.is_rt_dose(instance(sop_class=files.RT_DOSE_STORAGE))
    assert face_review.is_rt_dose(instance("CT", files.RT_DOSE_STORAGE))
    # Any spelling that may be RTDOSE: another case, several values, a
    # character outside printable ASCII, padding aside, or none readable.
    for modality in (
        "RTDOSE",
        "rtdose",
        "RtDose ",
        ["RTDOSE", "CT"],
        ["CT", "RTDOSE"],
        ["CT", "MR"],
        "RTDOS\u00c9",
        "\uff32\uff34\uff24\uff2f\uff33\uff25",
        "\0RTDOSE",
        "RT\x01DOSE",
        "CT\u00e9",
    ):
        assert face_review.is_rt_dose(instance(modality)), modality
    assert face_review.is_rt_dose(instance("CT", kind=_Unreadable))
    # A value that is not text, or text of several values, may be RTDOSE.
    for given in (b"RTDOSE", b"CT", 7, "RTDOSE\\CT", "CT\\MR"):
        dataset = instance(kind=_Given)
        dataset.given = given
        assert face_review.is_rt_dose(dataset), given
    # A missing or empty Modality says nothing about dose, and another
    # modality, padded or not, is not RTDOSE.
    for modality in (None, "", "CT", "CT ", "RTPLAN", "RTDOSE2"):
        assert not face_review.is_rt_dose(instance(modality)), modality


def test_an_rt_dose_is_shown_by_its_dose_levels():
    # A grid's dose levels list every frame, a series of planes' every
    # plane, and a lone plane's map its frame, whether two planes or one.
    for written in (
        {0: _dose(30)},
        {0: _dose(12)},
        dict(enumerate(_dose_planes())),
        dict(enumerate(_dose_planes(2))),
        dict(enumerate(_dose_planes(1))),
        # An RT Dose labelled CT is one by its SOP Class.
        {0: _relabelled(_dose(12), "CT")},
    ):
        found, _ = _shown(written)
        kinds = [preview.kind for preview in found.previews]
        assert PreviewKind.SERIES_DOSE_LEVELS in kinds
        assert PreviewKind.SERIES_SURFACE not in kinds
        assert found.pixels_shown == frozenset(written)


def _altered(data, **attributes):
    """A file with attributes set, or deleted where None."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    for keyword, value in attributes.items():
        if value is None:
            delattr(dataset, keyword)
        else:
            setattr(dataset, keyword, value)
    return files.written(dataset)


def _unshown_doses():
    """RT Dose instances of 12 frames, or a series of planes, whose dose
    levels cannot be drawn, by name."""
    oblique = (0.866025, 0.5, 0.0, -0.5, 0.866025, 0.0)
    longer = pydicom.dcmread(io.BytesIO(_dose(12)))
    longer.PixelData += bytes(4 * 20 * 20)
    return {
        "unscaled": [_altered(_dose(12), DoseGridScaling=None)],
        "zero-scaling": [_altered(_dose(12), DoseGridScaling=0)],
        "negative-scaling": [_altered(_dose(12), DoseGridScaling=-0.001)],
        "signed": [_altered(_dose(12), PixelRepresentation=1)],
        "rescaled": [_altered(_dose(12), RescaleSlope=2, RescaleIntercept=0)],
        "oblique": [_altered(_dose(12), ImageOrientationPatient=list(oblique))],
        "uneven": [
            _altered(_dose(12), GridFrameOffsetVector=[0.0, 3.0, 7.0, *range(9, 18)])
        ],
        "longer": [files.written(longer)],
        "plane-unscaled": [
            *_dose_planes()[:3],
            _altered(_dose_planes()[3], DoseGridScaling=None),
        ],
    }


@pytest.mark.parametrize("name", list(_unshown_doses()))
def test_an_rt_dose_whose_levels_cannot_be_drawn_is_not_shown(name):
    # Its cine strip lists every frame of a short grid, and a series of
    # planes' projection and Otsu render every plane, but the strip is
    # windowed to the highest doses, which can leave a low dose outlining
    # the skin black, and an Otsu render shows one level. A grid whose
    # stored values may be below 0, or rescaled, or not scaled above 0, has
    # doses that its levels would not show.
    written = dict(enumerate(_unshown_doses()[name]))
    found, framed = _shown(written)
    assert all(
        framed[position] == set(range(12 if len(written) == 1 else 1))
        for position in written
    )
    assert found.pixels_shown == frozenset()


def test_an_image_labelled_rtdose_is_not_shown():
    # Its Modality makes it an RT Dose, which only dose levels show, and
    # only an RT Dose by its SOP Class has them.
    found, framed = _shown({0: _relabelled(_frames(12), "RTDOSE")})
    assert framed[0] == set(range(12))
    assert found.pixels_shown == frozenset()


def _thin(block=None, count=40):
    """A series of axial CT slices of air, 0.5 mm apart, with soft tissue in
    part of slice ``block``."""
    template = _slices()[0]
    written = {}
    for index in range(count):
        dataset = pydicom.dcmread(io.BytesIO(files.written(template)))
        dataset.SOPInstanceUID = f"{template.SOPInstanceUID}.{index + 1}"
        dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
        dataset.InstanceNumber = index + 1
        dataset.ImagePositionPatient = [*template.ImagePositionPatient[:2], 0.5 * index]
        rows, columns = dataset.Rows, dataset.Columns
        # Stored values less the intercept of -1024: air, then 0 HU.
        stored = np.full((rows, columns), 24, "<i2")
        if index == block:
            stored[rows // 4 : rows // 2, columns // 4 : columns // 2] = 1024
        dataset.PixelData = stored.tobytes()
        written[index] = files.written(dataset)
    return written


def test_renders_draw_every_slice_of_a_volume_whose_slices_are_closer_than_their_pixels():
    previews = {}
    for block in (None, 5):
        found, _ = _shown(_thin(block))
        assert found.pixels_shown == set(range(40))
        previews[block] = {
            preview.kind: preview.png
            for preview in found.previews
            if preview.kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE)
        }
    # Sampled by nearest neighbour alone, the projection's 5 mm pixels and
    # the render's 2 mm voxels would take neither slice 5.
    heights = np.arange(40) * 0.5
    assert 5 not in qc_surfaces.sampled_indices(heights, 2, 2.0)
    assert 5 not in qc_previews._nearest(heights, np.arange(4) * 5.0)
    assert set(previews[None]) == {PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE}
    for kind, image in previews[None].items():
        assert previews[5][kind] != image, kind


def test_frames_count_only_from_the_first_with_none_missing():
    cine, surface, contours = (
        PreviewKind.SERIES_CINE.value,
        PreviewKind.SERIES_SURFACE.value,
        PreviewKind.STRUCTURE_SET_CONTOURS.value,
    )
    assert pictured_frames([(cine, [(0, 0), (0, 1), (1, 0)])], ()) == {0: 2, 1: 1}
    assert pictured_frames([(cine, [(0, 0), (0, 2)]), (cine, [(1, 1)])], ()) == {}
    assert pictured_frames([(cine, [(0, 0)])], {0}) == {}
    # A contour sheet's frames never count, and where kinds are named, only
    # those count, as only dose levels do for an RT Dose.
    assert pictured_frames([(surface, [(0, 0), (0, 1)])], ()) == {0: 2}
    assert pictured_frames([(contours, [(0, 0)])], ()) == {}
    levels = PreviewKind.SERIES_DOSE_LEVELS.value
    previews = [(cine, [(0, 0), (1, 0)]), (levels, [(1, 0), (1, 1)])]
    assert pictured_frames(previews, ()) == {0: 1, 1: 2}
    assert pictured_frames(previews, (), {levels}) == {1: 2}
    assert pictured_frames(previews, (), {levels, contours}) == {1: 2}


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
    # It carries how many frames, from the first, the previews showed, and
    # none that dose levels showed.
    assert entry[4] == 1 and entry[5] is None
    document["previews"][0]["frames"].append({"position": 0, "frame": 2})
    with pytest.raises(QcPackError, match="not of its format"):
        face_review._series_files(json.dumps(document).encode("ascii"))
    document["previews"][0]["frames"][1]["frame"] = 1
    (entry,) = face_review._series_files(json.dumps(document).encode("ascii"))[0]
    assert entry[4] == 2
    # Dose levels' frames count for both.
    document["previews"].append(
        {"kind": "series-dose-levels", "frames": [{"position": 0, "frame": 0}]}
    )
    (entry,) = face_review._series_files(json.dumps(document).encode("ascii"))[0]
    assert entry[4:] == (2, 1)
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
    for frames in (0, 17, 40, None):
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


def test_a_review_holds_an_rt_dose_unless_its_dose_levels_showed_every_frame():
    source, pixels = hashlib.sha256(b"source").digest(), hashlib.sha256(b"x").digest()
    contours = bytes.fromhex(NO_CONTOURS_SHA256)

    def review(dose_frames):
        return FaceReview(
            REFERENCE,
            frozenset({source}),
            frozenset(),
            frozenset({(source, pixels), (source, bytes.fromhex(NO_PIXELS_SHA256))}),
            frozenset({(source, contours)}),
            frozenset({(source, pixels, 16)}),
            dose_frames,
        )

    held = VisualFeaturesReason.OTHER_PIXEL_DATA
    # Other previews' frames do not count for an RT Dose, so a review
    # without dose levels' holds every one with pixel data.
    for dose_frames in (None, frozenset()):
        assert review(dose_frames).hold_reason(source, pixels, contours, 16) is None
        assert (
            review(dose_frames).hold_reason(source, pixels, contours, 16, dose=True)
            is held
        )
    shown = review(frozenset({(source, pixels, 12)}))
    assert shown.hold_reason(source, pixels, contours, 12, dose=True) is None
    for frames in (0, 13, None):
        assert shown.hold_reason(source, pixels, contours, frames, dose=True) is held
    # One without pixel data, of dose-volume histograms alone, shows no face.
    none = bytes.fromhex(NO_PIXELS_SHA256)
    assert review(None).hold_reason(source, none, contours, None, dose=True) is None
    with pytest.raises(QcPackError, match="frames shown"):
        FaceReview(
            REFERENCE,
            frozenset({source}),
            frozenset(),
            absent_dose_frames=frozenset({(source, pixels, 16)}),
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


def _verdict_run(*data):
    """Run files alone under ``basic``, attest their series absent, and run
    them again under the option; return the first pack's entries and the
    second run's outcomes."""
    directory = Path(tempfile.mkdtemp(prefix="p"))
    try:
        (directory / "in").mkdir()
        for index, each in enumerate(data):
            (directory / "in" / f"image-{index:02d}.dcm").write_bytes(each)
        first = run.run(
            run.discover(directory / "in"),
            directory / "r1",
            InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True),
            ReleaseGate(),
            qc_destination=directory / "qc1",
        )
        pack = json.loads(first.qc_pack.read_text("utf-8"))
        _attest(
            first.qc_pack.parent,
            {series["positions"][0]: Face.ABSENT for series in pack["series"]},
        )
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
        return pack["instances"], second.outcomes
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize(
    "data",
    [
        [_frames(40)],
        [_longer(1)],
        _unshown_doses()["unscaled"],
        _unshown_doses()["longer"],
        _unshown_doses()["plane-unscaled"],
    ],
    ids=["frames", "bytes", "unscaled-grid", "longer-grid", "unscaled-plane"],
)
def test_a_verdict_of_absent_holds_pixel_data_that_the_pack_did_not_show(data):
    # Frames beyond the cine, bytes beyond the frames, and RT Dose whose
    # dose levels the pack could not draw.
    entries, outcomes = _verdict_run(*data)
    assert len(outcomes) == len(data)
    for entry, outcome in zip(entries, outcomes):
        assert entry["pixel_sha256"] is None
        assert outcome.status.value == "held-for-review"
        # Its verdict was on a series whose pixel data the pack has no
        # digest of, so it is held as pixel data other than those reviewed.
        assert outcome.reasons == (
            HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA),
        )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize(
    "data",
    [[_frames(12)], [_dose(30)], [_dose(12)], _dose_planes(), _dose_planes(1)],
    ids=["frames", "grid", "short-grid", "planes", "plane"],
)
def test_a_verdict_of_absent_releases_pixel_data_whose_every_frame_was_shown(data):
    entries, outcomes = _verdict_run(*data)
    assert len(outcomes) == len(data)
    for entry, outcome in zip(entries, outcomes):
        assert entry["pixel_sha256"] is not None
        assert outcome.status.value == "released"


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize(
    "data",
    [
        _dose(12),
        _relabelled(_frames(12), "RTDOSE"),
        _relabelled(_frames(12), "rtdose"),
        _relabelled(_frames(12), ["RTDOSE", "CT"]),
        _relabelled(_frames(12), "\0RTDOSE"),
    ],
    ids=["rt-dose", "ct-rtdose", "ct-lower-case", "ct-two-values", "ct-nul"],
)
def test_a_run_releases_an_rt_dose_only_where_its_dose_levels_showed_every_frame(
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

    def transformed(dose_frames):
        return InstanceTransform(
            _policy(),
            KEY,
            face_review=FaceReview(
                REFERENCE,
                frozenset({source}),
                frozenset(),
                frozenset({(source, pixels)}),
                frozenset({(source, face_review.contour_data_sha256(written))}),
                frozenset({(source, pixels, 12)}),
                dose_frames,
            ),
            unvalidated_policy=True,
        )(data, record)

    # A review that binds the verdict to every frame through other previews
    # does not release an RT Dose, by its SOP Class or Modality, nor one
    # whose dose levels showed too few frames.
    for dose_frames in (None, frozenset({(source, pixels, 11)})):
        held = transformed(dose_frames)
        assert isinstance(held, Transformed)
        assert isinstance(held.evidence, HeldEvidence)
        assert getattr(held.evidence, "held") == (
            HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA),
        )
    released = transformed(frozenset({(source, pixels, 12)}))
    assert isinstance(released, Transformed)
    assert not isinstance(released.evidence, HeldEvidence)
