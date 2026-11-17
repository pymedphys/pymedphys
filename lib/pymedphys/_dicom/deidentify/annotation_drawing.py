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
  point, with a line from the box to its anchor point where it has both
  and its Anchor Point Visibility (0070,0015) is not N, since a display
  then shows no link to the anchor point (PS3.3 C.10.5.1.1); one whose
  visibility is neither Y nor N is drawn with the line and counted as not
  drawn whole;
- each closed graphic object or compound graphic that Graphic Filled
  (0070,0024) fills, shaded, and, where the Fill Mode (0070,0257) of its
  Fill Style Sequence (0070,0233) is STIPPELED, its Fill Pattern
  (0070,0256) in a panel of its own, each of its 32 x 32 bits magnified,
  the most significant bit of each row's four bytes leftmost (PS3.3
  C.10.5.1.3.14), since a pattern that a display tiles inside the object
  can spell a name as surely as a line can.

A line whose Line Style Sequence (0070,0232) makes it DASHED is drawn as a
solid line, and counted as not drawn whole. A display draws each set bit
of its 32-bit Line Pattern (0070,0255) in the foreground colour and each
clear bit in the background colour along the line (PS3.3 C.10.5.1.3.13),
but the standard says neither which bit comes first nor how long a bit is
along the line, so no drawing can show the dashes that a display draws,
and lines whose patterns are the rows of a bitmap can spell a name. A
pattern whose 32 bits are all the same draws the whole line in one
colour, so it hides nothing, and its line is drawn whole.

The drawing draws every object in one colour and opacity, at one
thickness, with no shadow, whatever its style. That hides nothing where
the objects of an annotation look alike, but objects that look different,
such as opaque and transparent strokes of one grid, can spell a name that
the drawing cannot show. So each graphic object and compound graphic
whose style, its Line Style Sequence (0070,0232) and Fill Style Sequence
(0070,0233) but for a fill's pattern, which is drawn, differs from that of
the item's first one is counted as not drawn whole, as is each text
object whose Text Style Sequence (0070,0231), its colour, opacity, and
shadow, differs from that of the first text object. A text object's other
elements, such as its justification, only place its text, which the text
values list, and a graphic's other elements, such as a compound
graphic's rotation, shape it, not how it shows.

Several annotations of one instance, those shown together on one frame of
one image, can be drawn as one (:func:`together`), since a name can be
split into strokes across them.
The drawing of them together is whole only where each is, where their
objects look alike across them, as within one, and where their graphic
layers show alike, by every element of Graphic Layer Sequence (0070,0060)
but a layer's name, order, and description (:func:`undrawn_together`).

Annotation units are PIXEL, in the image's pixels, or DISPLAY, in
fractions of the displayed area (C.10.5.1.1). Without the image, the two
cannot be put in one frame, so the drawing has a panel for each units
that the item uses: pixel units in a frame around what they draw, and
display units in the displayed area, 1000 units a side. A display draws
both on the one image, so objects in both, such as pixel-unit strokes and
display-unit strokes that spell a name together, are not shown as a
display shows them: each object placed in units other than the item's
first object's, and each text object whose bounding box and anchor point
are in different units, is counted as not drawn whole. Graphic Data that
is not two-dimensional, cannot be read, or holds a value that is not
finite, a fill whose mode or pattern cannot be read, and a line style
other than SOLID or a uniform DASHED one, are left out and counted in the
drawing's caption, never guessed; :func:`undrawn_objects` counts them, so
that an annotation with any is not released on a reviewer's decision to
keep it (D-062).

Text is escaped with :func:`html.escape`, which writes the same five
entities that SVG's XML needs; nothing here parses XML.
"""

from __future__ import annotations

import dataclasses
import html
import math
from collections.abc import Iterable, Mapping, Sequence

from pymedphys._imports import pydicom

PIXEL = "PIXEL"
DISPLAY = "DISPLAY"
DISPLAY_SIDE = 1000.0
_PANEL = 400.0
_GAP = 24.0
_CAPTION = 20.0
_MARGIN = 0.05
# A Fill Pattern's bitmap: 32 rows of 32 bits, four bytes a row.
FILL_PATTERN_SIDE = 32
_FILL_PATTERN_BYTES = FILL_PATTERN_SIDE * FILL_PATTERN_SIDE // 8
_FILLED_SHADE = 'fill-opacity="0.15"'
# The Line Patterns that draw a dashed line in one colour, all bits clear or
# all set, whose line a solid one shows whole.
_UNIFORM_LINE_PATTERNS = (0, 0xFFFFFFFF)
# The elements of a graphic layer that name or order it, which are not
# part of how it shows.
_LAYER_NAMING = frozenset(
    {"GraphicLayer", "GraphicLayerOrder", "GraphicLayerDescription"}
)
# The style sequences of a graphic object or compound graphic.
_STYLES = ("LineStyleSequence", "FillStyleSequence")
# The element of a style that the drawing draws: a fill's pattern, in a
# panel of its own.
_DRAWN = frozenset({"FillPattern"})

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
    # Each distinct Fill Pattern, in the order first drawn.
    patterns: list[bytes] = dataclasses.field(default_factory=list)

    def panel(self, units: object) -> _Panel | None:
        if units not in (PIXEL, DISPLAY):
            self.skipped += 1
            return None
        return self.panels[str(units)]


def _escape(value: str) -> str:
    """Return text escaped for SVG's character data or a quoted attribute."""
    return html.escape(value, quote=True)


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
    points: Sequence[Point],
    *,
    closed: bool = False,
    dashed: bool = False,
    fill: str = 'fill="none"',
) -> str:
    joined = " ".join(f"{_number(x)},{_number(y)}" for x, y in points)
    tag = "polygon" if closed else "polyline"
    dash = ' stroke-dasharray="4 3"' if dashed else ""
    return f'<{tag} points="{joined}" {fill}{dash}/>'


def _fill(drawing: _Drawing, graphic: pydicom.Dataset) -> str:
    """Return the fill attribute of a closed graphic, noting its pattern.

    An object that Graphic Filled does not fill is drawn as an outline. One
    that it fills is shaded; where its Fill Mode is STIPPELED, its Fill
    Pattern is kept for a panel of its own. A filled object whose Fill Mode
    is neither SOLID nor STIPPELED, or whose pattern is not 128 bytes, is
    counted as not drawn, though its outline is.
    """
    if graphic.get("GraphicFilled") != "Y":
        return 'fill="none"'
    styles = graphic.get("FillStyleSequence") or ()
    for style in styles:
        mode = style.get("FillMode")
        if mode == "STIPPELED":
            pattern = style.get("FillPattern")
            if (
                not isinstance(pattern, (bytes, bytearray))
                or len(pattern) != _FILL_PATTERN_BYTES
            ):
                drawing.skipped += 1
                continue
            if bytes(pattern) not in drawing.patterns:
                drawing.patterns.append(bytes(pattern))
        elif mode != "SOLID":
            drawing.skipped += 1
    return _FILLED_SHADE


def _line_style(drawing: _Drawing, graphic: pydicom.Dataset) -> None:
    """Count a line style whose line the drawing cannot show whole.

    The line itself is always drawn solid. A style is shown whole where its
    Line Dashing Style is SOLID, or DASHED with a Line Pattern whose bits
    are all the same; any other, including one that cannot be read, is
    counted as not drawn, as the module describes.
    """
    for style in graphic.get("LineStyleSequence") or ():
        dashing = style.get("LineDashingStyle")
        if dashing == "SOLID":
            continue
        pattern = style.get("LinePattern")
        if (
            dashing == "DASHED"
            and isinstance(pattern, int)
            and pattern in _UNIFORM_LINE_PATTERNS
        ):
            continue
        drawing.skipped += 1


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
        panel.shapes.append(
            _polyline(points[:-1], closed=True, fill=_fill(drawing, graphic))
            if closed
            else _polyline(points)
        )
    elif kind == "CIRCLE" and len(points) == 2:
        (x, y), (edge_x, edge_y) = points
        radius = math.hypot(edge_x - x, edge_y - y)
        panel.shapes.append(
            f'<circle cx="{_number(x)}" cy="{_number(y)}" r="{_number(radius)}" '
            f"{_fill(drawing, graphic)}/>"
        )
        points = [(x - radius, y - radius), (x + radius, y + radius)]
    elif kind == "ELLIPSE" and len(points) == 4:
        panel.shapes.append(_ellipse(points, _fill(drawing, graphic)))
    else:
        drawing.skipped += 1
        return
    _line_style(drawing, graphic)
    panel.points.extend(points)


def _ellipse(points: Sequence[Point], fill: str = 'fill="none"') -> str:
    """Return an ellipse from the ends of its major then its minor axis."""
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = points
    centre_x, centre_y = (ax + bx) / 2, (ay + by) / 2
    major = math.hypot(bx - ax, by - ay) / 2
    minor = math.hypot(dx - cx, dy - cy) / 2
    angle = math.degrees(math.atan2(by - ay, bx - ax))
    return (
        f'<ellipse cx="{_number(centre_x)}" cy="{_number(centre_y)}" '
        f'rx="{_number(major)}" ry="{_number(minor)}" {fill} '
        f'transform="rotate({_number(angle)} {_number(centre_x)} {_number(centre_y)})"/>'
    )


def _compound(drawing: _Drawing, compound: pydicom.Dataset) -> None:
    """Draw a compound graphic in the units of Compound Graphic Units."""
    panel = drawing.panel(compound.get("CompoundGraphicUnits"))
    if panel is None:
        return
    points = _points(compound, "GraphicData")
    if compound.get("GraphicDimensions", 2) != 2 or points is None:
        drawing.skipped += 1
        return
    points = _scaled(str(compound.CompoundGraphicUnits), points)
    fill = _fill(drawing, compound)
    panel.shapes.append(
        _polyline(points, dashed=True, closed=fill != 'fill="none"', fill=fill)
        if len(points) > 1
        else (
            f'<circle cx="{_number(points[0][0])}" cy="{_number(points[0][1])}" r="2"/>'
        )
    )
    _line_style(drawing, compound)
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
        f'<text x="{_number(x)}" y="{_number(y)}" stroke="none">{_escape(value)}</text>'
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
            visibility = str(text.get("AnchorPointVisibility", "") or "").strip()
            point = _scaled(units, anchor)[0]
            box_panel.points.append(point)
            if visibility != "N":
                box_panel.shapes.append(_polyline([top_left, point], dashed=True))
            if visibility not in ("Y", "N"):
                # Whether a display shows the anchor is not known.
                drawing.skipped += 1
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


def _appearance(dataset: pydicom.Dataset, drawn: frozenset[str] = _DRAWN) -> tuple:
    """Return what of an object the drawing does not draw, to compare.

    Each element but those in ``drawn`` and UIDs, by tag, with its items'
    appearances or its value's text, so that two objects that look alike
    have the same appearance.
    """
    parts = []
    for element in dataset:
        if element.keyword in drawn or element.VR == "UI":
            continue
        if element.VR == "SQ":
            value: object = tuple(_appearance(item) for item in element.value or ())
        elif isinstance(element.value, (bytes, bytearray)):
            value = bytes(element.value).hex()
        else:
            value = repr(element.value)
        parts.append((int(element.tag), value))
    return tuple(parts)


def _appearance_of(dataset: pydicom.Dataset, keywords: Sequence[str]) -> tuple:
    """Return the appearances of the items of an object's style sequences."""
    return tuple(
        (keyword, tuple(_appearance(item) for item in dataset.get(keyword) or ()))
        for keyword in keywords
    )


def _style(graphic: pydicom.Dataset) -> tuple:
    """Return a graphic object's or compound graphic's style, to compare."""
    return _appearance_of(graphic, _STYLES)


def _unlike(appearances: Sequence[tuple]) -> int:
    """Return how many objects look different from the first of them."""
    return sum(each != appearances[0] for each in appearances[1:])


def _placed(dataset: pydicom.Dataset, keywords: Sequence[tuple[str, str]]) -> tuple:
    """Return the units, PIXEL or DISPLAY, that an object is placed in.

    ``keywords`` pairs each element that places the object with the element
    that gives its units; an element that is absent places nothing, and
    units that the drawing cannot draw are counted where it draws.
    """
    return tuple(
        units
        for where, keyword in keywords
        if dataset.get(where) is not None
        and (units := dataset.get(keyword)) in (PIXEL, DISPLAY)
    )


_PLACING = {
    "GraphicObjectSequence": (("GraphicData", "GraphicAnnotationUnits"),),
    "CompoundGraphicSequence": (("GraphicData", "CompoundGraphicUnits"),),
    "TextObjectSequence": (
        ("BoundingBoxTopLeftHandCorner", "BoundingBoxAnnotationUnits"),
        ("AnchorPoint", "AnchorPointAnnotationUnits"),
    ),
}


def _unregistered(item: pydicom.Dataset) -> int:
    """Return how many objects are placed in units other than the first's.

    Pixel and display units cannot be put in one frame without the image
    and its displayed area, so they are drawn in panels of their own, and
    strokes split between them, each a fragment, can spell a name that a
    display shows on the one image. Each object placed in units other than
    those that the item's first object is first placed in, including a text
    object whose bounding box and anchor point are in different units, is
    counted.
    """
    placed = [
        _placed(each, keywords)
        for keyword, keywords in _PLACING.items()
        for each in item.get(keyword) or ()
    ]
    first = next((units[0] for units in placed if units), None)
    return sum(any(units != first for units in each) for each in placed)


def _draw(item: pydicom.Dataset) -> _Drawing:
    drawing = _Drawing()
    drawing.skipped += _unregistered(item)
    drawing.skipped += _unlike(
        [
            _style(graphic)
            for keyword in ("GraphicObjectSequence", "CompoundGraphicSequence")
            for graphic in item.get(keyword) or ()
        ]
    )
    drawing.skipped += _unlike(
        [
            _appearance_of(text, ("TextStyleSequence",))
            for text in item.get("TextObjectSequence") or ()
        ]
    )
    for graphic in item.get("GraphicObjectSequence") or ():
        _graphic(drawing, graphic)
    for compound in item.get("CompoundGraphicSequence") or ():
        _compound(drawing, compound)
    for text in item.get("TextObjectSequence") or ():
        _text_object(drawing, text)
    return drawing


def together(items: Sequence[pydicom.Dataset]) -> pydicom.Dataset:
    """Return one item that holds every object of ``items``, in their order.

    Its drawing (:func:`draw_annotation`) draws the annotations as one, so
    that strokes split across them show as a display shows them together.
    """
    merged = pydicom.Dataset()
    for keyword in (
        "GraphicObjectSequence",
        "CompoundGraphicSequence",
        "TextObjectSequence",
    ):
        objects = [each for item in items for each in item.get(keyword) or ()]
        if objects:
            setattr(merged, keyword, objects)
    return merged


def layer_appearances(dataset: pydicom.Dataset) -> dict[str, tuple]:
    """Return how each graphic layer of an instance shows, by its name.

    Every element of each item of Graphic Layer Sequence (0070,0060) but its
    name, order, and description, such as its recommended display grayscale
    or CIELab value, which the drawing does not draw.
    """
    layers: dict[str, tuple] = {}
    for layer in dataset.get("GraphicLayerSequence") or ():
        name = str(layer.get("GraphicLayer", "") or "").rstrip(" \x00")
        layers[name] = _appearance(layer, _LAYER_NAMING)
    return layers


def undrawn_together(
    items: Sequence[pydicom.Dataset], layers: Mapping[str, tuple]
) -> int:
    """Return how much the drawing of annotations as one leaves out.

    The drawing draws every object in one colour and opacity, whatever its
    annotation or layer, so as well as what it leaves out of each
    annotation (:func:`undrawn_objects`), each object that looks different
    from the first of its kind among all of them, or is placed in units
    other than the first object's, and each annotation on a
    layer that shows differently from the first annotation's, is counted:
    strokes split across annotations, in different styles or layers, can
    spell a name that the drawing hides.

    Parameters
    ----------
    items : sequence of pydicom.Dataset
        The annotations shown together, as received.
    layers : mapping of str to tuple
        How each of the instance's layers shows (:func:`layer_appearances`).
    """
    shown = [
        layers.get(str(item.get("GraphicLayer", "") or "").rstrip(" \x00"))
        for item in items
    ]
    return undrawn_objects(together(items)) + sum(
        each != shown[0] for each in shown[1:]
    )


def undrawn_objects(item: pydicom.Dataset) -> int:
    """Return how many of an annotation's objects its drawing leaves out.

    Parameters
    ----------
    item : pydicom.Dataset
        An item of Graphic Annotation Sequence as received.

    Returns
    -------
    int
        The count that :func:`draw_annotation`'s caption gives: each object
        whose units, type, or Graphic Data cannot be drawn, each fill
        whose mode or pattern cannot be read, each line style other than
        SOLID or a uniform DASHED one, and each object that looks different
        from the item's first of its kind in a way that the drawing does
        not draw. A reviewer has not seen an annotation whole where this is
        not 0.
    """
    return _draw(item).skipped


def _pattern_rows(pattern: bytes) -> list[str]:
    """Return a Fill Pattern's set bits as one SVG rect for each run in a row.

    Row ``r`` is bytes ``4r`` to ``4r + 3``, the most significant bit of each
    leftmost (PS3.3 C.10.5.1.3.14).
    """
    rects = []
    row_bytes = FILL_PATTERN_SIDE // 8
    for row in range(FILL_PATTERN_SIDE):
        bits = int.from_bytes(pattern[row * row_bytes : (row + 1) * row_bytes], "big")
        column = 0
        while column < FILL_PATTERN_SIDE:
            if bits >> (FILL_PATTERN_SIDE - 1 - column) & 1:
                start = column
                while (
                    column < FILL_PATTERN_SIDE
                    and bits >> (FILL_PATTERN_SIDE - 1 - column) & 1
                ):
                    column += 1
                rects.append(
                    f'<rect x="{start}" y="{row}" width="{column - start}" height="1"/>'
                )
            else:
                column += 1
    return rects


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
    drawing = _draw(item)
    drawn = [
        (units, panel)
        for units, panel in drawing.panels.items()
        if panel.shapes and panel.points
    ]
    panels = len(drawn) + len(drawing.patterns)
    width = max(panels, 1) * (_PANEL + _GAP) + _GAP
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
            f'viewBox="{_escape(" ".join(_number(v) for v in (x, y, frame_width, frame_height)))}" '
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
    for number, pattern in enumerate(drawing.patterns, start=1):
        left = _GAP + (len(drawn) + number - 1) * (_PANEL + _GAP)
        side = FILL_PATTERN_SIDE
        parts.append(
            f'<text x="{_number(left)}" y="{_number(_CAPTION)}" '
            f'font-family="sans-serif" font-size="12">fill pattern {number}, '
            "tiled inside its object</text>"
        )
        parts.append(
            f'<svg x="{_number(left)}" y="{_number(_CAPTION + 4)}" '
            f'width="{_number(_PANEL)}" height="{_number(_PANEL)}" '
            f'viewBox="0 0 {side} {side}" preserveAspectRatio="xMidYMid meet" '
            'shape-rendering="crispEdges">'
        )
        parts.append(
            f'<rect width="{side}" height="{side}" fill="#f4f4f4" stroke="#999" '
            'stroke-width="0.05"/>'
        )
        parts.append('<g fill="#c00">')
        parts.extend(_pattern_rows(pattern))
        parts.append("</g></svg>")
    caption = "nothing drawn" if not panels else ""
    if drawing.skipped:
        caption = f"{caption}; " if caption else ""
        caption += f"{drawing.skipped} object(s) not drawn whole"
    if caption:
        parts.append(
            f'<text x="{_number(_GAP)}" y="{_number(height - _CAPTION / 2)}" '
            f'font-family="sans-serif" font-size="12">{_escape(caption)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
