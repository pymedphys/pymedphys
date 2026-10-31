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

"""Burn synthetic text into frames, with exact ground truth (D-056).

The same code burns text into synthetic phantoms and, on a CI runner, into
real images that hold none, so that sensitivity is measured on real anatomy
with nobody viewing an image: only counts leave the runner.

An :class:`InjectionPlan` lists the values of each property of the text to
draw from. For each piece of text, :func:`inject` draws one value of each,
uniformly and independently, from a generator seeded by the plan's seed, the
frame's collection, case, and frame number, so that a frame gets the same
text however many processes run and in whatever order:

font
    One of the plan's fonts (:mod:`~.text_evaluation_fonts`).
height
    A cap height in pixels, or, where the plan gives heights in millimetres
    and the frame its spacing, in millimetres.
contrast
    How far the ink's stored value lies from the median of the stored values
    under the text, in multiples of the frame's noise
    (:func:`~.text_evaluation_frames.noise_sigma`, at least one stored
    unit), or ``"saturated"``: the greatest or least stored value. The ink
    is clipped to the stored range, so text darker than air on a CT may
    reach far less contrast than was drawn: the text's ``contrast`` stratum
    is the contrast it reached against what lies behind it (its box, for a
    boxed text), halved for a translucent one, in the bins of
    :data:`CONTRAST`, and ``contrast_drawn`` the one drawn.
polarity
    ``"higher"`` or ``"lower"`` stored values than the background.
style
    ``"solid"``; ``"outlined"``, a one-pixel ring of the opposite polarity;
    ``"shadowed"``, a copy of the opposite polarity one pixel down and
    right; ``"boxed"``, on an opaque box of the opposite polarity; or
    ``"translucent"``, blended at half its coverage.
orientation
    0, 90, or 270 degrees anticlockwise.
position
    ``"air"``, where at most 2% of the text's footprint is tissue;
    ``"tissue"``, where at least 98% is; or ``"edge"``, from 20% to 80%:
    across the body's edge (:func:`~.text_evaluation_frames.tissue_mask`).
content
    ``"name"``, ``"identifier"``, ``"date"``, ``"letter"`` (a single
    orientation letter), ``"parameters"`` (acquisition settings), or
    ``"scale"`` (a scale bar with its length).

The text is drawn as coverage, composited onto the frame in floats, rounded,
and clipped to the stored range. Its ground truth
(:class:`~.text_evaluation_frames.BurnedText`) is its coverage, with any
outline or shadow, and the values it was drawn with, as strata. Each value
is a choice from the plan, never a value of the frame. Each text's place is
drawn uniformly from every place in the frame that meets its position and
lies clear of the zones of the text already placed. A text with no such
place is not drawn and is counted by why.

Every string is invented: names from syllables that the module lists,
identifiers and dates from the generator.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from collections.abc import Mapping

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from .text_detection import TextBox
from .text_evaluation_fonts import BitmapFont, Font, SmoothBitmapFont
from .text_evaluation_frames import (
    BurnedText,
    EvaluationFrame,
    EvaluationRefused,
    noise_sigma,
    tissue_mask,
)

STYLES = ("solid", "outlined", "shadowed", "boxed", "translucent")
POLARITIES = ("higher", "lower")
ORIENTATIONS = (0, 90, 270)
POSITIONS = ("air", "tissue", "edge")
CONTENTS = ("name", "identifier", "date", "letter", "parameters", "scale")
SATURATED = "saturated"
# The share of a footprint that is tissue, for each position.
_POSITION_SHARES = {"air": (0.0, 0.02), "tissue": (0.98, 1.0), "edge": (0.2, 0.8)}
_SYLLABLES = (
    "KA", "LO", "VEN", "MIR", "TA", "SOL", "DREN", "PAV", "ESK", "ORI",
    "NUL", "BEX", "QUA", "ZIM", "RHO", "TEV", "WAN", "JUL", "FEN", "GOR",
)  # fmt: skip
_MONTHS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)  # fmt: skip


@dataclasses.dataclass(frozen=True)
class InjectionPlan:
    """The values that each property of injected text is drawn from, as the
    module describes.

    Attributes
    ----------
    fonts : tuple of Font
    heights : tuple of float
        Cap heights in pixels.
    heights_mm : tuple of float
        Cap heights in millimetres; where given, they replace ``heights``
        for frames whose spacing is known.
    contrasts : tuple of float or str
        Multiples of the noise, or ``"saturated"``.
    polarities, styles, orientations, positions, contents : tuple
        Values from :data:`POLARITIES`, :data:`STYLES`,
        :data:`ORIENTATIONS`, :data:`POSITIONS`, and :data:`CONTENTS`.
    texts : int
        How many pieces of text each frame is given.
    seed : int
    """

    fonts: tuple[Font, ...] = (BitmapFont(), SmoothBitmapFont())
    heights: tuple[float, ...] = (5.0, 7.0, 10.0, 14.0, 20.0, 28.0, 40.0)
    heights_mm: tuple[float, ...] = ()
    contrasts: tuple[float | str, ...] = (2.0, 4.0, 8.0, 16.0, 32.0, SATURATED)
    polarities: tuple[str, ...] = POLARITIES
    styles: tuple[str, ...] = STYLES
    orientations: tuple[int, ...] = ORIENTATIONS
    positions: tuple[str, ...] = POSITIONS
    contents: tuple[str, ...] = CONTENTS
    texts: int = 3
    seed: int = 0

    def __post_init__(self):
        for name, allowed in (
            ("polarities", POLARITIES),
            ("styles", STYLES),
            ("orientations", ORIENTATIONS),
            ("positions", POSITIONS),
            ("contents", CONTENTS),
        ):
            values = getattr(self, name)
            if not values or not set(values) <= set(allowed):
                raise EvaluationRefused(f"The plan's {name} must be known values.")
        if not self.fonts or not all(isinstance(each, Font) for each in self.fonts):
            raise EvaluationRefused("The plan must name fonts.")
        if len({each.name for each in self.fonts}) != len(self.fonts):
            raise EvaluationRefused("The plan's fonts must have different names.")
        for name in ("heights", "heights_mm"):
            if not all(_positive(each) for each in getattr(self, name)):
                raise EvaluationRefused(f"The plan's {name} must be positive.")
        if not self.heights:
            raise EvaluationRefused("The plan must give heights in pixels.")
        if not self.contrasts or not all(
            each == SATURATED or (_positive(each) and not isinstance(each, str))
            for each in self.contrasts
        ):
            raise EvaluationRefused(
                'The plan\'s contrasts must be positive or "saturated".'
            )
        if self.texts < 1:
            raise EvaluationRefused("The plan must give each frame text.")

    def described(self) -> dict[str, object]:
        """The plan, for the summary: its fonts by name."""
        return {
            "fonts": [each.name for each in self.fonts],
            "heights": list(self.heights),
            "heights_mm": list(self.heights_mm),
            "contrasts": list(self.contrasts),
            "polarities": list(self.polarities),
            "styles": list(self.styles),
            "orientations": list(self.orientations),
            "positions": list(self.positions),
            "contents": list(self.contents),
            "texts": self.texts,
            "seed": self.seed,
        }


def _positive(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


@dataclasses.dataclass(frozen=True)
class Injected:
    """A frame with text burned in, and the texts that could not be placed,
    by why (such as ``"no-edge-place"``)."""

    frame: EvaluationFrame
    not_placed: Mapping[str, int]


def frame_rng(seed: int, frame: EvaluationFrame) -> np.random.Generator:
    """A generator for one frame's text, from the plan's seed and the
    frame's collection, case, and number, so that it does not depend on the
    order in which frames are injected."""
    digest = hashlib.sha256(
        "\0".join(
            ("pymedphys-text-injection/1", str(seed), frame.collection, frame.case)
        ).encode()
    ).digest()
    return np.random.default_rng([int.from_bytes(digest[:8], "big"), frame.number])


def inject(frame: EvaluationFrame, plan: InjectionPlan) -> Injected:
    """Burn the plan's text into a frame, as the module describes.

    Raises
    ------
    EvaluationRefused
        If the frame already holds text, or is RGB, whose text this module
        does not draw.
    """
    if frame.texts:
        raise EvaluationRefused("The frame already holds text.")
    if frame.rgb:
        raise EvaluationRefused("Text is injected only into monochrome frames.")
    rng = frame_rng(plan.seed, frame)
    values = frame.stored.astype(np.float64)
    tissue = tissue_mask(frame)
    sigma = max(1.0, noise_sigma(values))
    taken = np.zeros(frame.shape, bool)
    inked = np.zeros(frame.shape, bool)
    texts: list[BurnedText] = []
    not_placed: dict[str, int] = {}
    for _ in range(plan.texts):
        drawn = _draw(plan, rng, frame.pixel_spacing)
        placed = _place(drawn, frame, rng, tissue, (taken, inked), values, sigma)
        if isinstance(placed, str):
            not_placed[placed] = not_placed.get(placed, 0) + 1
            continue
        values, text = placed
        zone = text.zone(frame.shape)
        taken[zone.top : zone.bottom, zone.left : zone.right] = True
        inked[text.top : text.top + text.coverage.shape[0],
              text.left : text.left + text.coverage.shape[1]] = True  # fmt: skip
        texts.append(text)
    low, high = frame.stored_range
    stored = np.clip(np.rint(values), low, high).astype(frame.stored.dtype)
    return Injected(
        frame.with_texts(stored, tuple(texts)), dict(sorted(not_placed.items()))
    )


@dataclasses.dataclass(frozen=True)
class _Drawn:
    font: Font
    height: float
    height_label: str
    contrast: float | str
    polarity: str
    style: str
    orientation: int
    position: str
    content: str
    text: str
    phase: tuple[float, float]


def _draw(
    plan: InjectionPlan, rng: np.random.Generator, spacing: float | None
) -> _Drawn:
    font = plan.fonts[int(rng.integers(len(plan.fonts)))]
    if plan.heights_mm and spacing is not None:
        mm = plan.heights_mm[int(rng.integers(len(plan.heights_mm)))]
        height, label = mm / spacing, f"{mm:g} mm"
    else:
        height = plan.heights[int(rng.integers(len(plan.heights)))]
        label = f"{height:g} px"
    content = plan.contents[int(rng.integers(len(plan.contents)))]
    return _Drawn(
        font=font,
        height=float(height),
        height_label=label,
        contrast=plan.contrasts[int(rng.integers(len(plan.contrasts)))],
        polarity=plan.polarities[int(rng.integers(len(plan.polarities)))],
        style=plan.styles[int(rng.integers(len(plan.styles)))],
        orientation=plan.orientations[int(rng.integers(len(plan.orientations)))],
        position=plan.positions[int(rng.integers(len(plan.positions)))],
        content=content,
        text=invented_text(content, rng),
        phase=(float(rng.uniform(0, 1)), float(rng.uniform(0, 1))),
    )


def _name(rng: np.random.Generator) -> str:
    surname = "".join(rng.choice(_SYLLABLES, size=int(rng.integers(2, 4))))
    given = "".join(rng.choice(_SYLLABLES, size=int(rng.integers(1, 3))))
    if rng.uniform() < 0.5:
        return f"{surname}^{given}"
    return f"{surname.capitalize()}, {given.capitalize()}"


def _identifier(rng: np.random.Generator) -> str:
    digits = "".join(
        str(each) for each in rng.integers(0, 10, int(rng.integers(6, 11)))
    )
    return ("ID ", "MRN ", "#", "Pt ", "")[int(rng.integers(5))] + digits


def _date(rng: np.random.Generator) -> str:
    year, month, day = (
        int(rng.integers(1930, 2030)),
        int(rng.integers(1, 13)),
        int(rng.integers(1, 29)),
    )
    hour, minute = int(rng.integers(0, 24)), int(rng.integers(0, 60))
    forms = (
        f"{year:04d}-{month:02d}-{day:02d}",
        f"{day:02d}/{month:02d}/{year:04d}",
        f"{day:02d}-{_MONTHS[month - 1]}-{year:04d}",
        f"{year:04d}{month:02d}{day:02d} {hour:02d}:{minute:02d}",
        f"DOB {day:02d}.{month:02d}.{year:04d}",
    )
    return forms[int(rng.integers(len(forms)))]


def _parameters(rng: np.random.Generator) -> str:
    forms = (
        f"W:{int(rng.integers(50, 2000))} L:{int(rng.integers(-500, 500))}",
        f"kV {int(rng.integers(70, 141))} mAs {int(rng.integers(20, 400))}",
        f"TE {int(rng.integers(5, 120))} TR {int(rng.integers(300, 5000))}",
        f"Gantry {int(rng.integers(0, 360))}",
        f"Slice {int(rng.integers(1, 400))}/{int(rng.integers(100, 400))}",
    )
    return forms[int(rng.integers(len(forms)))]


_INVENTED = {
    "name": _name,
    "identifier": _identifier,
    "date": _date,
    "letter": lambda rng: "LRAPHF"[int(rng.integers(6))],
    "parameters": _parameters,
    "scale": lambda rng: f"{int(rng.choice((1, 2, 5, 10)))} cm",
}


def invented_text(content: str, rng: np.random.Generator) -> str:
    """An invented string of one kind of content; ``"scale"`` gives the
    scale bar's label."""
    invent = _INVENTED.get(content)
    if invent is None:
        raise EvaluationRefused("The content is not a known kind.")
    return invent(rng)


def drawn_coverage(drawn: _Drawn) -> np.ndarray:
    """The text's coverage before its style, turned to its orientation; for
    a scale bar, the label above a bar with end ticks."""
    coverage = drawn.font.coverage(drawn.text, drawn.height, drawn.phase)
    if drawn.content == "scale":
        thickness = max(1, round(drawn.height / 7))
        length = max(coverage.shape[1], round(4 * drawn.height))
        tick = max(2, round(drawn.height / 2))
        gap = thickness
        ruler = np.zeros((tick, length))
        ruler[tick - thickness :, :] = 1
        ruler[:, :thickness] = 1
        ruler[:, length - thickness :] = 1
        label = np.zeros((coverage.shape[0], length))
        label[:, : coverage.shape[1]] = coverage
        coverage = np.concatenate([label, np.zeros((gap, length)), ruler])
    return np.rot90(coverage, k=drawn.orientation // 90).copy()


def _styled(
    coverage: np.ndarray, style: str, height: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The text's coverage, the coverage drawn in the opposite polarity
    under it, and its ground truth, each padded to the footprint."""
    pad = max(2, math.ceil(height / 7)) if style == "boxed" else 2
    text = np.pad(coverage, pad)
    under = np.zeros_like(text)
    if style == "outlined":
        inked = text > 0
        ring = scipy.ndimage.binary_dilation(inked, np.ones((3, 3), bool)) & ~inked
        under = ring.astype(np.float64)
    elif style == "shadowed":
        under = np.zeros_like(text)
        under[1:, 1:] = text[:-1, :-1]
    elif style == "boxed":
        under = np.ones_like(text)
    truth = text if style == "boxed" else np.maximum(text, under)
    if style == "translucent":
        # Blended at half its coverage; its truth is still its whole shape.
        text = text * 0.5
    return text, under, truth


def _place(
    drawn: _Drawn,
    frame: EvaluationFrame,
    rng: np.random.Generator,
    tissue: np.ndarray,
    occupied: tuple[np.ndarray, np.ndarray],
    values: np.ndarray,
    sigma: float,
) -> tuple[np.ndarray, BurnedText] | str:
    """Draw the text at a place that meets its position, clear of the
    zones of the text already placed, ``occupied[0]``, with its own zone
    clear of their footprints, ``occupied[1]``, or say why none does."""
    taken, inked = occupied
    text, under, truth = _styled(drawn_coverage(drawn), drawn.style, drawn.height)
    rows, columns = text.shape
    if rows > frame.shape[0] or columns > frame.shape[1]:
        return "too-large"
    low_share, high_share = _POSITION_SHARES[drawn.position]
    shares = _window_sums(tissue, rows, columns) / (rows * columns)
    margin = max(8, math.ceil(drawn.height))
    grown = np.pad(inked, margin)
    free = (_window_sums(taken, rows, columns) == 0) & (
        _window_sums(grown, rows + 2 * margin, columns + 2 * margin) == 0
    )
    # A small tolerance, so that a share of exactly a limit is within it.
    places = np.flatnonzero(
        free & (shares >= low_share - 1e-9) & (shares <= high_share + 1e-9)
    )
    if not places.size:
        return f"no-{drawn.position}-place"
    top, left = divmod(int(places[int(rng.integers(places.size))]), shares.shape[1])
    window = (slice(top, top + rows), slice(left, left + columns))
    background = values[window]
    ink, opposite = _ink_values(
        drawn, float(np.median(background)), sigma, frame.stored_range
    )
    drawn_values = background * (1 - under) + opposite * under
    drawn_values = drawn_values * (1 - text) + ink * text
    written = values.copy()
    written[window] = drawn_values
    burned = BurnedText(top, left, truth, drawn.height)
    behind = opposite if drawn.style == "boxed" else float(np.median(background))
    weight = 0.5 if drawn.style == "translucent" else 1.0
    achieved = weight * abs(ink - behind) / sigma
    strata = {
        **_strata(drawn),
        "contrast": contrast_label(achieved),
        "zone": zone_of(burned.extent, frame.shape),
    }
    return written, dataclasses.replace(burned, strata=strata)


def _window_sums(mask: np.ndarray, rows: int, columns: int) -> np.ndarray:
    """The sum of the mask over every window of ``rows`` by ``columns`` that
    the frame holds, by the window's top-left pixel."""
    total = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), np.int64)
    total[1:, 1:] = np.cumsum(np.cumsum(mask, axis=0, dtype=np.int64), axis=1)
    return (
        total[rows:, columns:]
        - total[:-rows, columns:]
        - total[rows:, :-columns]
        + total[:-rows, :-columns]
    )


def _ink_values(
    drawn: _Drawn, background: float, sigma: float, stored_range: tuple[int, int]
) -> tuple[float, float]:
    """The ink's stored value, and the opposite polarity's, for outlines,
    shadows, and boxes."""
    low, high = stored_range
    sign = 1.0 if drawn.polarity == "higher" else -1.0
    if drawn.contrast == SATURATED:
        ink = high if sign > 0 else low
        opposite = low if sign > 0 else high
        return float(ink), float(opposite)
    step = float(drawn.contrast) * sigma
    ink = min(high, max(low, background + sign * step))
    opposite = min(high, max(low, background - sign * step))
    return float(ink), float(opposite)


# The bins of the contrast that a text reached, in multiples of the noise.
CONTRAST = (0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)


def contrast_label(achieved: float) -> str:
    """The bin of :data:`CONTRAST` that holds a contrast."""
    low = max(edge for edge in CONTRAST if edge <= achieved)
    following = [edge for edge in CONTRAST if edge > low]
    if not following:
        return f"{low:g} sigma or more"
    return f"{low:g} to under {following[0]:g} sigma"


def _strata(drawn: _Drawn) -> dict[str, str]:
    contrast = drawn.contrast
    return {
        "font": drawn.font.name,
        "height": drawn.height_label,
        "contrast_drawn": (
            SATURATED if contrast == SATURATED else f"{float(contrast):g} sigma"
        ),
        "polarity": drawn.polarity,
        "style": drawn.style,
        "orientation": f"{drawn.orientation} degrees",
        "position": drawn.position,
        "content": drawn.content,
    }


ZONES = ("corner", "edge", "centre")
# The share of a frame's side, from each edge, that its edge zones span.
ZONE_SHARE = 0.15


def zone_of(box: TextBox, shape: tuple[int, int]) -> str:
    """Where a box's centre lies: ``"corner"`` within :data:`ZONE_SHARE`
    of two edges, ``"edge"`` of one, otherwise ``"centre"``. Text in real
    scans' annotations sits mostly at corners and edges, so regions that a
    collection without text gives there may be text that curation left."""
    row = (box.top + box.bottom) / 2 / shape[0]
    column = (box.left + box.right) / 2 / shape[1]
    near = sum(min(each, 1 - each) < ZONE_SHARE for each in (row, column))
    return ZONES[2 - near]
