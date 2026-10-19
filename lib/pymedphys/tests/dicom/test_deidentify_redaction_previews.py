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

"""Tests of what the QC pack holds for the review of Clean Pixel Data.

The pack lists the regions that the option blacked out in each frame of each
instance it cleaned, and previews every frame of it at full resolution, as
received beside as written where the frame has regions, and a monochrome
frame as written again over its full range. Every image is synthetic.
"""

import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_pack, qc_previews, run
from pymedphys._dicom.deidentify.instance_transform import ReleaseGate
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    InstanceEntry,
    NotPreviewedEntry,
    NotPreviewedReason,
    Preview,
    PreviewKind,
    QcPackError,
    RedactionEntry,
)
from pymedphys._dicom.deidentify.reasons import PixelDataReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.run_qc import RedactionMaterial
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_references as synthetic
from .test_deidentify_pixel_cleaning import Finder, _ct, _frame, _rgb, _transform
from .test_deidentify_qc_pack import SOURCE_PATH, _pack, _sequestered, _written
from .test_deidentify_qc_previews import _decoded

# A run needs a base directory short enough for Windows' output path limit.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

# Large enough to have pixels inside it that its outline leaves alone.
BOX = TextBox(1, 1, 5, 6)
OUTLINE = (255, 0, 255)
GUTTER = 8
BLACKED_OUT = PixelDataReason.TEXT_BLACKED_OUT
NOTHING_FOUND = PixelDataReason.NO_TEXT_FOUND


def _cleaned(dataset, finder):
    """The source file, the transform's result, and its redaction material."""
    data = synthetic.written(dataset)
    result = _transform(finder)(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    (material,) = [item for item in result.qc if isinstance(item, RedactionMaterial)]
    return data, result, material


def _entry(material, position=0):
    return RedactionEntry(
        position,
        material.reason,
        material.frames,
        material.rows,
        material.columns,
        material.regions,
    )


def _previews(dataset, finder):
    data, result, material = _cleaned(dataset, finder)
    return qc_previews.previews_of({0: result.data}, (), {0: (data, _entry(material))})


def _redaction_images(previews):
    return [
        (preview, _decoded(preview.png))
        for preview in previews.previews
        if preview.kind is PreviewKind.REDACTION
    ]


def _outline(shape, box=BOX):
    """The pixels of a box's own edge."""
    mask = np.zeros(shape, dtype=bool)
    mask[box.top : box.bottom, box.left : box.right] = True
    mask[box.top + 1 : box.bottom - 1, box.left + 1 : box.right - 1] = False
    return mask


def _interior(shape, box=BOX):
    mask = np.zeros(shape, dtype=bool)
    mask[box.top + 1 : box.bottom - 1, box.left + 1 : box.right - 1] = True
    return mask


# The transform's material.


def test_the_transform_gives_the_regions_and_source_for_review():
    frames = np.stack([_frame(), _frame(start=900)])
    data, _, material = _cleaned(_ct(frames), Finder((BOX,), frames={1}))

    assert material.reason is BLACKED_OUT
    assert (material.frames, material.rows, material.columns) == (2, 6, 8)
    assert material.regions == ((1, (BOX,)),)
    assert material.source == data
    assert "source" not in repr(material) and str(data[:16]) not in repr(material)


def test_a_frame_without_text_gives_no_regions_and_keeps_no_source():
    _, _, material = _cleaned(_ct(_frame()), Finder(()))
    assert material.reason is NOTHING_FOUND
    assert (material.frames, material.regions, material.source) == (1, (), None)


# The pack's entries.


@pytest.mark.parametrize(
    "fields",
    [
        ("text-blacked-out", 1, 6, 8, ((0, (BOX,)),)),
        (BLACKED_OUT, 0, 6, 8, ()),
        (BLACKED_OUT, True, 6, 8, ((0, (BOX,)),)),
        (BLACKED_OUT, 1, 0, 8, ((0, (BOX,)),)),
        (BLACKED_OUT, 1, 6, True, ((0, (BOX,)),)),
        (BLACKED_OUT, 1, 4, 8, ((0, (BOX,)),)),
        (BLACKED_OUT, 1, 6, 5, ((0, (BOX,)),)),
        (BLACKED_OUT, 1, 6, 8, ((1, (BOX,)),)),
        (BLACKED_OUT, 1, 6, 8, ((0, ()),)),
        (BLACKED_OUT, 1, 6, 8, ((0, (TextBox(2, 2, 3, 3), BOX)),)),
        (BLACKED_OUT, 1, 6, 8, ((0, (BOX, BOX)),)),
        (BLACKED_OUT, 1, 6, 8, ((0, ((1, 1, 5, 6),)),)),
        (BLACKED_OUT, 2, 6, 8, ((1, (BOX,)), (0, (BOX,)))),
        (BLACKED_OUT, 2, 6, 8, ((0, (BOX,)), (0, (TextBox(0, 0, 1, 1),)))),
        (BLACKED_OUT, 1, 6, 8, ()),
        (NOTHING_FOUND, 1, 6, 8, ((0, (BOX,)),)),
    ],
    ids=[
        "reason",
        "no-frames",
        "boolean-frames",
        "no-rows",
        "boolean-columns",
        "box-past-rows",
        "box-past-columns",
        "frame-out-of-range",
        "no-boxes",
        "unsorted-boxes",
        "repeated-box",
        "box-as-tuple",
        "frames-out-of-order",
        "frame-twice",
        "text-without-regions",
        "regions-without-text",
    ],
)
def test_a_redaction_entry_is_checked(fields):
    with pytest.raises(QcPackError, match="cleaned instance 0"):
        RedactionEntry(0, *fields)


def _unshown(position=0):
    """A cleaned instance that the pack lists as not previewed."""
    return (NotPreviewedEntry(position, NotPreviewedReason.SOURCE_NOT_SHOWN),)


def _held(position=0):
    return InstanceEntry(
        position,
        SOURCE_PATH,
        Disposition.HELD_FOR_REVIEW,
        reasons=("pixel data held",),
    )


def test_the_pack_lists_each_cleaned_instance_once_in_order():
    entry = RedactionEntry(0, BLACKED_OUT, 1, 6, 8, ((0, (BOX,)),))
    later = RedactionEntry(1, NOTHING_FOUND, 1, 6, 8, ())
    instances = (_held(0), _held(1))
    unshown = _unshown(0) + _unshown(1)
    assert _pack(
        instances=instances, redactions=(entry, later), not_previewed=unshown
    ).redactions
    for redactions in ((later, entry), (entry, entry)):
        with pytest.raises(QcPackError, match="redactions must list"):
            _pack(instances=instances, redactions=redactions, not_previewed=unshown)
    with pytest.raises(QcPackError, match="run position without"):
        _pack(instances=(_held(),), redactions=(later,))


def test_the_pack_lists_no_redaction_of_a_sequestered_instance():
    entry = RedactionEntry(0, NOTHING_FOUND, 1, 6, 8, ())
    assert _pack(
        instances=(_written(),), redactions=(entry,), not_previewed=_unshown()
    ).redactions
    with pytest.raises(QcPackError, match="neither released nor held"):
        _pack(
            instances=(_sequestered(),), redactions=(entry,), not_previewed=_unshown()
        )


def test_the_document_gives_each_frames_boxes():
    entry = RedactionEntry(
        0, BLACKED_OUT, 3, 6, 8, ((0, (BOX,)), (2, (TextBox(0, 0, 1, 2), BOX)))
    )
    pack = _pack(instances=(_held(),), redactions=(entry,), not_previewed=_unshown())
    document = qc_pack.pack_document(pack)
    assert document["redactions"] == [
        {
            "position": 0,
            "reason": "text-blacked-out",
            "frames": 3,
            "rows": 6,
            "columns": 8,
            "regions": [
                {"frame": 0, "boxes": [[1, 1, 5, 6]]},
                {"frame": 2, "boxes": [[0, 0, 1, 2], [1, 1, 5, 6]]},
            ],
        }
    ]
    assert "redactions=1" in repr(pack)


def _redaction_preview(number, frames, total=2):
    return Preview(
        f"P-{number:04d}.png",
        PreviewKind.REDACTION,
        frames,
        total,
        qc_previews.png(np.zeros((1, 1), np.uint8)),
    )


@pytest.mark.parametrize(
    "previews, not_previewed",
    [
        ((), ()),
        ((_redaction_preview(1, ((0, 0),)),), ()),
        ((_redaction_preview(1, ((0, 1),)), _redaction_preview(2, ((0, 0),))), ()),
        ((_redaction_preview(1, ((0, 0), (0, 1))),), ()),
        ((_redaction_preview(1, ((0, 0),), total=1),), ()),
        ((_redaction_preview(1, ((0, 0),)),), _unshown()),
    ],
    ids=["none", "a-frame-missing", "out-of-order", "two-frames", "total", "unshown"],
)
def test_the_pack_previews_each_frame_of_a_cleaned_instance_or_says_why_not(
    previews, not_previewed
):
    entry = RedactionEntry(0, NOTHING_FOUND, 2, 6, 8, ())
    shown = (_redaction_preview(1, ((0, 0),)), _redaction_preview(2, ((0, 1),)))
    assert _pack(instances=(_held(),), redactions=(entry,), previews=shown).previews

    with pytest.raises(QcPackError, match="redaction preview"):
        _pack(
            instances=(_held(),),
            redactions=(entry,),
            previews=previews,
            not_previewed=not_previewed,
        )


def test_the_pack_has_no_redaction_preview_of_an_instance_not_cleaned():
    with pytest.raises(QcPackError, match="redaction preview"):
        _pack(instances=(_held(),), previews=(_redaction_preview(1, ((0, 0),), 1),))


# The previews.


def test_every_frame_is_previewed_and_one_with_regions_beside_its_source():
    frames = np.stack([_frame(), _frame(start=900)])
    previews = _previews(_ct(frames), Finder((BOX,), frames={0}))

    shown = _redaction_images(previews)
    assert [preview.frames for preview, _ in shown] == [((0, 0),), ((0, 1),)]
    assert all(preview.total_frames == 2 for preview, _ in shown)
    (_, first), (_, second) = shown
    rows, columns = frames.shape[1:]
    # As received, as written, and as written over its full range.
    assert first.shape == (rows, 3 * columns + 2 * GUTTER, 3)
    for start in (columns, 2 * columns + GUTTER):
        assert np.all(first[:, start : start + GUTTER] == 128)
    # The second frame has no region, so it is shown in grey, as written
    # and over its full range.
    assert second.shape == (rows, 2 * columns + GUTTER)
    assert np.all(second[:, columns : columns + GUTTER] == 128)


def test_regions_are_outlined_inside_their_own_edges_and_nothing_else_changes():
    frame = _frame()
    previews = _previews(_ct(frame), Finder((BOX,)))

    ((_, image),) = _redaction_images(previews)
    before, after, full = _panels(image, frame.shape[1])
    edge, interior = _outline(frame.shape), _interior(frame.shape)
    for panel in (before, after, full):
        assert np.all(panel[edge] == OUTLINE)
        assert not np.all(panel[~edge] == OUTLINE, axis=1).any()
    outside = ~(edge | interior)
    # Both panels are windowed together, so what the region left alone is
    # shown the same in both.
    assert np.array_equal(before[outside], after[outside])
    # The fill is the frame's smallest value, so it shows as the window's
    # black; the source showed the text's values there.
    assert np.all(after[interior] == 0)
    assert np.any(before[interior] != 0)


def _panels(image, columns):
    """Each image of a preview, from left to right."""
    step = columns + GUTTER
    return tuple(
        image[:, start : start + columns] for start in range(0, image.shape[1], step)
    )


@pytest.mark.parametrize("photometric", ["MONOCHROME1", "MONOCHROME2"])
def test_the_fill_shows_black_whatever_the_photometric_interpretation(photometric):
    frame = _frame()
    previews = _previews(_ct(frame, photometric=photometric), Finder((BOX,)))

    ((_, image),) = _redaction_images(previews)
    before, after, full = _panels(image, frame.shape[1])
    interior = _interior(frame.shape)
    assert np.all(after[interior] == 0)
    assert np.all(full[interior] == 0)
    assert np.any(before[interior] != 0)
    outside = ~(_outline(frame.shape) | interior)
    assert np.array_equal(before[outside], after[outside])


def test_signed_rescaled_values_are_shown_through_one_window_from_the_source():
    frame = _frame() - 2000
    dataset = _ct(frame, signed=True)
    dataset.RescaleSlope, dataset.RescaleIntercept = 2, -1024
    previews = _previews(dataset, Finder((BOX,)))

    ((_, image),) = _redaction_images(previews)
    before, after, _ = _panels(image, frame.shape[1])
    interior = _interior(frame.shape)
    outside = ~(_outline(frame.shape) | interior)
    # The fill changes the written frame's percentiles, so equal pixels
    # outside the regions show that one window, the source's, was used.
    assert np.array_equal(before[outside], after[outside])
    window = qc_previews._window(  # pylint: disable = protected-access
        (frame * 2 - 1024).astype(np.float32)
    )
    expected = qc_previews._grey(  # pylint: disable = protected-access
        (frame * 2 - 1024).astype(np.float32), window, False
    )
    assert np.array_equal(before[outside][:, 0], expected[outside])
    assert np.all(after[interior] == 0)


@pytest.mark.parametrize("planar", [0, 1])
def test_an_rgb_frame_is_shown_in_colour_with_its_regions_outlined(planar):
    frame = (np.arange(6 * 8 * 3).reshape(6, 8, 3) * 5 + 40) % 256
    previews = _previews(_rgb(frame, planar=planar), Finder((BOX,)))

    ((_, image),) = _redaction_images(previews)
    # Colour has no window to widen, so it has no full-range image.
    assert image.shape == (6, 2 * 8 + GUTTER, 3)
    before, after = _panels(image, 8)
    outside = ~(_outline(frame.shape[:2]) | _interior(frame.shape[:2]))
    assert np.array_equal(before[outside], frame[outside])
    assert np.array_equal(after[outside], frame[outside])
    assert np.all(after[_interior(frame.shape[:2])] == 0)
    assert np.all(before[_outline(frame.shape[:2])] == OUTLINE)


def test_an_instance_whose_source_does_not_match_is_listed_not_previewed():
    data, result, material = _cleaned(_ct(_frame()), Finder((BOX,)))
    other = synthetic.written(_ct(_frame(rows=7)))
    previews = qc_previews.previews_of(
        {0: result.data}, (), {0: (other, _entry(material))}
    )
    assert not _redaction_images(previews)
    assert [entry.reason for entry in previews.not_previewed] == [
        NotPreviewedReason.SOURCE_NOT_SHOWN
    ]
    assert data != other


def test_an_instance_with_regions_and_no_source_is_listed_not_previewed():
    _, result, material = _cleaned(_ct(_frame()), Finder((BOX,)))
    previews = qc_previews.previews_of(
        {0: result.data}, (), {0: (None, _entry(material))}
    )
    assert not _redaction_images(previews)
    assert [entry.reason for entry in previews.not_previewed] == [
        NotPreviewedReason.SOURCE_NOT_SHOWN
    ]


def test_an_instance_without_text_found_is_previewed_as_written():
    previews = _previews(_ct(_frame()), Finder(()))
    ((preview, image),) = _redaction_images(previews)
    assert preview.frames == ((0, 0),)
    assert image.shape == (6, 2 * 8 + GUTTER)


def test_text_that_the_percentile_window_saturates_stands_apart_over_the_full_range():
    # Anatomy from 0 to 1,500, bone at 1,600 in 2% of the frame, so that
    # the 99.5th percentile falls on it, and a pixel of missed text at the
    # largest stored value.
    frame = np.tile(np.linspace(0, 1500, 20).round().astype(int), (20, 1))
    frame[10, 2:10] = 1600
    frame[10, 12] = 4095
    previews = _previews(_ct(frame), Finder(()))

    ((_, image),) = _redaction_images(previews)
    windowed, full = _panels(image, 20)
    bone, text = (10, 3), (10, 12)
    assert windowed[bone] == windowed[text] == 255
    assert full[text] == 255 and full[bone] < 128
    values = frame.astype(np.float32)
    expected = qc_previews._grey(  # pylint: disable = protected-access
        values, (0.0, 4095.0), False
    )
    assert np.array_equal(full, expected)


# A run.


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_runs_pack_lists_each_cleaned_instance_and_previews_its_frames(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    frames = np.stack([_frame(), _frame(start=900)])
    datasets = [_ct(frames), synthetic.rt_plan()]
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    transform = _transform(Finder((BOX,), frames={1}))

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
    )

    assert [outcome.status for outcome in result.outcomes] == [
        run.Status.HELD_FOR_REVIEW,
        run.Status.RELEASED,
    ]
    pack = json.loads((tmp_path / "qc" / "qc-pack.json").read_text(encoding="ascii"))
    assert pack["format"] == "pymedphys-deid-qc-pack/9"
    assert pack["redactions"] == [
        {
            "position": 0,
            "reason": "text-blacked-out",
            "frames": 2,
            "rows": 6,
            "columns": 8,
            "regions": [{"frame": 1, "boxes": [[1, 1, 5, 6]]}],
        }
    ]
    redactions = [entry for entry in pack["previews"] if entry["kind"] == "redaction"]
    assert [entry["frames"] for entry in redactions] == [
        [{"position": 0, "frame": 0}],
        [{"position": 0, "frame": 1}],
    ]
    for entry in redactions:
        assert (tmp_path / "qc" / entry["file"]).is_file()
