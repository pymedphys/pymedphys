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

"""The text detector evaluation's fonts, phantoms, and text injection."""

import dataclasses
import importlib.util
import pickle

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation_fonts as fonts
from pymedphys._dicom.deidentify import text_evaluation_frames as frames
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify.text_detection import TextBox

# -- Fonts --------------------------------------------------------------------


def test_every_glyph_is_seven_rows_of_five_columns():
    for character, rows in fonts.GLYPHS.items():
        assert len(rows) == fonts.GLYPH_ROWS, character
        assert all(len(row) == fonts.GLYPH_COLUMNS for row in rows), character
        assert set("".join(rows)) <= {"#", "."}, character


def test_every_glyph_but_the_space_has_ink_and_glyphs_differ():
    shapes = {}
    for character, rows in fonts.GLYPHS.items():
        if character != " ":
            assert "#" in "".join(rows), character
        shapes.setdefault(rows, []).append(character)
    assert all(len(each) == 1 for each in shapes.values())


def test_the_bitmap_font_scales_by_whole_pixels():
    one = fonts.BitmapFont().coverage("AB", 7)
    three = fonts.BitmapFont().coverage("AB", 20)
    assert one.shape == (7, 11)
    assert three.shape == (21, 33)
    assert set(np.unique(three)) == {0.0, 1.0}
    assert np.array_equal(three[::3, ::3], one)


def test_the_smooth_font_keeps_the_ink_area_at_any_height():
    mask = fonts.glyph_mask("L7")
    for height in (5.0, 9.5, 13.0, 31.0):
        coverage = fonts.SmoothBitmapFont().coverage("L7", height, (0.3, 0.7))
        scale = height / 7
        assert coverage.sum() == pytest.approx(mask.sum() * scale**2)
        assert coverage.min() >= 0 and coverage.max() <= 1
        assert ((coverage > 0) & (coverage < 1)).any()


def test_area_resampling_at_whole_scales_repeats_pixels():
    image = np.array([[1.0, 0.0], [0.5, 0.25]])
    assert np.array_equal(
        fonts.area_resampled(image, 2.0), np.kron(image, np.ones((2, 2)))
    )


def test_a_half_pixel_phase_splits_a_pixel_over_two():
    resampled = fonts.area_resampled(np.ones((1, 1)), 1.0, (0.5, 0.0))
    assert resampled == pytest.approx(np.array([[0.5], [0.5]]))


@pytest.mark.parametrize("height", [0, -1, float("nan"), float("inf")])
def test_heights_must_be_positive(height):
    with pytest.raises(fonts.FontRefused):
        fonts.SmoothBitmapFont().coverage("A", height)


def test_characters_without_a_glyph_are_refused_without_quoting_them():
    with pytest.raises(fonts.FontRefused) as raised:
        fonts.BitmapFont().coverage("Aé", 7)
    assert "é" not in str(raised.value)


def _pillow_with_freetype() -> bool:
    if importlib.util.find_spec("PIL") is None:
        return False
    from PIL import features  # pylint: disable = import-outside-toplevel

    return bool(features.check("freetype2"))


@pytest.mark.skipif(not _pillow_with_freetype(), reason="needs Pillow with FreeType")
def test_a_pillow_font_draws_anti_aliased_text_at_the_cap_height():
    font = fonts.PillowFont("pillow-default")
    for height in (8.0, 16.0, 30.0):
        coverage = font.coverage("HH", height)
        rows = np.flatnonzero(coverage.max(axis=1) > 0.5)
        assert rows[-1] - rows[0] + 1 == pytest.approx(height, abs=2)
        assert ((coverage > 0.05) & (coverage < 0.95)).any()
    assert pickle.loads(pickle.dumps(font)) == font


def test_a_missing_font_file_is_reported(tmp_path):
    if importlib.util.find_spec("PIL") is None:
        pytest.skip("needs Pillow")
    with pytest.raises(OSError):
        fonts.PillowFont("missing", tmp_path / "missing.ttf").coverage("A", 10)


# -- Frames -------------------------------------------------------------------


def _frame(values, **options):
    return frames.EvaluationFrame(
        stored=np.asarray(values),
        collection=options.pop("collection", "synthetic"),
        case=options.pop("case", "case"),
        iod=options.pop("iod", "CT Image Storage"),
        modality=options.pop("modality", "CT"),
        **options,
    )


def test_frames_and_texts_show_nothing_of_themselves():
    frame = _frame(np.full((4, 4), 7), slope=1.0, intercept=-1024.0)
    text = frames.BurnedText(0, 0, np.ones((2, 2)), 2.0, {"font": "x"})
    assert repr(frame) == "EvaluationFrame()"
    assert repr(text) == "BurnedText()"


@pytest.mark.parametrize(
    "change",
    [
        {"stored": np.zeros((2, 2, 2), np.int16)},
        {"stored": np.zeros((2, 2), np.float32)},
        {"stored_range": (5, 5)},
        {"pixel_spacing": 0.0},
        {"slope": 0.0},
    ],
)
def test_frames_that_cannot_be_evaluated_are_refused(change):
    options = {"stored": np.zeros((2, 2), np.int16), **change}
    with pytest.raises(frames.EvaluationRefused):
        _frame(options.pop("stored"), **options)


def test_a_ct_s_tissue_is_above_minus_900_hu():
    values = np.array([[0, 100], [124, 125]], np.int16)
    tissue = frames.tissue_mask(_frame(values, intercept=-1024.0))
    assert tissue.tolist() == [[False, False], [False, True]]


def test_other_frames_tissue_is_their_body_with_holes_filled():
    values = np.zeros((64, 64), np.int16)
    values[16:48, 16:48] = 500
    values[30:34, 30:34] = 0  # a hole inside the body
    tissue = frames.tissue_mask(_frame(values, modality="MR", iod="MR"))
    assert tissue[16:48, 16:48].mean() > 0.95
    assert tissue[30:34, 30:34].all()
    assert not tissue[:12].any()


def test_a_flat_frame_has_no_tissue():
    tissue = frames.tissue_mask(_frame(np.full((8, 8), 3), modality="MR"))
    assert not tissue.any()


def test_noise_is_estimated_robustly():
    rng = np.random.default_rng(0)
    values = rng.normal(0, 10, (256, 256))
    values[100:110, 100:200] += 3000  # an edge does not inflate it
    assert frames.noise_sigma(values) == pytest.approx(10, rel=0.05)
    assert frames.noise_sigma(np.zeros((16, 16))) == 0


def test_a_text_s_zone_grows_with_its_height_and_stays_in_the_frame():
    coverage = np.zeros((10, 30))
    coverage[2:9, 1:29] = 1
    text = frames.BurnedText(5, 3, coverage, 20.0)
    assert text.extent == TextBox(7, 4, 14, 32)
    assert text.zone((100, 100)) == TextBox(0, 0, 34, 52)
    assert text.ink((100, 100), 0.5).sum() == 7 * 28


# -- Phantoms -----------------------------------------------------------------


@pytest.mark.parametrize("kind", phantoms.KINDS)
def test_each_phantom_is_seeded_and_scaled_in_millimetres(kind):
    small = phantoms.Phantom(kind, 128, 400 / 128)
    large = phantoms.Phantom(kind, 256, 400 / 256)
    first = phantoms.phantom_frame(small, np.random.default_rng(3), case="a")
    again = phantoms.phantom_frame(small, np.random.default_rng(3), case="a")
    finer = phantoms.phantom_frame(large, np.random.default_rng(3), case="a")
    assert np.array_equal(first.stored, again.stored)
    assert first.stored.dtype == np.uint16
    low, high = first.stored_range
    assert low <= first.stored.min() and first.stored.max() <= high
    assert first.pixel_spacing == pytest.approx(400 / 128)
    assert first.background == kind
    # The same field: its tissue covers about the same share of the frame.
    share = frames.tissue_mask(first).mean()
    assert 0.05 < share < 0.95
    assert frames.tissue_mask(finer).mean() == pytest.approx(share, abs=0.05)


def test_ct_phantoms_are_stored_as_hounsfield_units_plus_1024():
    frame = phantoms.phantom_frame(
        phantoms.Phantom("ct-head", 256, 1.0), np.random.default_rng(0), case="a"
    )
    hu = frame.stored * frame.slope + frame.intercept
    assert hu.min() == pytest.approx(-1024, abs=60)
    assert (hu > 1000).any()  # cortical bone
    assert frame.hounsfield


def test_phantom_cases_cover_every_combination_and_read_their_frames():
    cases = phantoms.phantom_cases(
        kinds=("pet", "mr-head"), sizes=(64, 96), fields_of_view=(300.0,), seeds=(1, 2)
    )
    assert len(cases) == 8
    assert len({each.case for each in cases}) == 8
    read = list(cases[0].read())
    assert len(read) == 1 and read[0].case == cases[0].case
    assert pickle.loads(pickle.dumps(cases[0])) == cases[0]


def test_unknown_phantoms_are_refused():
    with pytest.raises(frames.EvaluationRefused):
        phantoms.Phantom("ultrasound", 128, 1.0)


# -- Injection ----------------------------------------------------------------


def _ct(seed=0, size=256):
    return phantoms.phantom_frame(
        phantoms.Phantom("ct-thorax", size, 400 / size),
        np.random.default_rng(seed),
        case=f"case-{seed}",
    )


def test_injection_is_reproducible_and_independent_of_order():
    plan = injection.InjectionPlan(texts=3, seed=5)
    first, second = _ct(1), _ct(2)
    a = injection.inject(first, plan).frame
    injection.inject(second, plan)
    again = injection.inject(first, plan).frame
    assert np.array_equal(a.stored, again.stored)
    other = injection.inject(first, dataclasses.replace(plan, seed=6)).frame
    assert not np.array_equal(a.stored, other.stored)


def test_injected_text_changes_only_its_footprint_and_is_recorded():
    frame = _ct()
    injected = injection.inject(frame, injection.InjectionPlan(texts=4)).frame
    changed = injected.stored != frame.stored
    footprints = np.zeros(frame.shape, bool)
    for text in injected.texts:
        rows, columns = text.coverage.shape
        footprints[text.top : text.top + rows, text.left : text.left + columns] = True
    assert changed.any()
    assert not (changed & ~footprints).any()
    for text in injected.texts:
        assert set(text.strata) == {
            "font", "height", "contrast", "contrast_drawn", "polarity",
            "style", "orientation", "position", "content", "zone",
        }  # fmt: skip


def test_injected_texts_never_meet_each_others_zones():
    injected = injection.inject(_ct(4), injection.InjectionPlan(texts=6)).frame
    zones = [text.zone(injected.shape) for text in injected.texts]
    for first, text in enumerate(injected.texts):
        extent = text.extent
        for second, zone in enumerate(zones):
            if first != second:
                assert not (
                    extent.top < zone.bottom
                    and zone.top < extent.bottom
                    and extent.left < zone.right
                    and zone.left < extent.right
                )


@pytest.mark.parametrize("position", injection.POSITIONS)
def test_text_is_placed_where_its_position_says(position):
    plan = injection.InjectionPlan(texts=3, positions=(position,), heights=(10.0,))
    frame = _ct(7)
    tissue = frames.tissue_mask(frame)
    low, high = {"air": (0, 0.02), "tissue": (0.98, 1), "edge": (0.2, 0.8)}[position]
    injected = injection.inject(frame, plan).frame
    assert injected.texts
    for text in injected.texts:
        rows, columns = text.coverage.shape
        share = tissue[
            text.top : text.top + rows, text.left : text.left + columns
        ].mean()
        assert low <= share <= high


def test_saturated_text_reaches_the_stored_range():
    plan = injection.InjectionPlan(
        texts=1, contrasts=("saturated",), polarities=("higher",), styles=("solid",),
        fonts=(fonts.BitmapFont(),), positions=("tissue",),
    )  # fmt: skip
    injected = injection.inject(_ct(3), plan).frame
    (text,) = injected.texts
    ink = text.ink(injected.shape, 0.5)
    assert (injected.stored[ink] == injected.stored_range[1]).all()
    assert text.strata["contrast_drawn"] == "saturated"


def test_the_contrast_stratum_is_the_contrast_reached():
    # Dark text over air can reach only air's distance from the least
    # stored value, whatever was drawn.
    plan = injection.InjectionPlan(
        texts=1, contrasts=(32.0,), polarities=("lower",), styles=("solid",),
        fonts=(fonts.BitmapFont(),), positions=("air",),
    )  # fmt: skip
    (text,) = injection.inject(_ct(5), plan).frame.texts
    assert text.strata["contrast_drawn"] == "32 sigma"
    assert text.strata["contrast"] in (
        "0 to under 1 sigma",
        "1 to under 2 sigma",
        "2 to under 4 sigma",
    )


@pytest.mark.parametrize("style", injection.STYLES)
def test_each_style_keeps_its_text_in_its_ground_truth(style):
    plan = injection.InjectionPlan(
        texts=1, styles=(style,), fonts=(fonts.BitmapFont(),), heights=(14.0,),
        contrasts=(16.0,), positions=("tissue",), orientations=(0,),
    )  # fmt: skip
    injected = injection.inject(_ct(9), plan).frame
    (text,) = injected.texts
    assert text.coverage.max() == 1.0
    if style in ("outlined", "shadowed"):
        # The outline or shadow is part of the text's ink.
        assert (text.coverage > 0).sum() > (
            fonts.BitmapFont().coverage("A", 14) > 0
        ).sum()


@pytest.mark.parametrize("orientation", injection.ORIENTATIONS)
def test_orientation_turns_the_text(orientation):
    drawn = injection._Drawn(  # pylint: disable = protected-access
        font=fonts.BitmapFont(),
        height=7.0,
        height_label="7 px",
        contrast=8.0,
        polarity="higher",
        style="solid",
        orientation=orientation,
        position="air",
        content="name",
        text="ABC",
        phase=(0.0, 0.0),
    )
    coverage = injection.drawn_coverage(drawn)
    assert coverage.shape == ((7, 17) if orientation == 0 else (17, 7))


def test_a_scale_bar_draws_its_label_above_a_bar():
    rng = np.random.default_rng(0)
    label = injection.invented_text("scale", rng)
    assert label.endswith(" cm")
    drawn = injection._Drawn(  # pylint: disable = protected-access
        fonts.BitmapFont(), 14.0, "14 px", 8.0, "higher", "solid", 0, "air",
        "scale", label, (0.0, 0.0),
    )  # fmt: skip
    coverage = injection.drawn_coverage(drawn)
    assert coverage.shape[1] >= 4 * 14
    assert coverage[-1].all()  # the bar


@pytest.mark.parametrize("content", injection.CONTENTS)
def test_invented_text_is_drawable_by_the_bitmap_font(content):
    rng = np.random.default_rng(11)
    for _ in range(50):
        text = injection.invented_text(content, rng)
        assert set(text) <= fonts.CHARACTERS


def test_text_that_cannot_be_placed_is_counted():
    plan = injection.InjectionPlan(texts=2, heights=(40.0,), contents=("name",))
    small = _frame(np.full((48, 48), 24, np.uint16), intercept=-1024.0)
    injected = injection.inject(small, plan)
    assert not injected.frame.texts
    assert sum(injected.not_placed.values()) == 2


def test_heights_in_millimetres_follow_the_spacing():
    plan = injection.InjectionPlan(
        texts=1, heights_mm=(5.0,), fonts=(fonts.BitmapFont(),)
    )
    frame = dataclasses.replace(_ct(2), pixel_spacing=0.5)
    (text,) = injection.inject(frame, plan).frame.texts
    assert text.height == pytest.approx(10.0)
    assert text.strata["height"] == "5 mm"


@pytest.mark.parametrize(
    "change",
    [
        {"styles": ("glowing",)},
        {"orientations": (45,)},
        {"heights": ()},
        {"heights": (0.0,)},
        {"contrasts": ("faint",)},
        {"texts": 0},
        {"fonts": ()},
        {"fonts": (fonts.BitmapFont(), fonts.BitmapFont())},
    ],
)
def test_plans_with_unknown_values_are_refused(change):
    with pytest.raises(frames.EvaluationRefused):
        injection.InjectionPlan(**change)


def test_frames_with_text_or_colour_are_not_injected():
    plan = injection.InjectionPlan()
    with_text = injection.inject(_ct(), plan).frame
    with pytest.raises(frames.EvaluationRefused):
        injection.inject(with_text, plan)
    rgb = _frame(np.zeros((8, 8, 3), np.uint8), stored_range=(0, 255))
    with pytest.raises(frames.EvaluationRefused):
        injection.inject(rgb, plan)


@pytest.mark.parametrize(
    "box, zone",
    [
        (TextBox(0, 0, 10, 10), "corner"),
        (TextBox(0, 45, 10, 55), "edge"),
        (TextBox(45, 45, 55, 55), "centre"),
        (TextBox(90, 90, 100, 100), "corner"),
    ],
)
def test_zones_are_corners_edges_and_the_centre(box, zone):
    assert injection.zone_of(box, (100, 100)) == zone
