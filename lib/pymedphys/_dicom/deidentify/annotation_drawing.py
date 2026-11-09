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

"""A drawing of one graphic annotation, for its review in the QC pack (D-062).

A reviewer decides whether to keep an item of Graphic Annotation Sequence
(0070,0001) from its text and from what its graphics draw, since a
polyline can spell a name as surely as a text object can.
:func:`draw_annotation` draws an item as received as a standalone SVG
document with no script, style sheet, or external reference:

- each graphic object of Graphic Object Sequence (0070,0009) by its Graphic
  Type (0070,0023): a POINT as a dot, a POLYLINE as a line through its
  points, an INTERPOLATED one as a line through its points, not the curve
  that a display interpolates, a CIRCLE by its centre and a point on it,
  and an ELLIPSE by the ends of its major and minor axes (PS3.3
  C.10.5.1.2);
- each compound graphic of Compound Graphic Sequence (0070,0209) as a
  dashed line through its Graphic Data (0070,0022), whatever its type,
  with its tick labels, which its text values also list;
- each text object of Text Object Sequence (0070,0008) as its text, at the
  top left corner of its bounding box or, without one, at its anchor
  point, with a line from the box to its anchor point where it has both.

Annotation units are PIXEL, in the image's pixels, or DISPLAY, in
fractions of the displayed area (C.10.5.1.1). Without the image, the two
cannot be put in one frame, so the drawing has a panel for each units
that the item uses: pixel units in a frame around what they draw, and
display units in the displayed area, 1000 units a side. Graphic Data that
is not two-dimensional, cannot be read, or holds a value that is not
finite is left out and counted in the drawing's caption, never guessed.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence
from xml.sax.saxutils import escape, quoteattr

from pymedphys._imports import pydicom

PIXEL = "PIXEL"
DISPLAY = "DISPLAY"
DISPLAY_SIDE = 1000.0
_PANEL = 400.0
_GAP = 24.0
_CAPTION = 20.0
_MARGIN = 0.05

Point = tuple[float, float]


@dataclasses.dataclass
class _Panel:
    """What one unit system draws, in its own coordinates."""

    shapes: list[str] = dataclasses.field(default_factory=list)
    points: list[Point] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class _Drawing:
    panels: dict[str, _Panel] = dataclasses.field(
        default_factory=lambda: {PIXEL: _Panel(), DISPLAY: _Panel()}
    )
    skipped: int = 0

    def panel(self, units: object) -> _Panel | None:
        if units not in (PIXEL, DISPLAY):
            self.skipped += 1
            return None
        return self.panels[str(units)]


def _number(value: float) -> str:
    """Return a coordinate as SVG text, the same for the same value."""
    text = f"{value:.6g}"
    return "0" if text == "-0" else text


def _points(
    item: pydicom.Dataset, keyword: str, count: int | None = None
) -> list[Point] | None:
    """Return an item's (column, row) points, or None if they cannot be drawn."""
    try:
        values = item[keyword].value
    except KeyError:
        return None
    if values is None:
        return None
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        values = [values]
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if (
        not numbers
        or len(numbers) % 2
        or not all(math.isfinite(number) for number in numbers)
    ):
        return None
    points = [
        (numbers[index], numbers[index + 1]) for index in range(0, len(numbers), 2)
    ]
    if count is not None and len(points) != count:
        return None
    return points


def _scaled(units: str, points: Iterable[Point]) -> list[Point]:
    factor = DISPLAY_SIDE if units == DISPLAY else 1.0
    return [(column * factor, row * factor) for column, row in points]


def _polyline(
    points: Sequence[Point], *, closed: bool = False, dashed: bool = False
) -> str:
    joined = " ".join(f"{_number(x)},{_number(y)}" for x, y in points)
    tag = "polygon" if closed else "polyline"
    dash = ' stroke-dasharray="4 3"' if dashed else ""
    return f'<{tag} points="{joined}" fill="none"{dash}/>'


def _graphic(drawing: _Drawing, graphic: pydicom.Dataset) -> None:
    panel = drawing.panel(graphic.get("GraphicAnnotationUnits"))
    if panel is None:
        return
    units = str(graphic.GraphicAnnotationUnits)
    kind = graphic.get("GraphicType")
    dimensions = graphic.get("GraphicDimensions", 2)
    points = _points(graphic, "GraphicData")
    if dimensions != 2 or points is None:
        drawing.skipped += 1
        return
    points = _scaled(units, points)
    if kind == "POINT" and len(points) == 1:
        x, y = points[0]
        panel.shapes.append(f'<circle cx="{_number(x)}" cy="{_number(y)}" r="2"/>')
    elif kind in ("POLYLINE", "INTERPOLATED") and len(points) >= 2:
        closed = points[0] == points[-1] and len(points) > 2
        panel.shapes.append(_polyline(points[:-1] if closed else points, closed=closed))
    elif kind == "CIRCLE" and len(points) == 2:
        (x, y), (edge_x, edge_y) = points
        radius = math.hypot(edge_x - x, edge_y - y)
        panel.shapes.append(
            f'<circle cx="{_number(x)}" cy="{_number(y)}" r="{_number(radius)}" fill="none"/>'
        )
        points = [(x - radius, y - radius), (x + radius, y + radius)]
    elif kind == "ELLIPSE" and len(points) == 4:
        panel.shapes.append(_ellipse(points))
    else:
        drawing.skipped += 1
        return
    panel.points.extend(points)


def _ellipse(points: Sequence[Point]) -> str:
    """Return an ellipse from the ends of its major then its minor axis."""
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = points
    centre_x, centre_y = (ax + bx) / 2, (ay + by) / 2
    major = math.hypot(bx - ax, by - ay) / 2
    minor = math.hypot(dx - cx, dy - cy) / 2
    angle = math.degrees(math.atan2(by - ay, bx - ax))
    return (
        f'<ellipse cx="{_number(centre_x)}" cy="{_number(centre_y)}" '
        f'rx="{_number(major)}" ry="{_number(minor)}" fill="none" '
        f'transform="rotate({_number(angle)} {_number(centre_x)} {_number(centre_y)})"/>'
    )


def _compound(drawing: _Drawing, compound: pydicom.Dataset) -> None:
    panel = drawing.panel(compound.get("GraphicAnnotationUnits"))
    if panel is None:
        return
    points = _points(compound, "GraphicData")
    if compound.get("GraphicDimensions", 2) != 2 or points is None:
        drawing.skipped += 1
        return
    points = _scaled(str(compound.GraphicAnnotationUnits), points)
    panel.shapes.append(
        _polyline(points, dashed=True)
        if len(points) > 1
        else (
            f'<circle cx="{_number(points[0][0])}" cy="{_number(points[0][1])}" r="2"/>'
        )
    )
    panel.points.extend(points)
    if len(points) < 2:
        return
    (start_x, start_y), (end_x, end_y) = points[0], points[-1]
    for tick in compound.get("MajorTicksSequence") or ():
        label = str(tick.get("TickLabel", "") or "").rstrip(" \x00")
        try:
            where = float(tick.get("TickPosition"))
        except (TypeError, ValueError):
            drawing.skipped += 1
            continue
        if not label or not math.isfinite(where):
            continue
        x = start_x + where * (end_x - start_x)
        y = start_y + where * (end_y - start_y)
        panel.shapes.append(_text(label, (x, y)))


def _text(value: str, at: Point) -> str:
    x, y = at
    return (
        f'<text x="{_number(x)}" y="{_number(y)}" stroke="none">{escape(value)}</text>'
    )


def _text_object(drawing: _Drawing, text: pydicom.Dataset) -> None:
    value = str(text.get("UnformattedTextValue", "") or "").rstrip(" \x00")
    box = _points(text, "BoundingBoxTopLeftHandCorner", 1)
    corner = _points(text, "BoundingBoxBottomRightHandCorner", 1)
    anchor = _points(text, "AnchorPoint", 1)
    box_panel = drawing.panel(text.get("BoundingBoxAnnotationUnits")) if box else None
    anchor_panel = (
        drawing.panel(text.get("AnchorPointAnnotationUnits")) if anchor else None
    )
    if box is None and anchor is None:
        drawing.skipped += 1
        return
    if box and box_panel is not None:
        units = str(text.BoundingBoxAnnotationUnits)
        top_left = _scaled(units, box)[0]
        box_panel.shapes.append(_text(value, (top_left[0], top_left[1] + 12)))
        box_panel.points.append(top_left)
        if corner:
            box_panel.points.append(_scaled(units, corner)[0])
        if anchor and anchor_panel is box_panel:
            point = _scaled(units, anchor)[0]
            box_panel.shapes.append(_polyline([top_left, point], dashed=True))
            box_panel.points.append(point)
    elif anchor and anchor_panel is not None:
        point = _scaled(str(text.AnchorPointAnnotationUnits), anchor)[0]
        anchor_panel.shapes.append(_text(value, point))
        anchor_panel.points.append(point)


def _frame(units: str, panel: _Panel) -> tuple[float, float, float, float]:
    """Return the panel's (x, y, width, height) in its own units."""
    if units == DISPLAY:
        return (0.0, 0.0, DISPLAY_SIDE, DISPLAY_SIDE)
    xs = [x for x, _ in panel.points]
    ys = [y for _, y in panel.points]
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    side = max(right - left, bottom - top, 1.0)
    pad = side * _MARGIN + 16
    return (left - pad, top - pad, side + 2 * pad, side + 2 * pad)


def draw_annotation(item: pydicom.Dataset) -> str:
    """Return an SVG drawing of one item of Graphic Annotation Sequence.

    Parameters
    ----------
    item : pydicom.Dataset
        The item as received.

    Returns
    -------
    str
        A standalone SVG document, as the module describes; the same for
        the same item.
    """
    drawing = _Drawing()
    for graphic in item.get("GraphicObjectSequence") or ():
        _graphic(drawing, graphic)
    for compound in item.get("CompoundGraphicSequence") or ():
        _compound(drawing, compound)
    for text in item.get("TextObjectSequence") or ():
        _text_object(drawing, text)
    drawn = [
        (units, panel)
        for units, panel in drawing.panels.items()
        if panel.shapes and panel.points
    ]
    width = max(len(drawn), 1) * (_PANEL + _GAP) + _GAP
    height = _PANEL + _CAPTION * 2 + _GAP
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{_number(width)}" height="{_number(height)}" '
        f'viewBox="0 0 {_number(width)} {_number(height)}">',
        f'<rect width="{_number(width)}" height="{_number(height)}" fill="white"/>',
    ]
    for index, (units, panel) in enumerate(drawn):
        x, y, frame_width, frame_height = _frame(units, panel)
        left = _GAP + index * (_PANEL + _GAP)
        parts.append(
            f'<text x="{_number(left)}" y="{_number(_CAPTION)}" '
            f'font-family="sans-serif" font-size="12">{units.lower()} units</text>'
        )
        parts.append(
            f'<svg x="{_number(left)}" y="{_number(_CAPTION + 4)}" '
            f'width="{_number(_PANEL)}" height="{_number(_PANEL)}" '
            f"viewBox={quoteattr(' '.join(_number(v) for v in (x, y, frame_width, frame_height)))} "
            'preserveAspectRatio="xMidYMid meet" overflow="hidden">'
        )
        parts.append(
            f'<rect x="{_number(x)}" y="{_number(y)}" width="{_number(frame_width)}" '
            f'height="{_number(frame_height)}" fill="#f4f4f4" stroke="#999" '
            'vector-effect="non-scaling-stroke"/>'
        )
        parts.append(
            '<g stroke="#c00" fill="#c00" stroke-width="1.5" '
            'vector-effect="non-scaling-stroke" font-family="sans-serif" '
            f'font-size="{_number(frame_height / 30)}">'
        )
        parts.extend(panel.shapes)
        parts.append("</g></svg>")
    caption = "nothing drawn" if not drawn else ""
    if drawing.skipped:
        caption = f"{caption}; " if caption else ""
        caption += f"{drawing.skipped} object(s) not drawn"
    if caption:
        parts.append(
            f'<text x="{_number(_GAP)}" y="{_number(height - _CAPTION / 2)}" '
            f'font-family="sans-serif" font-size="12">{escape(caption)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
