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
):
    """An RT Dose instance; grid is (frames, rows, columns) of stored values."""
    grid = np.asarray(grid)
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = RT_DOSE_STORAGE
    dataset.SOPInstanceUID = "2.25.9101"
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


def _surface(written):
    """The PNG of the only surface render of the files."""
    previews = qc_previews.previews_of(written, ())
    surfaces = [p for p in previews.previews if p.kind is PreviewKind.SERIES_SURFACE]
    assert len(surfaces) == 1
    return surfaces[0].png


def _views(data):
    """Each view of a surface render, in the order of qc_surfaces.VIEWS."""
    image = _decoded(data)
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
def test_an_rt_dose_grid_is_rendered_at_5_percent_of_its_maximum():
    # A hot spot raises the maximum, but not past 20 times the body's dose.
    written = {0: _dose(_hot(19000), [2.0 * k for k in range(SIDE)])}

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_SURFACE,
    ]
    surface = previews.previews[1]
    assert surface.frames == tuple((0, frame) for frame in range(SIDE))
    assert surface.total_frames == SIDE
    assert surface.png == _surface(_axial(_body()))
    # Past it, only the hot spot is rendered.
    hot = _views(_surface({0: _dose(_hot(21000), [2.0 * k for k in range(SIDE)])}))
    assert np.count_nonzero(hot[0]) == 1


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "case",
    ["absolute offsets", "descending offsets", "no scaling", "two frames"],
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
    elif case == "no scaling":
        kwargs["scaling"] = None
    elif case == "two frames":
        grid, offsets = grid[19:21], [0.0, 2.0]

    data = _surface({0: _dose(grid, offsets, **kwargs)})

    if case == "two frames":
        assert _views(data)[0].shape[0] == 2 and _decoded(data).any()
    else:
        assert data == _surface(_axial(_body()))


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "case",
    [
        "one frame",
        "oblique",
        "uneven offsets",
        "no offsets",
        "absolute offsets off the origin",
        "absolute offsets of a coronal grid",
    ],
)
def test_an_rt_dose_grid_that_cannot_be_placed_is_not_rendered(case):
    grid = _dose_body()[:4]
    offsets = [0.0, 2.0, 4.0, 6.0]
    kwargs = {}
    if case == "one frame":
        grid, offsets = grid[:1], [0.0]
    elif case == "oblique":
        angle = math.radians(30)
        cosine, sine = round(math.cos(angle), 6), round(math.sin(angle), 6)
        kwargs["orientation"] = (cosine, sine, 0.0, -sine, cosine, 0.0)
    elif case == "uneven offsets":
        offsets = [0.0, 2.0, 4.0, 7.0]
    elif case == "no offsets":
        offsets = None
    elif case == "absolute offsets off the origin":
        offsets = [10.0, 12.0, 14.0, 16.0]
    else:
        kwargs["orientation"] = CORONAL
        kwargs["origin"] = (0.0, 0.0, 10.0)
        offsets = [10.0, 12.0, 14.0, 16.0]

    previews = qc_previews.previews_of({0: _dose(grid, offsets, **kwargs)}, ())

    assert [preview.kind for preview in previews.previews] == [PreviewKind.SERIES_CINE]
    assert not previews.not_previewed


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


def test_a_long_volume_is_sampled_to_at_most_the_maximum_voxels():
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

    assert mask is not None
    assert max(mask.shape) == qc_surfaces.MAXIMUM_VOXELS
    assert mask.all()
    image = surface.image()
    assert image is not None and image.dtype == np.uint8


def test_a_render_needs_every_slice():
    directions = (np.array([0, 0, 1.0]), np.array([0, 1.0, 0]), np.array([1.0, 0, 0]))
    surface = qc_surfaces.Surface(
        qc_surfaces.grid(
            directions, [0.0, 2.0, 4.0], (2.0, 2.0), (3, 3), qc_surfaces.Threshold.OTSU
        )
    )
    surface.add(np.zeros((3, 3), np.float32))

    assert surface.mask() is None and surface.image() is None
