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

"""Tests of the QC pack's volumes of multi-frame instances.

Each frame of an Enhanced CT, Legacy Converted Enhanced CT, Enhanced PET,
or Enhanced MR instance is a slice placed by its functional groups, so the
expected previews are those of the same slices written as single-frame
instances, which earlier tests check against the patient's axes. Every
image is synthetic.
"""

import copy
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import qc_previews
from pymedphys._dicom.deidentify.qc_pack import PreviewKind

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_qc_previews import _decoded, _file
from .test_deidentify_qc_surfaces import SIDE, _axial, _body, _coronal, _with

ENHANCED_CT = "1.2.840.10008.5.1.4.1.1.2.1"
LEGACY_CONVERTED_ENHANCED_CT = "1.2.840.10008.5.1.4.1.1.2.2"
ENHANCED_PET = "1.2.840.10008.5.1.4.1.1.130"
ENHANCED_MR = "1.2.840.10008.5.1.4.1.1.4.1"
# The groups that place and rescale a frame, by the attributes that each
# holds, and the group that names its stack and time point.
_GROUPS = {
    "PlanePositionSequence": ("ImagePositionPatient",),
    "PlaneOrientationSequence": ("ImageOrientationPatient",),
    "PixelMeasuresSequence": ("PixelSpacing",),
    "PixelValueTransformationSequence": ("RescaleSlope", "RescaleIntercept"),
}
_SHARED = ("PlaneOrientationSequence", "PixelMeasuresSequence")
_INSTANCE = "2.25.93001"


def _multi_frame(
    slices,
    *,
    sop_class=ENHANCED_CT,
    order=None,
    shared=_SHARED,
    rescales=None,
    rescale_type="HU",
    stacks=None,
    series=None,
    instance=_INSTANCE,
    changed=None,
):
    """One multi-frame instance whose frames are the single-frame files'
    slices, by ``order`` of their keys, or in key order.

    Each frame is placed by Plane Position (Patient), Plane Orientation
    (Patient), and Pixel Measures groups from its slice, each group named in
    ``shared`` in the Shared Functional Groups Sequence, from the first
    frame's slice, and every other in the frame's item. Each frame's Pixel
    Value Transformation group gives its (slope, intercept) of
    ``rescales``, or (1, 0), with stored values such that its rescaled
    values are its slice's, and Rescale Type ``rescale_type``, or none
    where it is None. Each frame's Frame Content group gives (Stack ID,
    Temporal Position Index) of ``stacks``, where given. ``changed`` is
    called with the data set before it is written.
    """
    keys = sorted(slices) if order is None else list(order)
    datasets = [pydicom.dcmread(io.BytesIO(slices[key])) for key in keys]
    first = datasets[0]
    dataset = copy.deepcopy(first)
    for keyword in (
        "ImagePositionPatient",
        "ImageOrientationPatient",
        "PixelSpacing",
        "RescaleSlope",
        "RescaleIntercept",
        "PixelData",
    ):
        if keyword in dataset:
            del dataset[keyword]
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    if series is not None:
        dataset.SeriesInstanceUID = series
    dataset.InstanceNumber = 1
    dataset.NumberOfFrames = len(datasets)
    rescales = rescales or [(1.0, 0.0)] * len(datasets)

    def group(source, keyword, index):
        item = pydicom.Dataset()
        if keyword == "PixelValueTransformationSequence":
            item.RescaleSlope, item.RescaleIntercept = rescales[index]
            if rescale_type is not None:
                item.RescaleType = rescale_type
            return item
        for attribute in _GROUPS[keyword]:
            setattr(item, attribute, source[attribute].value)
        return item

    common = pydicom.Dataset()
    for keyword in shared:
        setattr(common, keyword, [group(first, keyword, 0)])
    dataset.SharedFunctionalGroupsSequence = [common]
    dataset.PerFrameFunctionalGroupsSequence = []
    stored = []
    for index, each in enumerate(datasets):
        item = pydicom.Dataset()
        for keyword in _GROUPS:
            if keyword not in shared:
                setattr(item, keyword, [group(each, keyword, index)])
        if stacks is not None:
            content = pydicom.Dataset()
            stack, time = stacks[index]
            if stack:
                content.StackID = stack
            if time:
                content.TemporalPositionIndex = int(time)
            item.FrameContentSequence = [content]
        dataset.PerFrameFunctionalGroupsSequence.append(item)
        slope, intercept = rescales[index]
        values = each.pixel_array.astype(float) * float(
            each.get("RescaleSlope", 1)
        ) + float(each.get("RescaleIntercept", 0))
        frame = (values - intercept) / slope
        assert np.array_equal(frame, np.rint(frame))
        assert frame.min() >= -32768 and frame.max() <= 32767
        stored.append(frame.astype("<i2"))
    dataset.PixelData = np.stack(stored).tobytes()
    dataset["PixelData"].VR = "OW"
    if changed is not None:
        changed(dataset)
    return _file(dataset)


def _kinds(previews):
    return [preview.kind for preview in previews.previews]


def _only(previews, kind):
    (found,) = [preview for preview in previews.previews if preview.kind is kind]
    return found


# The head of qc_surfaces' tests, of 40 axial slices 2 mm apart.
def _single():
    return _axial(_body())


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "sop_class", [ENHANCED_CT, LEGACY_CONVERTED_ENHANCED_CT, ENHANCED_PET, ENHANCED_MR]
)
@pytest.mark.parametrize(
    "shared", [_SHARED, (), (*_SHARED, "PixelValueTransformationSequence")]
)
def test_a_multi_frame_volume_is_projected_and_rendered_as_its_slices_are(
    sop_class, shared
):
    single = qc_previews.previews_of(_single(), ())
    modality = {ENHANCED_PET: "PT", ENHANCED_MR: "MR"}.get(sop_class, "CT")
    # Otsu's threshold for PET and MR, as for their single-frame slices.
    expected = (
        single
        if modality == "CT"
        else qc_previews.previews_of(_axial(_body(), modality=modality), ())
    )
    written = {
        0: _multi_frame(
            _axial(_body(), modality=modality),
            sop_class=sop_class,
            shared=shared,
            rescale_type="HU" if modality == "CT" else "US",
        )
    }

    previews = qc_previews.previews_of(written, ())

    assert _kinds(previews) == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
    ]
    for kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE):
        found = _only(previews, kind)
        assert found.png == _only(expected, kind).png
        assert found.frames == tuple((0, frame) for frame in range(SIDE))
        assert found.total_frames == SIDE
    # Every one of its 40 frames is drawn, more than a cine strip shows, so
    # a face verdict can release its pixel data.
    assert SIDE > qc_previews.CINE_FRAMES
    assert previews.pixels_shown == frozenset({0})
    assert not previews.not_previewed


@pytest.mark.pydicom
def test_frames_in_any_order_are_stacked_along_the_normal():
    single = qc_previews.previews_of(_single(), ())
    order = list(np.random.default_rng(3).permutation(SIDE))
    written = {0: _multi_frame(_single(), order=order)}

    previews = qc_previews.previews_of(written, ())

    for kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE):
        found = _only(previews, kind)
        assert found.png == _only(single, kind).png
        # Listed from the lowest slice up, by the frame that holds each.
        assert found.frames == tuple((0, order.index(k)) for k in range(SIDE))
    assert previews.pixels_shown == frozenset({0})


@pytest.mark.pydicom
def test_a_coronal_multi_frame_volume_is_rendered_as_its_slices_are():
    single = qc_previews.previews_of(_coronal(_body(ear=True)), ())
    written = {0: _multi_frame(_coronal(_body(ear=True)))}

    previews = qc_previews.previews_of(written, ())

    for kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE):
        assert _only(previews, kind).png == _only(single, kind).png


@pytest.mark.pydicom
def test_each_frame_is_rescaled_by_its_own_group():
    # Stored values 1024 above Hounsfield units in even frames, and half of
    # 1000 above them in odd frames: rescaled, every frame is its slice.
    rescales = [(1.0, -1024.0) if k % 2 == 0 else (2.0, -1000.0) for k in range(SIDE)]
    single = qc_previews.previews_of(_single(), ())
    written = {0: _multi_frame(_single(), rescales=rescales)}
    stored = pydicom.dcmread(io.BytesIO(written[0])).pixel_array
    assert stored[::2].max() == 40 + 1024 and stored[1::2].max() == (40 + 1000) // 2

    previews = qc_previews.previews_of(written, ())

    for kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE):
        assert _only(previews, kind).png == _only(single, kind).png


@pytest.mark.pydicom
@pytest.mark.parametrize("rescale_type", ["US", None])
def test_ct_frames_not_known_to_be_hounsfield_units_are_rendered_by_otsu(
    rescale_type,
):
    # Tissue at -500 lies below the CT surface's -300 HU, so a CT render
    # shows none of it, while Otsu's threshold finds the head against air.
    faint = _axial(_body(inside=-500))
    assert not _decoded(
        _only(qc_previews.previews_of(faint, ()), PreviewKind.SERIES_SURFACE).png
    ).any()
    expected = _only(
        qc_previews.previews_of(_axial(_body(inside=-500), modality="MR"), ()),
        PreviewKind.SERIES_SURFACE,
    ).png
    assert _decoded(expected).any()

    written = {0: _multi_frame(faint, rescale_type=rescale_type)}
    found = _only(qc_previews.previews_of(written, ()), PreviewKind.SERIES_SURFACE)

    assert found.png == expected


@pytest.mark.pydicom
def test_a_ct_image_of_other_units_than_hounsfield_is_rendered_by_otsu():
    faint = {
        k: _with(data, RescaleType="US")
        for k, data in _axial(_body(inside=-500)).items()
    }
    expected = qc_previews.previews_of(_axial(_body(inside=-500), modality="MR"), ())

    previews = qc_previews.previews_of(faint, ())

    assert (
        _only(previews, PreviewKind.SERIES_SURFACE).png
        == _only(expected, PreviewKind.SERIES_SURFACE).png
    )
    # Rescale Type HU keeps the CT surface, as an absent one does.
    hounsfield = {
        k: _with(data, RescaleType="HU")
        for k, data in _axial(_body(inside=-500)).items()
    }
    surface = _only(qc_previews.previews_of(hounsfield, ()), PreviewKind.SERIES_SURFACE)
    assert not _decoded(surface.png).any()


def _volume_previews(previews):
    """Each volume's projection and surface render, in order."""
    return [
        preview
        for preview in previews.previews
        if preview.kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE)
    ]


def _each_alone(written, parts, previews):
    """That each part, by its run positions in ``written``, is a volume of its
    own, drawn as the part's slices alone are, in order."""
    found = _volume_previews(previews)
    assert len(found) == 2 * len(parts)
    for index, (part, frames) in enumerate(parts):
        expected = qc_previews.previews_of(part, ())
        for kind, preview in zip(
            (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE),
            found[2 * index :][:2],
        ):
            assert preview.kind is kind
            assert preview.png == _only(expected, kind).png
            assert preview.frames == frames
    assert previews.pixels_shown == frozenset(written)


@pytest.mark.pydicom
def test_single_frame_and_multi_frame_instances_of_a_series_are_volumes_of_their_own():
    # Interleaved, the multi-frame instance's slices would sit between the
    # single-frame ones, and one outline could hide the other's.
    plain = _single()
    eared = _axial(_body(ear=True))
    lower = {k: plain[k] for k in range(0, SIDE, 2)}
    upper = {k: eared[k] for k in range(1, SIDE, 2)}
    written = {**lower, SIDE: _multi_frame(upper)}

    previews = qc_previews.previews_of(written, ())

    _each_alone(
        written,
        [
            (lower, tuple((k, 0) for k in range(0, SIDE, 2))),
            (upper, tuple((SIDE, frame) for frame in range(SIDE // 2))),
        ],
        previews,
    )


def _organised(*uids, concatenation=None):
    """A change that names each Dimension Organization UID, and a
    Concatenation UID, where given."""

    def changed(dataset):
        dataset.DimensionOrganizationSequence = []
        for uid in uids:
            item = pydicom.Dataset()
            item.DimensionOrganizationUID = uid
            dataset.DimensionOrganizationSequence.append(item)
        if concatenation is not None:
            dataset.ConcatenationUID = concatenation
        if not uids:
            del dataset.DimensionOrganizationSequence

    return changed


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "organisations", [("2.25.94001", "2.25.94002"), ("2.25.94001",) * 2, (None, None)]
)
def test_instances_that_reuse_a_stack_and_time_point_are_volumes_of_their_own(
    organisations,
):
    # PS3.3 C.7.6.16.2.2.4 lets another SOP Instance reuse a Stack ID, so
    # two acquisitions labelled alike at interleaved positions, 2 mm apart
    # each and 1 mm apart from each other, are each drawn alone; one
    # merged volume would show the broader outline and hide the other.
    plain = _single()
    eared = _axial(_body(ear=True))
    even = {k: plain[k] for k in range(0, SIDE, 2)}
    odd = {k: eared[k] for k in range(1, SIDE, 2)}
    labels = [("1", "1")] * (SIDE // 2)
    written = {
        0: _multi_frame(
            even,
            stacks=labels,
            instance="2.25.93002",
            changed=_organised(*filter(None, organisations[:1])),
        ),
        1: _multi_frame(
            odd,
            stacks=labels,
            instance="2.25.93003",
            changed=_organised(*filter(None, organisations[1:])),
        ),
    }

    previews = qc_previews.previews_of(written, ())

    frames = tuple(range(SIDE // 2))
    _each_alone(
        written,
        [
            (even, tuple((0, frame) for frame in frames)),
            (odd, tuple((1, frame) for frame in frames)),
        ],
        previews,
    )


@pytest.mark.pydicom
@pytest.mark.parametrize("interleaved", [False, True])
def test_the_instances_of_one_concatenation_form_one_volume(interleaved):
    single = qc_previews.previews_of(_single(), ())
    slices = _single()
    if interleaved:
        parts = [range(0, SIDE, 2), range(1, SIDE, 2)]
    else:
        parts = [range(SIDE // 2), range(SIDE // 2, SIDE)]
    labels = [("1", "1")] * (SIDE // 2)
    written = {
        index: _multi_frame(
            {k: slices[k] for k in part},
            stacks=labels,
            instance=f"2.25.9300{4 + index}",
            changed=_organised("2.25.94001", concatenation="2.25.95001"),
        )
        for index, part in enumerate(parts)
    }

    previews = qc_previews.previews_of(written, ())

    assert _kinds(previews) == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
    ]
    for kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE):
        found = _only(previews, kind)
        assert found.png == _only(single, kind).png
        assert found.frames == tuple(
            next(
                (index, list(part).index(k))
                for index, part in enumerate(parts)
                if k in part
            )
            for k in range(SIDE)
        )
    assert previews.pixels_shown == frozenset({0, 1})


@pytest.mark.pydicom
def test_an_instance_of_two_dimension_organisations_forms_no_volume():
    # A Stack ID is unique only within its Dimension Organization UID, so
    # the frames of an instance of two cannot be told apart by it.
    written = {
        0: _multi_frame(_single(), changed=_organised("2.25.94001", "2.25.94002"))
    }

    previews = qc_previews.previews_of(written, ())

    assert _kinds(previews) == [PreviewKind.SERIES_CINE]
    assert previews.pixels_shown == frozenset()


def _two_times(stacks):
    """The head at one time point, then with an ear at the next, as one
    instance of 80 frames, frame k of each time at slice k."""
    slices = {**_single(), **{SIDE + k: v for k, v in _axial(_body(ear=True)).items()}}
    return _multi_frame(slices, stacks=stacks)


@pytest.mark.pydicom
@pytest.mark.parametrize("by", ["time", "stack"])
def test_each_time_point_or_stack_of_an_instance_is_a_volume_of_its_own(by):
    stacks = [
        ("", str(1 + k // SIDE)) if by == "time" else (str(1 + k // SIDE), "")
        for k in range(2 * SIDE)
    ]
    written = {0: _two_times(stacks)}

    previews = qc_previews.previews_of(written, ())

    assert _kinds(previews) == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
    ]
    for index, body in enumerate((_body(), _body(ear=True))):
        expected = qc_previews.previews_of(_axial(body), ())
        offset = index * SIDE
        for kind, found in zip(
            (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE),
            previews.previews[1 + 2 * index :][:2],
        ):
            assert found.kind is kind
            assert found.png == _only(expected, kind).png
            assert found.frames == tuple((0, offset + k) for k in range(SIDE))
    assert previews.pixels_shown == frozenset({0})


@pytest.mark.pydicom
def test_frames_at_one_position_of_one_time_point_form_no_volume():
    # Without a Frame Content group, the two times' frames share positions,
    # and their union could hide the surface of either.
    written = {0: _two_times(None)}

    previews = qc_previews.previews_of(written, ())

    assert _kinds(previews) == [PreviewKind.SERIES_CINE]
    assert previews.pixels_shown == frozenset()


def _without(keyword, frame=3):
    def changed(dataset):
        del dataset.PerFrameFunctionalGroupsSequence[frame][keyword]

    return changed


def _in_both(dataset):
    shared = dataset.SharedFunctionalGroupsSequence[0]
    dataset.PerFrameFunctionalGroupsSequence[
        3
    ].PlaneOrientationSequence = copy.deepcopy(shared.PlaneOrientationSequence)


def _unreadable_slope(dataset):
    item = dataset.PerFrameFunctionalGroupsSequence[3]
    del item.PixelValueTransformationSequence[0].RescaleSlope


def _two_items(dataset):
    item = dataset.PerFrameFunctionalGroupsSequence[3].PlanePositionSequence
    item.append(copy.deepcopy(item[0]))


def _too_few_items(dataset):
    del dataset.PerFrameFunctionalGroupsSequence[-1]


def _oblique(dataset):
    dataset.SharedFunctionalGroupsSequence[0].PlaneOrientationSequence[
        0
    ].ImageOrientationPatient = [0.6, 0.64, 0.48, 0, 0.6, -0.8]


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "changed",
    [
        _without("PlanePositionSequence"),
        _without("PixelValueTransformationSequence"),
        _in_both,
        _unreadable_slope,
        _two_items,
        _too_few_items,
        _oblique,
    ],
)
def test_frames_that_their_groups_cannot_place_or_rescale_form_no_volume(changed):
    written = {0: _multi_frame(_single(), changed=changed)}

    previews = qc_previews.previews_of(written, ())

    # Its 40 frames are more than its cine strip shows, so its pixel data
    # stay held whatever a verdict says.
    assert _kinds(previews) == [PreviewKind.SERIES_CINE]
    assert previews.pixels_shown == frozenset()


# A coarse scan of the analytic head, to draw contour and segments sheets on.
_SCAN = head.axial(
    spacing=4.0, thickness=4.0, extent=((-100, 100), (-130, 110), (-60, 110))
)


def _head_ct():
    return files.ct_files(_SCAN, head.Head(noise=0.0))


def _sheets(written, kind):
    previews = qc_previews.previews_of(written, ())
    return previews, _only(previews, kind)


@pytest.mark.pydicom
def test_a_contour_sheet_is_drawn_on_a_multi_frame_volume_as_on_its_slices():
    slices = _head_ct()
    count = len(slices)
    contours = files.structure_set(
        [("EXTERNAL", [files.square((0.0, -40.0, z), 30.0) for z in (-20.0, 0.0)])]
    )
    single = dict(enumerate(slices))
    single[count] = contours
    enhanced = {0: files.multi_frame(slices), 1: contours}

    _, expected = _sheets(single, PreviewKind.STRUCTURE_SET_CONTOURS)
    previews, found = _sheets(enhanced, PreviewKind.STRUCTURE_SET_CONTOURS)

    assert found.png == expected.png
    # The sheet lists the structure set, then the volume that it is drawn on.
    assert found.frames == ((1, 0), *((0, k) for k in range(count)))
    assert previews.contours_shown == frozenset({1})
    assert previews.pixels_shown == frozenset({0})


@pytest.mark.pydicom
def test_a_segments_sheet_is_drawn_on_a_multi_frame_volume_as_on_its_slices():
    slices = _head_ct()
    count = len(slices)
    mask = np.stack(
        [
            head.hounsfield(_SCAN.points(index)) >= -300
            for index in range(len(_SCAN.positions))
        ]
    )
    segmentation = files.segmentation(_SCAN, [mask])
    single = dict(enumerate(slices))
    single[count] = segmentation
    enhanced = {0: files.multi_frame(slices), 1: segmentation}

    _, expected = _sheets(single, PreviewKind.SEGMENTATION_SEGMENTS)
    previews, found = _sheets(enhanced, PreviewKind.SEGMENTATION_SEGMENTS)

    assert found.png == expected.png
    frames = pydicom.dcmread(io.BytesIO(segmentation)).NumberOfFrames
    assert found.frames == (
        *((1, k) for k in range(frames)),
        *((0, k) for k in range(count)),
    )
    assert previews.pixels_shown == frozenset({0, 1})
