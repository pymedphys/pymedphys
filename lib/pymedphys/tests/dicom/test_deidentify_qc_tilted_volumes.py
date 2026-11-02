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

"""Tests of the QC pack's projection and surface renders of stacks whose
axes do not lie along the patient's: with a gantry tilt, sheared, or
oblique, sampled by :mod:`~pymedphys._dicom.deidentify.stack_sampling`.

Every image is synthetic: small stacks of random or coded values, and the
analytic head of :mod:`._synthetic_head`.
"""

import dataclasses
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_previews, qc_surfaces, stack_sampling
from pymedphys._dicom.deidentify.qc_pack import PreviewKind

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_qc_previews import _decoded, _image
from .test_deidentify_qc_surfaces import SIDE, _dose, _hot


def _rotation(about_x: float = 0.0, about_y: float = 0.0, about_z: float = 0.0):
    """The rotation by these degrees about x, then y, then z."""
    a, b, c = (math.radians(angle) for angle in (about_x, about_y, about_z))
    x = np.array(
        [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
    )
    y = np.array(
        [[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]]
    )
    z = np.array(
        [[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]]
    )
    return z @ y @ x


def _orientation(rotation: np.ndarray, flip=(1.0, 1.0)):
    along_row = flip[0] * rotation @ np.array([1.0, 0.0, 0.0])
    down_column = flip[1] * rotation @ np.array([0.0, 1.0, 0.0])
    return tuple(float(value) for value in (*along_row, *down_column))


def _stack(
    orientation, steps, along=(0.0, 0.0, 1.0), spacing=(1.3, 0.9), shape=(9, 11)
):
    """A stack whose slices' first pixels lie at ``steps`` along ``along``."""
    positions = [
        tuple(float(value) for value in step * np.array(along)) for step in steps
    ]
    return stack_sampling.Stack(orientation, positions, spacing, shape)


_STEPS = tuple(2.1 * k for k in range(8))
_THIN = tuple(0.5 * k for k in range(14))

# Stacks whose axes lie along the patient's, with slices along the normal,
# which a grid also places: head first supine, feet first supine, head
# first prone, coronal, and sagittal, and slices closer than the voxels.
_ALIGNED = {
    "axial": ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0), _STEPS),
    "feet-first": ((-1.0, 0.0, 0.0, 0.0, 1.0, 0.0), tuple(-s for s in _STEPS)),
    "prone": ((-1.0, 0.0, 0.0, 0.0, -1.0, 0.0), _STEPS),
    "coronal": ((1.0, 0.0, 0.0, 0.0, 0.0, -1.0), _STEPS),
    "sagittal": ((0.0, 1.0, 0.0, 0.0, 0.0, -1.0), _STEPS),
    "thin-axial": ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0), _THIN),
}

_TILT_15 = _orientation(_rotation(about_x=-15.0))

# Stacks whose axes do not lie along the patient's.
_OBLIQUE = {
    "gantry-tilt-15": _stack(_TILT_15, _STEPS),
    "gantry-tilt-15-thin": _stack(_TILT_15, _THIN),
    "sheared": _stack(
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        _STEPS,
        along=(0.0, -math.tan(math.radians(15.0)), 1.0),
    ),
    "oblique-about-z": _stack(_orientation(_rotation(about_z=10.0)), _STEPS),
    "compound-oblique": _stack(
        _orientation(_rotation(about_x=25.0, about_y=-35.0, about_z=50.0)),
        _STEPS,
        along=_rotation(about_x=25.0, about_y=-35.0, about_z=50.0)
        @ np.array([0.2, -0.1, 1.0]),
    ),
}


def _frames(count, shape, seed, padded=False, dose=False):
    """Random slices: Hounsfield-like values, or stored doses of 0 to 2000,
    with about a tenth NaN, as padding, where ``padded``."""
    generator = np.random.default_rng(seed)
    frames = []
    for _ in range(count):
        if dose:
            frame = generator.integers(0, 2000, shape).astype(np.float32)
        else:
            frame = generator.normal(-300.0, 500.0, shape).astype(np.float32)
        if padded:
            frame[generator.random(shape) < 0.1] = np.nan
        frames.append(frame)
    return frames


def _rendered(surface, frames, scale=None, order=None):
    for index in range(len(frames)) if order is None else order:
        surface.add(frames[index], scale, index)
    return surface


# The stacked surface is the grid's where a grid can place the volume.


@pytest.mark.parametrize(
    "threshold, padded",
    [
        (qc_surfaces.Threshold.CT, False),
        (qc_surfaces.Threshold.OTSU, True),
        (qc_surfaces.Threshold.DOSE, False),
    ],
)
@pytest.mark.parametrize("name", list(_ALIGNED))
def test_a_stacked_surface_along_the_patient_axes_is_the_grids(name, threshold, padded):
    orientation, steps = _ALIGNED[name]
    normal = _normal(orientation)
    # In order along the normal, as a volume's slices are.
    offsets = sorted(steps)
    stack = _stack(orientation, offsets, along=normal)
    dose = threshold is qc_surfaces.Threshold.DOSE
    scale = 0.001 if dose else 1.0
    frames = _frames(len(steps), stack.shape, seed=7, padded=padded, dose=dose)
    grid = qc_surfaces.grid(
        (normal, np.array(orientation[3:]), np.array(orientation[:3])),
        offsets,
        stack.spacing,
        stack.shape,
        threshold,
        scale,
    )

    expected = _rendered(qc_surfaces.Surface(grid), frames)
    stacked = _rendered(
        qc_surfaces.Surface(qc_surfaces.Stacked(stack, threshold, scale)),
        frames,
        order=list(reversed(range(len(frames)))),
    )

    assert stacked.levels == expected.levels
    assert np.array_equal(stacked.mask(), expected.mask())
    assert np.array_equal(stacked.image(), expected.image())
    lattice = stacked.lattice
    assert lattice is not None and expected.lattice is None
    # The lattice's voxels are the grid's: its coordinates are those of the
    # pixels that the grid samples, where those lie on the voxels' centres.
    zs, ys, xs = lattice.coordinates
    assert (len(zs), len(ys), len(xs)) == expected.mask().shape


def _normal(orientation):
    return np.cross(orientation[:3], orientation[3:])


def test_a_stacked_surface_scales_each_slice_by_its_own_scale():
    stack = _OBLIQUE["gantry-tilt-15"]
    frames = _frames(len(stack.offsets), stack.shape, seed=3, dose=True)
    scales = [0.001 * (k + 1) for k in range(len(frames))]
    # As the surface scales each, to doses that float32 holds.
    scaled = [qc_surfaces.dose_values(frame, s) for frame, s in zip(frames, scales)]

    own = qc_surfaces.Surface(
        qc_surfaces.Stacked(stack, qc_surfaces.Threshold.DOSE, 1.0)
    )
    for index, (frame, s) in enumerate(zip(frames, scales)):
        own.add(frame, s, index)
    expected = _rendered(
        qc_surfaces.Surface(qc_surfaces.Stacked(stack, qc_surfaces.Threshold.DOSE)),
        scaled,
        scale=1.0,
    )

    assert own.levels == expected.levels
    assert np.array_equal(own.image(), expected.image())


# A lattice cut into slabs is sampled as a whole.


@pytest.mark.parametrize("most", [1, 37, 400])
@pytest.mark.parametrize("name", list(_OBLIQUE))
def test_slabs_sample_each_voxel_as_one_sampler_of_the_lattice(name, most):
    stack = _OBLIQUE[name]
    lattice = stack.lattice(0.7)
    whole = stack_sampling.StackSampler(stack, lattice)
    slabs = qc_surfaces.Slabs(stack, lattice, most)
    assert len(slabs.samplers) > 1
    # Each slab holds at most ``most`` voxels where a slab of one layer does.
    layer = math.prod(lattice.shape) // lattice.shape[slabs.axis]
    assert all(
        math.prod(sampler.lattice.shape) <= max(most, layer)
        for sampler in slabs.samplers
    )

    for index in range(len(stack.offsets)):
        expected = set()
        for found in (whole.nearest(index), whole.crossed(index)):
            expected.update(zip(found.voxels, found.rows, found.columns))
        taken = set()
        for placed in slabs.taken(index):
            voxels = np.ravel_multi_index(placed.indices, lattice.shape)
            taken.update(zip(voxels, placed.rows, placed.columns))
        assert taken == expected


@pytest.mark.parametrize("name", list(_OBLIQUE))
def test_a_surface_is_the_same_however_its_lattice_is_cut(name, monkeypatch):
    stack = _OBLIQUE[name]
    frames = _frames(len(stack.offsets), stack.shape, seed=11, padded=True)

    def rendered():
        surface = qc_surfaces.Surface(
            qc_surfaces.Stacked(stack, qc_surfaces.Threshold.OTSU)
        )
        return _rendered(surface, frames)

    whole = rendered()
    monkeypatch.setattr(qc_surfaces, "SLAB_VOXELS", 50)
    cut = rendered()

    assert cut._slabs is not None and len(cut._slabs.samplers) > 1  # pylint: disable = protected-access
    assert np.array_equal(cut.mask(), whole.mask())
    assert np.array_equal(cut.image(), whole.image())


# A tilted or oblique head is rendered as it lies.

_TALL = ((-100, 100), (-130, 110), (-160, 200))
_DEEP = ((-100, 100), (-130, 180), (-120, 120))


def _turned(scan: head.Scan, rotation: np.ndarray) -> head.Scan:
    """``scan`` with its rows, columns, and slices turned about its middle."""
    along_row = rotation @ np.array(scan.orientation[:3])
    down_column = rotation @ np.array(scan.orientation[3:])
    middle = np.mean(
        [scan.points(0)[0, 0], scan.points(len(scan.positions) - 1)[-1, -1]], axis=0
    )
    positions = tuple(
        tuple(float(v) for v in middle + rotation @ (np.array(p) - middle))
        for p in scan.positions
    )
    orientation = tuple(float(value) for value in (*along_row, *down_column))
    return dataclasses.replace(scan, orientation=orientation, positions=positions)


def _sheared(scan: head.Scan, degrees: float) -> head.Scan:
    """An axial ``scan``, each slice offset anteriorly from the last by its
    step times the tangent of ``degrees``, as a gantry tilt is recorded
    with axial direction cosines."""
    slope = math.tan(math.radians(degrees))
    positions = tuple(
        (x, y - (z - scan.positions[0][2]) * slope, z) for x, y, z in scan.positions
    )
    return dataclasses.replace(scan, positions=positions)


# Pixels of 1 mm, and slices 2.5 mm apart along the table, as Tilt-T1's
# tests sample them.
_HEADS = {
    "gantry-tilt-half-degree": head.tilted(degrees=0.5),
    "gantry-tilt-15": head.tilted(degrees=15.0, extent=_TALL),
    "gantry-tilt-30": head.tilted(degrees=30.0, extent=_TALL),
    "gantry-tilt-15-sheared": _sheared(head.axial(extent=_DEEP), 15.0),
    "oblique-about-z-10": _turned(head.axial(), _rotation(about_z=10.0)),
    "compound-oblique": _turned(head.axial(), _rotation(about_x=12.0, about_y=-8.0)),
}


def _stacked_surface(scan: head.Scan, anatomy: head.Head) -> qc_surfaces.Surface:
    stack = stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    surface = qc_surfaces.Surface(qc_surfaces.Stacked(stack, qc_surfaces.Threshold.CT))
    return _rendered(surface, list(scan.slices(anatomy)))


def _misdrawn(scan: head.Scan) -> tuple[float, np.ndarray]:
    """The share of voxels that a stack covers whose surface mask differs
    from the head's at their centres, and the mask near the eyes."""
    anatomy = head.Head(noise=0.0)
    surface = _stacked_surface(scan, anatomy)
    inside = surface.mask()
    lattice = surface.lattice
    assert inside is not None and lattice is not None
    stack = stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    covered = stack_sampling.SampledVolume(stack_sampling.StackSampler(stack, lattice))
    for index in range(len(scan.positions)):
        covered.add(np.ones(scan.shape), index)
    within = ~np.isnan(covered.values)
    centres = lattice.points(np.indices(lattice.shape))
    truth = head.hounsfield(centres, anatomy) >= qc_surfaces.CT_THRESHOLD
    differs = (inside != truth)[within]
    near_the_eyes = (
        (np.abs(centres[..., 0]) < head.GLOBE_X + 25)
        & (np.abs(centres[..., 1] - head.GLOBE_Y) < 25)
        & (np.abs(centres[..., 2] - head.GLOBE_Z) < 25)
    )
    return float(differs.mean()), within[near_the_eyes]


@pytest.mark.parametrize("scan", _HEADS.values(), ids=_HEADS.keys())
def test_a_tilted_or_oblique_heads_surface_is_the_head_as_it_lies(scan):
    differs, near_the_eyes = _misdrawn(scan)

    # The face is within the stack, and nearest neighbour moves each edge
    # by up to half a slice along the normal and half a pixel within it,
    # whatever the tilt, so the surface of a tilted head is no further from
    # the head as it lies than the untilted head's.
    assert near_the_eyes.all()
    untilted, _ = _misdrawn(head.axial())
    assert 0 < untilted < 0.02
    assert differs < 2 * untilted


@pytest.mark.pydicom
def test_a_gantry_tilted_head_ct_is_projected_and_rendered_whole():
    scan = head.tilted(degrees=15.0, extent=_TALL, spacing=2.0)
    written = dict(enumerate(files.ct_files(scan, head.Head(noise=0.0))))

    previews = qc_previews.previews_of(written, ())

    assert [preview.kind for preview in previews.previews] == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
    ]
    every = tuple((position, 0) for position in written)
    _, mip, surface = previews.previews
    assert mip.frames == every and surface.frames == every
    assert previews.pixels_shown == frozenset(written)
    assert not previews.not_previewed
    # The render is the head's surface sampled from the files as written.
    expected = _stacked_surface(scan, head.Head(noise=0.0)).image()
    assert np.array_equal(_decoded(surface.png), expected)


# The projection's orientation, and every slice drawn.


def _marked(column):
    """A stack tilted by 15 degrees of air, with a bright pixel in the
    highest slice's middle row, at ``column``: 0 at the patient's right."""
    orientation = tuple(round(value, 6) for value in _TILT_15)
    written = {}
    for k in range(10):
        pixels = np.full((20, 20), -1000.0)
        if k == 9:
            pixels[10, column] = 1000.0
        written[k] = _image(
            pixels,
            number=k + 1,
            origin=(0.0, 0.0, 5.0 * k),
            orientation=orientation,
            spacing=(2.0, 2.0),
        )
    return written


@pytest.mark.pydicom
@pytest.mark.parametrize("column", [0, 19])
def test_a_tilted_projection_has_the_head_up_and_the_right_on_the_left(column):
    previews = qc_previews.previews_of(_marked(column), ())
    (mip,) = [p for p in previews.previews if p.kind is PreviewKind.SERIES_MIP]
    image = _decoded(mip.png)

    rows, columns = np.nonzero(image == image.max())
    # The pixel lies 10 rows of 2 mm down its tilted column from the top
    # slice, at 45 mm, so about 5 mm below the top of the stack, whose
    # lowest pixel is about 10 mm below the lowest slice.
    assert image.max() == 255
    assert rows.max() < image.shape[0] // 4
    if column == 0:
        assert columns.max() < image.shape[1] // 4
    else:
        assert columns.min() >= 3 * image.shape[1] // 4


def _thin_stack(bright):
    """30 tilted slices 0.4 mm apart along the table, of air but for a
    pixel of soft tissue in slice ``bright``."""
    orientation = tuple(round(value, 6) for value in _TILT_15)
    written = {}
    for k in range(30):
        pixels = np.full((8, 8), -1000.0)
        if k == bright:
            pixels[4, 4] = 40.0
        written[k] = _image(
            pixels,
            number=k + 1,
            origin=(0.0, 0.0, round(0.4 * k, 6)),
            orientation=orientation,
            spacing=(1.0, 1.0),
        )
    return written


@pytest.mark.pydicom
def test_every_tilted_slice_is_drawn_where_slices_are_closer_than_the_voxels():
    # The surface's voxels are 2 mm, so some slices are nearest no voxel's
    # centre, and each is drawn only by the voxels that it crosses.
    orientation = tuple(round(value, 6) for value in _TILT_15)
    stack = stack_sampling.Stack(
        orientation,
        [(0.0, 0.0, round(0.4 * k, 6)) for k in range(30)],
        (1.0, 1.0),
        (8, 8),
    )
    sampler = stack_sampling.StackSampler(
        stack, stack.lattice(qc_surfaces.MINIMUM_VOXEL)
    )
    assert any(not len(sampler.nearest(k).voxels) for k in range(30))

    for bright in range(30):
        previews = qc_previews.previews_of(_thin_stack(bright), ())
        kinds = {p.kind: p for p in previews.previews}
        assert _decoded(kinds[PreviewKind.SERIES_MIP].png).max() == 255
        assert _decoded(kinds[PreviewKind.SERIES_SURFACE].png).any()


# Other volumes and grids.


@pytest.mark.pydicom
def test_an_oblique_rt_dose_grid_is_shown_by_its_dose_levels():
    angle = math.radians(30)
    cosine, sine = round(math.cos(angle), 6), round(math.sin(angle), 6)
    written = {
        0: _dose(
            _hot(19000),
            [2.0 * k for k in range(SIDE)],
            orientation=(cosine, sine, 0.0, -sine, cosine, 0.0),
        )
    }

    previews = qc_previews.previews_of(written, ())

    levels = [p for p in previews.previews if p.kind is PreviewKind.SERIES_DOSE_LEVELS]
    assert len(levels) == 1
    assert levels[0].frames == tuple((0, frame) for frame in range(SIDE))
    assert not previews.not_previewed
    assert previews.pixels_shown == frozenset(written)
    # Its support, the head, and three levels of its hot spot, as for the
    # grid along the patient's axes.
    image = _decoded(levels[0].png)
    rules = np.flatnonzero((image == qc_surfaces.LEVEL_RULE).all(axis=1))
    assert len(np.split(rules, np.flatnonzero(np.diff(rules) > 1) + 1)) == 3


@pytest.mark.pydicom
def test_a_tilted_stack_too_long_to_render_is_neither_rendered_nor_projected():
    orientation = tuple(round(value, 6) for value in _TILT_15)
    written = {
        k: _image(
            np.ones((4, 6)),
            number=k + 1,
            origin=(0.0, 0.0, 1100.0 * k),
            orientation=orientation,
        )
        for k in range(3)
    }

    previews = qc_previews.previews_of(written, ())

    assert [p.kind for p in previews.previews] == [PreviewKind.SERIES_CINE]
    assert previews.pixels_shown == frozenset(written)  # 3 frames, all in its strip


@pytest.mark.pydicom
def test_contours_are_drawn_with_the_surface_of_a_tilted_series():
    scan = head.tilted(degrees=15.0, extent=_TALL, spacing=4.0, thickness=4.0)
    ct = files.ct_files(scan, head.Head(noise=0.0))
    written = dict(enumerate(ct))
    contours = len(written)
    written[contours] = files.structure_set(
        [("ORGAN", files.square((0.0, -40.0, 20.0), half=10.0))]
    )

    previews = qc_previews.previews_of(written, ())

    (sheet,) = [
        p for p in previews.previews if p.kind is PreviewKind.STRUCTURE_SET_CONTOURS
    ]
    # The sheet lists the series whose surface it is drawn with.
    assert sheet.frames == ((contours, 0),) + tuple((k, 0) for k in range(contours))
    assert contours in previews.contours_shown
