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

"""Tests of the QC pack's skin-surface renders.

Every volume is synthetic: an ellipsoid head, with a nose on its anterior
surface and, where asked, an ear on the patient's left, on a grid of 2 mm
voxels in the patient's coordinates, where x runs to the patient's left, y
posterior, and z superior.
"""

# The tests share the synthetic head and its series builders, so they stay
# in one module.
# pylint: disable = too-many-lines

import io
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import qc_previews, qc_surfaces
from pymedphys._dicom.deidentify.qc_pack import PreviewKind

from .test_deidentify_qc_previews import _decoded, _file, _image

SIDE = 40  # voxels a side, 2 mm apart, from 0 to 78 mm
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"
AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
# Rows run to the patient's right, and slices are given from superior.
FLIPPED = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
CORONAL = (1.0, 0.0, 0.0, 0.0, 0.0, -1.0)
TOP = 2.0 * (SIDE - 1)
# The nose is below the middle of the head, and the ear level with it.
NOSE_Z = 32.0
EAR_Z = 40.0


def _body(nose=True, ear=False, inside=40, outside=-1000):
    """Values at (x, y, z) = 2 * (i, j, k) mm, indexed [k, j, i]."""
    z, y, x = np.meshgrid(*(2.0 * np.arange(SIDE),) * 3, indexing="ij")
    head = ((x - 40) / 24) ** 2 + ((y - 40) / 28) ** 2 + ((z - 40) / 30) ** 2 <= 1
    if nose:
        # The head's anterior surface is at y = 12 mm, level with its middle.
        head |= (x - 40) ** 2 + (y - 14) ** 2 + (z - NOSE_Z) ** 2 <= 25
    if ear:
        head |= (x - 64) ** 2 + (y - 40) ** 2 + (z - EAR_Z) ** 2 <= 25
    return np.where(head, inside, outside)


def _with(data, **attributes):
    dataset = pydicom.dcmread(io.BytesIO(data))
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    return _file(dataset)


def _axial(body, modality="CT", series="2.25.7101"):
    """Axial slices from inferior to superior: rows posterior, columns left."""
    return {
        k: _with(
            _image(
                body[k],
                number=k + 1,
                series=series,
                origin=(0.0, 0.0, 2.0 * k),
                spacing=(2.0, 2.0),
            ),
            Modality=modality,
        )
        for k in range(SIDE)
    }


def _flipped(body):
    """Axial slices from superior, with rows running to the patient's right."""
    return {
        position: _with(
            _image(
                body[SIDE - 1 - position][:, ::-1],
                number=position + 1,
                series="2.25.7102",
                origin=(TOP, 0.0, TOP - 2.0 * position),
                orientation=FLIPPED,
                spacing=(2.0, 2.0),
            ),
            Modality="CT",
        )
        for position in range(SIDE)
    }


def _coronal(body):
    """Coronal slices from anterior: rows run inferior, columns left."""
    return {
        j: _with(
            _image(
                body[::-1, j, :],
                number=j + 1,
                series="2.25.7103",
                origin=(0.0, 2.0 * j, TOP),
                orientation=CORONAL,
                spacing=(2.0, 2.0),
            ),
            Modality="CT",
        )
        for j in range(SIDE)
    }


def _dose(
    grid,
    offsets,
    *,
    origin=(0.0, 0.0, 0.0),
    orientation=AXIAL,
    scaling=0.001,
    instance="2.25.9101",
):
    """An RT Dose instance; grid is (frames, rows, columns) of stored values."""
    grid = np.asarray(grid)
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = RT_DOSE_STORAGE
    dataset.SOPInstanceUID = instance
    dataset.SeriesInstanceUID = "2.25.7104"
    dataset.Modality = "RTDOSE"
    dataset.NumberOfFrames = len(grid)
    dataset.FrameIncrementPointer = 0x3004000C
    dataset.Rows, dataset.Columns = grid.shape[1:]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = dataset.BitsStored = 32
    dataset.HighBit = 31
    dataset.PixelRepresentation = 0
    dataset.PixelData = grid.astype("<u4").tobytes()
    dataset.PixelSpacing = [2.0, 2.0]
    dataset.ImageOrientationPatient = list(orientation)
    dataset.ImagePositionPatient = list(origin)
    if offsets is not None:
        dataset.GridFrameOffsetVector = list(offsets)
    if scaling is not None:
        dataset.DoseGridScaling = scaling
    return _file(dataset)


def _surface(written, kind=PreviewKind.SERIES_SURFACE):
    """The PNG of the only surface render of the files, or of their only
    dose-levels render."""
    previews = qc_previews.previews_of(written, ())
    surfaces = [p for p in previews.previews if p.kind is kind]
    assert len(surfaces) == 1
    return surfaces[0].png


def _levels(data, rows):
    """Each row of a dose-levels render of ``rows`` rows, as an image."""
    image = _decoded(data)
    gap = qc_surfaces._GAP_PIXELS  # pylint: disable = protected-access
    height = (image.shape[0] - (rows - 1) * gap) // rows
    assert image.shape[0] == rows * height + (rows - 1) * gap
    assert not image[height : height + gap].any()
    return [image[index * (height + gap) :][:height] for index in range(rows)]


def _views(data):
    """Each view of a surface render, in the order of qc_surfaces.VIEWS."""
    image = _decoded(data) if isinstance(data, bytes) else data
    count = len(qc_surfaces.VIEWS)
    gap = qc_surfaces._GAP_PIXELS  # pylint: disable = protected-access
    width = (image.shape[1] - (count - 1) * gap) // count
    assert image.shape[1] == count * width + (count - 1) * gap
    return {
        view: image[:, index * (width + gap) : index * (width + gap) + width]
        for index, view in enumerate(qc_surfaces.VIEWS)
    }


def _rows(low, high):
    """The rows of a view that show z from ``low`` to ``high`` mm, and the
    rows around them that the shading of their surface can change."""
    margin = len(qc_surfaces._SMOOTHING) // 2 + 1  # pylint: disable = protected-access
    return set(
        range(
            math.floor((TOP - high) / 2) - margin,
            math.ceil((TOP - low) / 2) + margin + 1,
        )
    )


def _changed(first, second):
    """The rows and columns where one view's surface differs from another's."""
    rows, columns = np.nonzero(first != second)
    assert rows.size
    return set(rows.tolist()), set(columns.tolist())


@pytest.mark.parametrize(
    "values, expected",
    [
        (np.concatenate([np.full(300, 10.0), np.full(700, 200.0)]), (10, 200)),
        (np.array([0.0, 1.0]), (0, 1)),
    ],
)
def test_otsu_splits_two_populations_between_them(values, expected):
    rng = np.random.default_rng(0)
    noisy = values + rng.uniform(-1, 1, values.size) * (values.size > 2)
    padded = np.concatenate([noisy, [np.nan, np.nan]])

    level = qc_surfaces._otsu(padded)  # pylint: disable = protected-access

    assert level is not None and expected[0] < level <= expected[1]
    assert ((padded >= level) == (np.nan_to_num(padded) > np.mean(expected))).all()


@pytest.mark.parametrize("values", [np.full(5, 3.0), np.full(3, np.nan), np.zeros(0)])
def test_otsu_gives_no_threshold_without_two_values(values):
    assert qc_surfaces._otsu(values) is None  # pylint: disable = protected-access


@pytest.mark.parametrize("value", [300.0, 3.0e8, 1.0e30])
def test_otsu_puts_padding_below_one_value(value):
    values = np.array([np.nan, value, value, np.nan], np.float32)

    level = qc_surfaces._otsu(values, padding=True)  # pylint: disable = protected-access

    assert level is not None
    assert ((values >= level) == np.isfinite(values)).all()


@pytest.mark.parametrize("padding", [False, True])
def test_otsu_is_the_same_counted_in_parts(monkeypatch, padding):
    rng = np.random.default_rng(5)
    values = np.concatenate(
        [rng.normal(-800, 50, 400), rng.normal(60, 30, 600), np.full(100, np.nan)]
    ).astype(np.float32)
    rng.shuffle(values)
    volume = values.reshape(11, 10, 10)
    # pylint: disable = protected-access
    whole = qc_surfaces._otsu(volume, padding=padding)
    assert whole is not None

    for part in (1, 7, 64):
        monkeypatch.setattr(qc_surfaces, "_OTSU_PART", part)
        assert qc_surfaces._otsu(volume, padding=padding) == whole


@pytest.mark.deid_requirement("MIDI-BP-15", "MIDI-BP-17")
@pytest.mark.pydicom
def test_a_volume_gets_a_surface_render_after_its_projection():
    written = _axial(_body())

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
    ]
    mip, surface = previews.previews[1:]
    assert surface.name == "P-0003.png"
    assert surface.frames == mip.frames == tuple((k, 0) for k in range(SIDE))
    assert surface.total_frames == SIDE
    views = _views(surface.png)
    # Head to foot at 2 mm a voxel, as the slices are.
    assert all(view.shape[0] == SIDE and view.any() for view in views.values())


@pytest.mark.pydicom
def test_a_series_that_is_not_a_volume_gets_no_surface_render():
    body = _body()
    two = {k: data for k, data in _axial(body).items() if k in (19, 20)}
    one = {0: _with(_image(body[20], series=None, spacing=(2.0, 2.0)), Modality="CT")}

    for written in (two, one):
        previews = qc_previews.previews_of(written, ())
        assert [preview.kind for preview in previews.previews] == [
            PreviewKind.SERIES_CINE
        ]


@pytest.mark.parametrize("spacing, rendered", [(2.0, True), (600.0, False)])
@pytest.mark.pydicom
def test_a_volume_too_large_to_render_has_only_its_cine_strip_and_is_held_beyond_it(
    spacing, rendered
):
    # 20 slices of 3 by 3 pixels: 1,200 mm across at 600 mm a pixel.
    count = 20
    written = {
        k: _with(
            _image(
                np.full((3, 3), 40),
                number=k + 1,
                series="2.25.7105",
                origin=(0.0, 0.0, 2.0 * k),
                spacing=(spacing, spacing),
            ),
            Modality="CT",
        )
        for k in range(count)
    }

    previews = qc_previews.previews_of(written, ())

    kinds = [preview.kind for preview in previews.previews]
    if rendered:
        assert kinds == [
            PreviewKind.SERIES_CINE,
            PreviewKind.SERIES_MIP,
            PreviewKind.SERIES_SURFACE,
        ]
        assert previews.pixels_shown == frozenset(range(count))
    else:
        assert kinds == [PreviewKind.SERIES_CINE]
        (cine,) = previews.previews
        shown = {position for position, _ in cine.frames}
        assert len(shown) == qc_previews.CINE_FRAMES < count
        assert previews.pixels_shown == frozenset(shown)


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_the_frontal_view_meets_the_nose_first():
    # The volume's own axes: slices superior, rows posterior, columns left.
    directions = (np.array([0, 0, 1.0]), np.array([0, 1.0, 0]), np.array([1.0, 0, 0]))
    depths = {}
    for nose in (True, False):
        body = _body(nose=nose)
        surface = qc_surfaces.Surface(
            qc_surfaces.grid(
                directions,
                [2.0 * k for k in range(SIDE)],
                (2.0, 2.0),
                (SIDE, SIDE),
                qc_surfaces.Threshold.CT,
            )
        )
        for k in range(SIDE):
            surface.add(body[k].astype(np.float32))
        mask = surface.mask()
        # From superior, from anterior, and from the patient's right.
        assert (mask == (body >= qc_surfaces.CT_THRESHOLD)[::-1]).all()
        depths[nose] = qc_surfaces._depths(mask, 0)  # pylint: disable = protected-access

    nearest = depths[True][depths[True] >= 0].min()
    rows, columns = np.nonzero(depths[True] == nearest)
    # The tip, at y = 10 mm, is 2 voxels in front of the face behind it, at
    # y = 14 mm, and in the rows of z = 30, 32, and 34 mm, from the top.
    assert set(rows.tolist()) == {(TOP - z) / 2 for z in (30, 32, 34)}
    assert (depths[False][rows, columns] == nearest + 2).all()


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.pydicom
def test_each_crossing_of_a_surface_is_found_in_order_from_the_viewer():
    # Two pieces along one ray of the frontal view, the second reaching
    # the end of the ray.
    inside = np.zeros((1, 12, 1), bool)
    inside[0, 2:4, 0] = True
    inside[0, 7:, 0] = True
    crossings = qc_surfaces.view_crossings(inside)
    frontal = crossings[0]
    # The ray through the voxels is the middle of 13, and its depths are
    # one more than the voxels' indices from anterior.
    assert frontal.shape == (4, 1, 13)
    assert frontal[:, 0, 6].tolist() == [3, 4, 8, 12]
    assert (np.delete(frontal, 6, axis=2) == -1).all()
    for each, first in zip(crossings, qc_surfaces.view_depths(inside)):
        assert (each[0] == first).all()


def test_the_profiles_show_the_nose_on_the_side_it_faces():
    nose = _views(_surface(_axial(_body(nose=True))))
    plain = _views(_surface(_axial(_body(nose=False))))
    middle = nose[0].shape[1] // 2

    # From the front, the nose is below the middle of the head, which is at
    # the top: it is centred on the row of z = 32 mm, row 23, not row 16.
    rows, columns = _changed(nose[0], plain[0])
    assert rows <= _rows(NOSE_Z - 5, NOSE_Z + 5)
    assert abs(np.mean(sorted(rows)) - (TOP - NOSE_Z) / 2) <= 1
    assert max(abs(column - middle) for column in columns) <= 6
    # Seen from the patient's left (+90), anterior is on the viewer's left;
    # from the patient's right (-90), on the viewer's right.
    _, left = _changed(nose[90], plain[90])
    _, right = _changed(nose[-90], plain[-90])
    assert max(left) < middle - 6 and min(right) > middle + 6
    # Each oblique shows it on the side of its profile.
    _, left = _changed(nose[45], plain[45])
    _, right = _changed(nose[-45], plain[-45])
    assert max(left) < middle < min(right)


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.pydicom
def test_the_frontal_view_shows_the_patients_left_on_the_viewers_right():
    ear = _views(_surface(_axial(_body(ear=True))))
    plain = _views(_surface(_axial(_body(ear=False))))
    middle = ear[0].shape[1] // 2

    # The ear is on the patient's left, at x = 59 to 69 mm.
    rows, columns = _changed(ear[0], plain[0])
    assert min(columns) > middle + 5
    assert rows <= _rows(EAR_Z - 5, EAR_Z + 5)
    # Seen from the patient's right, it is behind the head.
    assert (ear[-90] == plain[-90]).all()
    assert not (ear[90] == plain[90]).all()


@pytest.mark.pydicom
def test_how_a_volume_is_stored_does_not_change_its_render():
    body = _body(ear=True)

    renders = {_surface(each(body)) for each in (_axial, _flipped, _coronal)}

    assert len(renders) == 1


@pytest.mark.pydicom
@pytest.mark.parametrize("inside, rendered", [(-500, False), (-100, True)])
def test_a_ct_surface_is_at_minus_300_hounsfield_units(inside, rendered):
    data = _surface(_axial(_body(inside=inside)))

    assert _decoded(data).any() == rendered
    if rendered:
        assert data == _surface(_axial(_body()))


@pytest.mark.pydicom
def test_a_ct_surface_follows_the_rescale():
    # Stored values 1024 above Hounsfield units, as many scanners write them.
    written = {
        k: _with(data, RescaleSlope=1, RescaleIntercept=-1024)
        for k, data in _axial(_body(inside=1064, outside=24)).items()
    }

    assert _surface(written) == _surface(_axial(_body()))


@pytest.mark.pydicom
@pytest.mark.parametrize("modality", ["MR", "PT"])
def test_an_mr_or_pet_surface_is_at_otsus_threshold(modality):
    rng = np.random.default_rng(1)
    body = _body(inside=300, outside=0) + rng.integers(0, 6, (SIDE,) * 3)

    data = _surface(_axial(body, modality=modality))

    assert data == _surface(_axial(_body()))


@pytest.mark.pydicom
def test_padding_is_below_every_threshold():
    padded = {}
    for k, data in _axial(_body(outside=3000)).items():
        dataset = pydicom.dcmread(io.BytesIO(data))
        dataset.add_new(0x00280120, "SS", 3000)  # Pixel Padding Value
        padded[k] = _file(dataset)

    assert _surface(padded) == _surface(_axial(_body()))
    assert _surface(_axial(_body(outside=3000))) != _surface(_axial(_body()))


def _padded(body, modality, slope=1):
    """Axial slices of ``body`` with 0 as Pixel Padding Value."""
    padded = {}
    for k, data in _axial(body, modality=modality).items():
        dataset = pydicom.dcmread(io.BytesIO(data))
        dataset.add_new(0x00280120, "SS", 0)  # Pixel Padding Value
        dataset.RescaleSlope = slope
        dataset.RescaleIntercept = 0
        padded[k] = _file(dataset)
    return padded


@pytest.mark.pydicom
@pytest.mark.parametrize("modality", ["MR", "PT"])
@pytest.mark.parametrize("slope", [1, 1_000_000])
def test_padding_alone_outlines_an_mr_or_pet_surface(modality, slope):
    # Every value but the padding is one, and the padding outlines the head,
    # however large the value is once rescaled.
    data = _surface(_padded(_body(inside=300, outside=0), modality, slope))

    assert data == _surface(_axial(_body()))


@pytest.mark.pydicom
@pytest.mark.parametrize("modality", ["MR", "PT"])
def test_padding_joins_the_background_of_an_mr_or_pet_surface(modality):
    # Half the air is padded, and the rest is noise a little above it.
    rng = np.random.default_rng(2)
    body = _body(inside=300, outside=0) + rng.integers(1, 6, (SIDE,) * 3)
    z = np.arange(SIDE)[:, None, None]
    body = np.where((body < 300) & (z < SIDE // 2), 0, body)

    data = _surface(_padded(body, modality))

    assert data == _surface(_axial(_body()))


def _dose_body():
    """The head as dose: 1 Gy inside, at a scaling of 0.001, and 0 outside."""
    return _body(inside=1000, outside=0)


def _hot(peak):
    """The head as dose, with a hot spot of ``peak`` at its middle."""
    k, j, i = np.indices((SIDE,) * 3)
    return np.where((k == 20) & (j == 20) & (i == 20), peak, _dose_body())


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.pydicom
def test_an_rt_dose_grid_is_rendered_at_each_of_its_dose_levels():
    # The body's dose, 1 Gy, is the smallest above 0, and a hot spot of
    # 19 Gy is the greatest, so the levels above the support are 0.1, 0.2,
    # and 0.5 of it: 1.9, 3.8, and 9.5 Gy, as 0.05 of it is below 1 Gy.
    written = {0: _dose(_hot(19000), [2.0 * k for k in range(SIDE)])}

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_DOSE_LEVELS,
    ]
    levels = previews.previews[1]
    assert levels.frames == tuple((0, frame) for frame in range(SIDE))
    assert levels.total_frames == SIDE
    support, *higher = _levels(levels.png, 4)
    # The support is the head, as a CT render shows it, and each level above
    # it only the hot spot.
    assert np.array_equal(support, _decoded(_surface(_axial(_body()))))
    for row in higher:
        assert np.count_nonzero(_views(row)[0]) == 1


def test_dose_levels_run_from_the_support_to_half_the_greatest_dose():
    levels = qc_surfaces.dose_levels(1.0, 0.001)
    assert levels == pytest.approx((0.0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5))
    # No two neighbours, nor the lowest and the smallest dose, are more
    # than 2.5 apart, however small that is.
    for floor in (0.3, 1e-4, 3e-7, 2.0**-32):
        above = qc_surfaces.dose_levels(1.0, floor)[1:]
        assert above[-1] == pytest.approx(0.5)
        assert floor < above[0] <= 2.5 * floor
        assert all(b / a <= 2.5 + 1e-9 for a, b in zip(above, above[1:]))
    # A uniform dose, no dose, and a greatest dose that is not finite have
    # only the support.
    for peak, floor in ((1.0, 1.0), (0.0, math.inf), (-1.0, math.inf)):
        assert qc_surfaces.dose_levels(peak, floor) == (0.0,)
    assert qc_surfaces.dose_levels(math.inf, 1.0) == (0.0,)
    assert qc_surfaces.dose_levels(math.nan, 1.0) == (0.0,)


def test_a_plane_is_grey_by_the_levels_its_dose_reaches():
    levels = qc_surfaces.dose_levels(1.0, 0.001)
    values = np.array([[0.0, 0.001, 0.003, 0.3, 1.0, np.nan]], np.float32)
    # 9 levels: none, the support, then 0.002, then up to 0.2, then all.
    expected = np.rint(np.array([[0, 1, 2, 8, 9, 0]]) * 255 / 9)
    assert np.array_equal(qc_surfaces.level_bands(values, levels), expected)


def _envelope(nose, air=0):
    """Dose of 1 Gy in a ball in the head, 12 mGy in the rest of it, with
    or without its nose, and ``air`` mGy outside it."""
    k, j, i = np.indices((SIDE,) * 3)
    core = (k - 20) ** 2 + (j - 20) ** 2 + (i - 20) ** 2 <= 36
    return np.where(core, 1000, _body(nose=nose, inside=12, outside=air))


@pytest.mark.pydicom
@pytest.mark.parametrize("air", [0, 3], ids=["set-to-zero", "computed-in-air"])
def test_a_low_dose_envelope_shows_in_a_dose_level_below_5_percent(air):
    offsets = [2.0 * k for k in range(SIDE)]
    renders = {
        nose: _surface(
            {0: _dose(_envelope(nose, air), offsets)}, PreviewKind.SERIES_DOSE_LEVELS
        )
        for nose in (True, False)
    }
    # Above the support: 0.02 Gy up where air is set to zero, else from
    # 0.005 Gy, as the smallest dose is 0.003 Gy in air.
    levels = qc_surfaces.dose_levels(1.0, 0.012 if air == 0 else 0.003)
    rows = {nose: _levels(png, len(levels)) for nose, png in renders.items()}
    changed = [
        level
        for level, with_nose, without in zip(levels, rows[True], rows[False])
        if not np.array_equal(with_nose, without)
    ]
    # The nose, at 12 mGy, is in the support where air is set to zero, and
    # in the levels of 5 and 10 mGy where air has 3 mGy; never in the 5%
    # level.
    assert changed == pytest.approx([0.0] if air == 0 else [0.005, 0.01])
    assert any(level == pytest.approx(0.05) for level in levels)


@pytest.mark.pydicom
def test_a_series_of_dose_planes_is_rendered_by_each_plane_s_own_scaling():
    grid = _hot(19000)
    offsets = [2.0 * k for k in range(SIDE)]
    # Odd planes store half the value at twice the scaling.
    planes = {
        k: _dose(
            grid[k : k + 1] // (2 if k % 2 else 1),
            None,
            origin=(0.0, 0.0, 2.0 * k),
            scaling=0.002 if k % 2 else 0.001,
            instance=f"2.25.9101.{k + 1}",
        )
        for k in range(SIDE)
    }
    previews = qc_previews.previews_of(planes, ())
    kinds = [preview.kind for preview in previews.previews]
    assert PreviewKind.SERIES_DOSE_LEVELS in kinds
    assert PreviewKind.SERIES_SURFACE not in kinds
    assert _surface(planes, PreviewKind.SERIES_DOSE_LEVELS) == _surface(
        {0: _dose(grid, offsets)}, PreviewKind.SERIES_DOSE_LEVELS
    )


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "case",
    ["absolute offsets", "descending offsets", "two frames"],
)
def test_an_rt_dose_grid_described_otherwise_is_rendered_alike(case):
    grid = _dose_body()
    offsets = [2.0 * k for k in range(SIDE)]
    kwargs = {}
    if case == "absolute offsets":
        # The first offset need only be within 0.01 mm of the origin's z.
        kwargs["origin"] = (0.0, 0.0, 10.004)
        offsets = [10.0 + offset for offset in offsets]
    elif case == "descending offsets":
        grid, offsets = grid[::-1], [-offset for offset in offsets]
        kwargs["origin"] = (0.0, 0.0, TOP)
    elif case == "two frames":
        grid, offsets = grid[19:21], [0.0, 2.0]

    # A uniform dose has only its support.
    data = _surface({0: _dose(grid, offsets, **kwargs)}, PreviewKind.SERIES_DOSE_LEVELS)

    if case == "two frames":
        assert _views(data)[0].shape[0] == 2 and _decoded(data).any()
    else:
        assert data == _surface(_axial(_body()))


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "case",
    [
        "oblique",
        "uneven offsets",
        "no offsets",
        "absolute offsets off the origin",
        "absolute offsets of a coronal grid",
        "no scaling",
        "zero scaling",
        "negative scaling",
        "signed",
    ],
)
def test_an_rt_dose_grid_that_cannot_be_placed_or_levelled_is_not_rendered(case):
    grid = _dose_body()[:4]
    offsets = [0.0, 2.0, 4.0, 6.0]
    kwargs = {}
    if case == "oblique":
        angle = math.radians(30)
        cosine, sine = round(math.cos(angle), 6), round(math.sin(angle), 6)
        kwargs["orientation"] = (cosine, sine, 0.0, -sine, cosine, 0.0)
    elif case == "uneven offsets":
        offsets = [0.0, 2.0, 4.0, 7.0]
    elif case == "no offsets":
        offsets = None
    elif case == "absolute offsets off the origin":
        offsets = [10.0, 12.0, 14.0, 16.0]
    elif case == "absolute offsets of a coronal grid":
        kwargs["orientation"] = CORONAL
        kwargs["origin"] = (0.0, 0.0, 10.0)
        offsets = [10.0, 12.0, 14.0, 16.0]
    elif case == "no scaling":
        kwargs["scaling"] = None
    elif case == "zero scaling":
        kwargs["scaling"] = 0.0
    elif case == "negative scaling":
        kwargs["scaling"] = -0.001
    data = _dose(grid, offsets, **kwargs)
    if case == "signed":
        data = _with(data, PixelRepresentation=1)

    previews = qc_previews.previews_of({0: data}, ())

    assert [preview.kind for preview in previews.previews] == [PreviewKind.SERIES_CINE]
    assert not previews.not_previewed


@pytest.mark.pydicom
def test_a_grid_of_no_dose_has_only_its_empty_support():
    data = _surface(
        {0: _dose(np.zeros((4, SIDE, SIDE)), [0.0, 2.0, 4.0, 6.0])},
        PreviewKind.SERIES_DOSE_LEVELS,
    )
    (support,) = _levels(data, 1)
    # Its four frames are its height, from superior.
    assert support.shape[0] == 4 and not support.any()


@pytest.mark.pydicom
def test_a_lone_dose_plane_is_mapped_by_its_dose_levels():
    plane = _hot(19000)[20:21]
    previews = qc_previews.previews_of({0: _dose(plane, [0.0])}, ())
    assert [preview.kind for preview in previews.previews] == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_DOSE_LEVELS,
    ]
    mapped = previews.previews[1]
    assert mapped.frames == ((0, 0),) and mapped.total_frames == 1
    values = plane[0].astype(np.float32) * np.float32(0.001)
    expected = qc_surfaces.level_bands(values, qc_surfaces.dose_levels(19.0, 1.0))
    assert np.array_equal(_decoded(mapped.png), expected)


def _sheet_rows(data):
    """Each row of a dose-levels render whose rows are all of the grid's
    height, as an image."""
    gap = qc_surfaces._GAP_PIXELS  # pylint: disable = protected-access
    return _levels(data, (_decoded(data).shape[0] + gap) // (SIDE + gap))


@pytest.mark.pydicom
def test_a_lower_dose_enclosed_by_a_higher_one_shows_in_rows_of_hidden_surfaces():
    # The head, with or without its nose, at 12 mGy, inside 1 Gy all around
    # it. Each level above 12 mGy is a box with the head as its cavity, so
    # every ray of every view meets the box first, and the head shows only
    # in the rows of the surfaces that the box hides.
    offsets = [2.0 * k for k in range(SIDE)]
    rows = {
        nose: _sheet_rows(
            _surface(
                {0: _dose(_body(nose=nose, inside=12, outside=1000), offsets)},
                PreviewKind.SERIES_DOSE_LEVELS,
            )
        )
        for nose in (True, False)
    }
    levels = qc_surfaces.dose_levels(1.0, 0.012)
    assert len(rows[True]) > len(levels)
    # The support, the whole box, hides nothing, and is the same either way.
    assert np.array_equal(rows[True][0], rows[False][0])
    assert any(
        not np.array_equal(with_nose, without)
        for with_nose, without in zip(rows[True][1:], rows[False][1:])
    )


def test_hidden_rows_show_a_cavity_and_each_further_crossing():
    k, j, i = np.indices((SIDE,) * 3)
    distance = (k - 20) ** 2 + (j - 20) ** 2 + (i - 20) ** 2
    ball, cavity = distance <= 225, distance <= 64
    assert not qc_surfaces.hidden_rows(ball)
    rows = qc_surfaces.hidden_rows(ball & ~cavity)
    # Its cavity, then where rays through it leave the shell, enter the
    # cavity's far side, and leave the shell again.
    assert len(rows) == 4
    assert np.array_equal(rows[0], qc_surfaces.side_by_side(qc_surfaces.views(cavity)))
    # In the frontal view, every ray through the shell leaves it, and only
    # those through the cavity enter it again.
    assert np.array_equal(
        _views(rows[1])[0] > 0,
        _views(qc_surfaces.side_by_side(qc_surfaces.views(ball)))[0] > 0,
    )
    assert np.array_equal(_views(rows[2])[0] > 0, _views(rows[0])[0] > 0)
    # The oblique views are black in the rows of crossings.
    for row in rows[1:]:
        assert not _views(row)[45].any() and not _views(row)[-45].any()


@pytest.mark.pydicom
@pytest.mark.parametrize("scaling", [1e-46, 1e-42, 1e39])
@pytest.mark.parametrize("shape", ["grid", "plane"])
def test_a_dose_that_its_scaling_would_lose_is_not_shown(shape, scaling):
    # Float32 takes the scaled dose to 0, below a normal float32, or to
    # infinity, so no level would show what it holds.
    grid = _hot(19000)
    data = (
        _dose(grid[18:22], [0.0, 2.0, 4.0, 6.0], scaling=scaling)
        if shape == "grid"
        else _dose(grid[20:21], [0.0], scaling=scaling)
    )

    previews = qc_previews.previews_of({0: data}, ())

    assert [preview.kind for preview in previews.previews] == [PreviewKind.SERIES_CINE]


@pytest.mark.pydicom
def test_a_scaling_that_float32_holds_or_a_grid_of_no_dose_is_shown():
    offsets = [2.0 * k for k in range(SIDE)]
    # Levels are fractions of the greatest dose, so a scaling far from 1
    # that float32 holds draws the same sheet.
    assert _surface(
        {0: _dose(_hot(19000), offsets, scaling=1e-30)},
        PreviewKind.SERIES_DOSE_LEVELS,
    ) == _surface({0: _dose(_hot(19000), offsets)}, PreviewKind.SERIES_DOSE_LEVELS)
    # A grid of no dose loses none at any scaling.
    (support,) = _levels(
        _surface(
            {0: _dose(np.zeros((4, SIDE, SIDE)), [0.0, 2.0, 4.0, 6.0], scaling=1e-46)},
            PreviewKind.SERIES_DOSE_LEVELS,
        ),
        1,
    )
    assert not support.any()


@pytest.mark.pydicom
def test_a_dose_sheet_taller_than_its_bound_is_not_shown(monkeypatch):
    # Four rows of the grid's 40 voxels, with three gaps between them.
    written = {0: _dose(_hot(19000), [2.0 * k for k in range(SIDE)])}
    gap = qc_surfaces._GAP_PIXELS  # pylint: disable = protected-access
    height = 4 * SIDE + 3 * gap
    monkeypatch.setattr(qc_surfaces, "MAXIMUM_DOSE_SHEET_PIXELS", height)
    assert _decoded(_surface(written, PreviewKind.SERIES_DOSE_LEVELS)).shape[0] == (
        height
    )
    monkeypatch.setattr(qc_surfaces, "MAXIMUM_DOSE_SHEET_PIXELS", height - 1)
    previews = qc_previews.previews_of(written, ())
    assert [preview.kind for preview in previews.previews] == [PreviewKind.SERIES_CINE]


@pytest.mark.pydicom
def test_each_frame_is_decoded_once(monkeypatch):
    decode = pydicom.pixels.pixel_array
    calls = []

    def counted(source, **kwargs):
        calls.append(kwargs.get("index"))
        return decode(source, **kwargs)

    monkeypatch.setattr(pydicom.pixels, "pixel_array", counted)

    qc_previews.previews_of(
        {0: _dose(_dose_body(), [2.0 * k for k in range(SIDE)])}, ()
    )
    assert sorted(calls) == list(range(SIDE))
    calls.clear()
    qc_previews.previews_of(_axial(_body()), ())
    assert calls == [0] * SIDE


@pytest.mark.pydicom
def test_the_same_files_give_the_same_render():
    assert _surface(_axial(_body(ear=True))) == _surface(_axial(_body(ear=True)))


def test_a_long_volume_is_sampled_at_2_mm():
    directions = (np.array([0, 0, 1.0]), np.array([0, 1.0, 0]), np.array([1.0, 0, 0]))
    surface = qc_surfaces.Surface(
        qc_surfaces.grid(
            directions,
            [0.0, 1.0, 1000.0],
            (0.5, 0.5),
            (600, 4),
            qc_surfaces.Threshold.CT,
        )
    )
    for _ in range(3):
        surface.add(np.zeros((600, 4), np.float32))

    mask = surface.mask()

    # 1,000 mm along z, 299.5 mm along y, and 1.5 mm along x, at 2 mm, where
    # 256 voxels a side would have sampled it at about 3.9 mm.
    assert mask is not None and mask.shape == (501, 150, 1)
    assert mask.all()
    image = surface.image()
    assert image is not None and image.dtype == np.uint8
    assert image.shape[0] == 501


def _box_grid(extents, threshold=qc_surfaces.Threshold.CT):
    """An axial grid of two slices, rows, and columns, whose extents along
    x, y, and z are as given."""
    x, y, z = extents
    directions = (np.array([0, 0, 1.0]), np.array([0, 1.0, 0]), np.array([1.0, 0, 0]))
    return qc_surfaces.grid(directions, [0.0, z], (y, x), (2, 2), threshold)


@pytest.mark.parametrize(
    "extents, rendered",
    [
        ((qc_surfaces.WIDEST, qc_surfaces.WIDEST, qc_surfaces.LONGEST), True),
        ((qc_surfaces.WIDEST + 0.5, 10.0, 10.0), False),
        ((10.0, qc_surfaces.WIDEST + 0.5, 10.0), False),
        ((10.0, 10.0, qc_surfaces.LONGEST + 0.5), False),
    ],
    ids=["at-the-bounds", "wide-across", "deep-front-to-back", "long"],
)
@pytest.mark.parametrize(
    "threshold", [qc_surfaces.Threshold.CT, qc_surfaces.Threshold.DOSE]
)
def test_a_volume_too_long_or_too_wide_is_not_rendered(extents, rendered, threshold):
    surface = qc_surfaces.Surface(_box_grid(extents, threshold))
    for _ in range(2):
        surface.add(np.ones((2, 2), np.float32))

    assert (surface.mask() is not None) is rendered
    assert (surface.image() is not None) is rendered
    if not rendered:
        # Nothing of it is sampled, however large it is.
        assert not surface._samples.size  # pylint: disable = protected-access


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.pydicom
def test_the_view_from_behind_shows_the_patients_left_on_the_viewers_left():
    ear = _views(_surface(_axial(_body(nose=False, ear=True))))
    plain = _views(_surface(_axial(_body(nose=False))))
    middle = ear[0].shape[1] // 2

    # The head and its ear are symmetric from front to back, so from behind
    # they are seen as from the front, mirrored.
    assert (ear[180] == ear[0][:, ::-1]).all()
    _, columns = _changed(ear[180], plain[180])
    assert max(columns) < middle - 5
    # The nose, in front, is hidden from behind.
    nose = _views(_surface(_axial(_body(nose=True))))
    assert (nose[180] == plain[180]).all()


def test_only_the_view_from_behind_and_the_profiles_show_a_bump_on_the_back():
    inside = np.zeros((9, 21, 21), bool)
    inside[:, 5:16, 5:16] = True
    bumped = inside.copy()
    # Rows run towards posterior.
    bumped[3:6, 16:18, 9:12] = True

    changed = {
        view: not (plain == bump).all()
        for view, plain, bump in zip(
            qc_surfaces.VIEWS, qc_surfaces.views(inside), qc_surfaces.views(bumped)
        )
    }

    assert changed == {0: False, 45: False, -45: False, 90: True, -90: True, 180: True}


def test_views_and_crossings_are_the_same_however_many_slices_are_rendered_at_once(
    monkeypatch,
):
    rng = np.random.default_rng(3)
    inside = rng.random((10, 15, 13)) < 0.4
    views = qc_surfaces.views(inside)
    crossings = qc_surfaces.view_crossings(inside)

    for count in (1, 3, 10**6):
        monkeypatch.setattr(qc_surfaces, "_SLICES_AT_A_TIME", count)
        assert all((a == b).all() for a, b in zip(qc_surfaces.views(inside), views))
        again = qc_surfaces.view_crossings(inside)
        assert all(
            a.dtype == np.int16 and a.shape == b.shape and (a == b).all()
            for a, b in zip(again, crossings)
        )


def test_hidden_rows_that_would_not_fit_are_not_drawn_nor_their_crossings_found(
    monkeypatch,
):
    # Ten nested square rings in a slice, so a ray crosses 20 times.
    inside = np.zeros((3, 44, 44), bool)
    for ring in range(10):
        inside[1, 2 * ring : 44 - 2 * ring, 2 * ring : 44 - 2 * ring] = ring % 2 == 0
    gap = qc_surfaces._GAP_PIXELS  # pylint: disable = protected-access
    # A row for each crossing after the first, as the room counts them.
    needed = 19 * (len(inside) + gap)
    rows = qc_surfaces.hidden_rows(inside, room=needed)
    # And a row of its cavities, which the room does not count.
    assert rows is not None and len(rows) == 1 + 19

    def found(*_):
        raise AssertionError("crossings found")

    monkeypatch.setattr(qc_surfaces, "_crossings", found)
    monkeypatch.setattr(qc_surfaces, "views", found)
    assert qc_surfaces.hidden_rows(inside, room=needed - 1) is None


def test_a_render_needs_every_slice():
    directions = (np.array([0, 0, 1.0]), np.array([0, 1.0, 0]), np.array([1.0, 0, 0]))
    surface = qc_surfaces.Surface(
        qc_surfaces.grid(
            directions, [0.0, 2.0, 4.0], (2.0, 2.0), (3, 3), qc_surfaces.Threshold.OTSU
        )
    )
    surface.add(np.zeros((3, 3), np.float32))

    assert surface.mask() is None and surface.image() is None
