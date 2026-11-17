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

"""Graphic annotations of Presentation States, released as a reviewer decides (D-062).

Under the Clean Graphics Option, with the custodian's reviewed annotations
list, each item of Graphic Annotation Sequence (0070,0001) is kept, removed,
or held for review by the reviewer's decision on its digest, and the QC
pack shows each with its text and a drawing of its graphics. Every file is
synthetic. Values that must never reach a written file carry the text
``SENTINEL``.
"""

# The tests share the annotation and list builders below, so they stay in
# one module.
# pylint: disable = too-many-lines

import copy
import io
import json
import math
import re
import xml.dom.minidom

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    method_digest,
    policy,
    qc_pack,
    release_report,
    reviewed_annotations_command,
    risk_assessment,
    run,
)
from pymedphys._dicom.deidentify.annotation_drawing import (
    draw_annotation,
    together,
    undrawn_objects,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.graphic_annotations import AnnotationMaterial
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import PolicyError
from pymedphys._dicom.deidentify.qc_pack import AnnotationEntry, QcPack, QcPackError
from pymedphys._dicom.deidentify.reasons import HeldAnnotation
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_report_markdown import to_markdown
from pymedphys._dicom.deidentify.reviewed_annotations import (
    Held,
    Outcome,
    Review,
    ReviewedAnnotations,
    ReviewedAnnotationsError,
    annotation_digest,
    annotation_texts,
    together_digest,
)
from pymedphys._dicom.deidentify.run_report import annotation_counts
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.1"
GRAPHIC_ANNOTATION_SEQUENCE = "(0070,0001)"
CLEAN_GRAPHICS = "clean_graphics"
MODIFIED_DATES = "retain_longitudinal_modified_dates"
OPTIONS = (MODIFIED_DATES, CLEAN_GRAPHICS)
ARROW_TEXT = "LESION 1"
RULER_TEXT = "SENTINEL RULER"


def _arrow():
    """An annotation of a reviewer's arrow and its label, on the first CT slice."""
    return synthetic.item(
        GraphicLayer="LAYER",
        ReferencedImageSequence=[
            synthetic.reference(synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[0])
        ],
        TextObjectSequence=[
            synthetic.item(
                BoundingBoxAnnotationUnits="PIXEL",
                BoundingBoxTopLeftHandCorner=[10.0, 10.0],
                BoundingBoxBottomRightHandCorner=[60.0, 20.0],
                BoundingBoxTextHorizontalJustification="LEFT",
                AnchorPointAnnotationUnits="PIXEL",
                AnchorPoint=[80.0, 40.0],
                AnchorPointVisibility="Y",
                UnformattedTextValue=ARROW_TEXT,
            )
        ],
        GraphicObjectSequence=[
            synthetic.item(
                GraphicAnnotationUnits="PIXEL",
                GraphicDimensions=2,
                NumberOfGraphicPoints=2,
                GraphicData=[60.0, 20.0, 80.0, 40.0],
                GraphicType="POLYLINE",
                GraphicFilled="N",
            )
        ],
    )


def _ruler(text=RULER_TEXT, units="DISPLAY"):
    """An annotation of a measurement, whose label stands in for a name."""
    return synthetic.item(
        GraphicLayer="LAYER",
        TextObjectSequence=[
            synthetic.item(
                AnchorPointAnnotationUnits=units,
                AnchorPoint=[0.5, 0.5],
                AnchorPointVisibility="N",
                UnformattedTextValue=text,
            )
        ],
    )


# Lettering that a Fill Pattern's bits spell, top rows first, each row's
# leftmost character its most significant bit (PS3.3 C.10.5.1.3.14).
LETTERING = (
    "#...#.###",
    "#...#..#.",
    "#####..#.",
    "#...#..#.",
    "#...#.###",
)


def _pattern(rows=LETTERING):
    """Return a 128-byte Fill Pattern whose set bits are the ``#`` of ``rows``."""
    rows = [row.ljust(32, ".") for row in rows]
    rows += ["." * 32] * (32 - len(rows))
    return b"".join(
        int(row.replace("#", "1").replace(".", "0"), 2).to_bytes(4, "big")
        for row in rows
    )


def _filled(mode="STIPPELED", pattern=None):
    """An annotation of a filled square, whose fill can carry lettering."""
    style = synthetic.item(FillMode=mode)
    if pattern is not None:
        style.FillPattern = pattern
    return synthetic.item(
        GraphicLayer="LAYER",
        ReferencedImageSequence=[
            synthetic.reference(synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[0])
        ],
        GraphicObjectSequence=[
            synthetic.item(
                GraphicAnnotationUnits="PIXEL",
                GraphicDimensions=2,
                NumberOfGraphicPoints=5,
                GraphicData=[1.0, 1.0, 40.0, 1.0, 40.0, 40.0, 1.0, 40.0, 1.0, 1.0],
                GraphicType="POLYLINE",
                GraphicFilled="Y",
                FillStyleSequence=[style],
            )
        ],
    )


def _bitmap(drawing):
    """Return the rows of the drawing's first fill pattern panel as ``#`` and ``.``."""
    document = xml.dom.minidom.parseString(drawing)
    (panel,) = [
        each
        for each in document.getElementsByTagName("svg")
        if each.getAttribute("viewBox") == "0 0 32 32"
    ]
    rows = [["."] * 32 for _ in range(32)]
    for group in panel.getElementsByTagName("g"):
        for rect in group.getElementsByTagName("rect"):
            x, y = int(rect.getAttribute("x")), int(rect.getAttribute("y"))
            for column in range(x, x + int(rect.getAttribute("width"))):
                rows[y][column] = "#"
    return ["".join(row) for row in rows]


def _line_patterns(rows=LETTERING):
    """Return a 32-bit Line Pattern for each row, its ``#`` the set bits."""
    return [
        int(row.ljust(32, ".").replace("#", "1").replace(".", "0"), 2) for row in rows
    ]


def _lined(patterns, dashing="DASHED", opacities=None):
    """An annotation of one horizontal line a row for each pattern.

    Where each line's Line Pattern is a row of lettering, a display that
    dashes the lines can spell it down the stack of lines. ``opacities``
    gives each line's Pattern On Opacity, 1 by default.
    """
    objects = []
    opacities = opacities or [1.0] * len(patterns)
    for row, (pattern, opacity) in enumerate(zip(patterns, opacities), start=1):
        style = synthetic.item(
            PatternOnColorCIELabValue=[65535, 32896, 32896],
            PatternOnOpacity=opacity,
            LineThickness=1.0,
            LineDashingStyle=dashing,
            ShadowStyle="OFF",
            ShadowOffsetX=0.0,
            ShadowOffsetY=0.0,
            ShadowColorCIELabValue=[0, 32896, 32896],
            ShadowOpacity=0.0,
        )
        if pattern is not None:
            style.LinePattern = pattern
        objects.append(
            synthetic.item(
                GraphicAnnotationUnits="PIXEL",
                GraphicDimensions=2,
                NumberOfGraphicPoints=2,
                GraphicData=[1.0, float(row), 64.0, float(row)],
                GraphicType="POLYLINE",
                LineStyleSequence=[style],
            )
        )
    return synthetic.item(
        GraphicLayer="LAYER",
        ReferencedImageSequence=[
            synthetic.reference(synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[0])
        ],
        GraphicObjectSequence=objects,
    )


def _presentation_state(*annotations, slices=1):
    dataset = synthetic.instance(
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        "2.25.701",
        "2.25.700",
        ReferencedSeriesSequence=[
            synthetic.item(
                SeriesInstanceUID=synthetic.CT_SERIES,
                ReferencedImageSequence=[
                    synthetic.reference(synthetic.CT_IMAGE_STORAGE, uid)
                    for uid in synthetic.CT_SLICES[:slices]
                ],
            )
        ],
    )
    dataset.Modality = "PR"
    dataset.InstanceNumber = 1
    dataset.ContentLabel = "ANNOTATED"
    dataset.ContentCreatorName = "SENTINEL^CREATOR"
    dataset.PresentationCreationDate = "20240305"
    dataset.PresentationCreationTime = "101500"
    dataset.DisplayedAreaSelectionSequence = [
        synthetic.item(
            DisplayedAreaTopLeftHandCorner=[1, 1],
            DisplayedAreaBottomRightHandCorner=[2, 2],
            PresentationSizeMode="SCALE TO FIT",
            PresentationPixelSpacing=["1", "1"],
        )
    ]
    dataset.PresentationLUTShape = "IDENTITY"
    dataset.GraphicLayerSequence = [
        synthetic.item(GraphicLayer="LAYER", GraphicLayerOrder=1)
    ]
    dataset.GraphicAnnotationSequence = list(annotations)
    return dataset


def _reviewed(**decisions):
    reviewed = ReviewedAnnotations.empty()
    for digest, review in decisions.values():
        reviewed.record(digest, review)
    return reviewed


def _transformed(dataset, reviewed, options=OPTIONS):
    transform = InstanceTransform(
        policy.compose_custom_policy(list(options)),
        KEY,
        reviewed_annotations=reviewed,
        unvalidated_policy=True,
    )
    data = synthetic.written(dataset)
    return transform, transform(data, InstanceRecord.from_file(data))


def _material(result):
    return [each for each in result.qc if isinstance(each, AnnotationMaterial)]


# The digest and the text that a reviewer reads


def test_an_annotations_digest_leaves_out_its_uids_and_nothing_else():
    arrow = _arrow()
    elsewhere = _arrow()
    elsewhere.ReferencedImageSequence[0].ReferencedSOPInstanceUID = "2.25.9"
    relabelled = _arrow()
    relabelled.TextObjectSequence[0].UnformattedTextValue = "LESION 2"
    moved = _arrow()
    moved.GraphicObjectSequence[0].GraphicData = [60.0, 20.0, 80.0, 41.0]

    digest = annotation_digest(arrow)

    assert len(digest) == 64 and digest == digest.lower()
    # The decision on an annotation applies wherever it is drawn, such as on
    # the same slice after its UIDs are replaced.
    assert annotation_digest(elsewhere) == digest
    assert annotation_digest(relabelled) != digest
    assert annotation_digest(moved) != digest


def test_an_annotations_texts_are_its_text_values_at_any_depth():
    # In file order: the layer, the text object's units, text, justification,
    # and anchor visibility, and the graphic object's units, type, and fill;
    # the UIDs of its image reference and its numbers are not text.
    assert annotation_texts(_arrow()) == (
        "LAYER",
        "PIXEL",
        "PIXEL",
        ARROW_TEXT,
        "LEFT",
        "Y",
        "PIXEL",
        "POLYLINE",
        "N",
    )
    assert annotation_texts(_ruler()) == ("LAYER", "DISPLAY", RULER_TEXT, "N")


def test_the_list_keeps_its_decisions_and_refuses_a_malformed_digest(tmp_path):
    path = tmp_path / "custodian" / "annotations.json"
    path.parent.mkdir()
    reviewed = ReviewedAnnotations.open(path)
    arrow, ruler = annotation_digest(_arrow()), annotation_digest(_ruler())
    reviewed.record(arrow, Review.KEEP)
    reviewed.record(ruler, Review.REMOVE)
    reviewed.save()

    reopened = ReviewedAnnotations.open(path)
    assert (reopened.get(arrow), reopened.get(ruler)) == (Review.KEEP, Review.REMOVE)
    assert reopened.canonical_bytes() == reviewed.canonical_bytes()
    with pytest.raises(ReviewedAnnotationsError) as raised:
        reviewed.record(arrow, Review.REMOVE)
    assert arrow not in str(raised.value)
    with pytest.raises(ReviewedAnnotationsError):
        reviewed.record(arrow.upper(), Review.KEEP)


# The transform


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_without_a_list_a_presentation_state_with_annotations_is_sequestered():
    _, result = _transformed(_presentation_state(_arrow()), None)

    assert isinstance(result, run.Sequestered)
    assert (
        Sequestration(
            ElementPath((), GRAPHIC_ANNOTATION_SEQUENCE),
            "D",
            "SQ",
            SequesterReason.NO_DUMMY_VALUE,
        )
        in result.reasons
    )


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_an_annotation_that_the_list_keeps_is_written_but_for_its_uids():
    reviewed = _reviewed(arrow=(annotation_digest(_arrow()), Review.KEEP))

    _, result = _transformed(_presentation_state(_arrow()), reviewed)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    (annotation,) = written.GraphicAnnotationSequence
    (text,) = annotation.TextObjectSequence
    assert text.UnformattedTextValue == ARROW_TEXT
    assert text.AnchorPoint == [80.0, 40.0]
    (graphic,) = annotation.GraphicObjectSequence
    assert graphic.GraphicData == [60.0, 20.0, 80.0, 40.0]
    (image,) = annotation.ReferencedImageSequence
    (series,) = written.ReferencedSeriesSequence
    # Its image reference is replaced as the Presentation State's own is.
    assert image.ReferencedSOPInstanceUID != synthetic.CT_SLICES[0]
    assert (
        image.ReferencedSOPInstanceUID
        == series.ReferencedImageSequence[0].ReferencedSOPInstanceUID
    )
    assert b"SENTINEL" not in result.data
    (material,) = _material(result)
    assert material.result.outcome is Outcome.KEPT


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_an_annotation_that_the_list_removes_is_removed_with_everything_in_it():
    reviewed = _reviewed(
        arrow=(annotation_digest(_arrow()), Review.KEEP),
        ruler=(annotation_digest(_ruler()), Review.REMOVE),
    )

    _, result = _transformed(_presentation_state(_ruler(), _arrow()), reviewed)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    (annotation,) = written.GraphicAnnotationSequence
    assert annotation.TextObjectSequence[0].UnformattedTextValue == ARROW_TEXT
    assert b"SENTINEL" not in result.data
    assert [each.result.outcome for each in _material(result)] == [
        Outcome.REMOVED,
        Outcome.KEPT,
    ]


def test_a_presentation_state_whose_annotations_are_all_removed_is_sequestered():
    # Graphic Annotation Sequence is Type 1, so it cannot be left empty.
    reviewed = _reviewed(ruler=(annotation_digest(_ruler()), Review.REMOVE))

    _, result = _transformed(_presentation_state(_ruler()), reviewed)

    assert isinstance(result, run.Sequestered)
    assert (
        Sequestration(
            ElementPath((), GRAPHIC_ANNOTATION_SEQUENCE),
            "D",
            "SQ",
            SequesterReason.NO_DUMMY_VALUE,
        )
        in result.reasons
    )


def test_an_annotation_without_a_decision_holds_its_instance_for_review():
    reviewed = _reviewed(arrow=(annotation_digest(_arrow()), Review.KEEP))

    # The ruler in the arrow's units, so that the two are drawn as one.
    transform, result = _transformed(
        _presentation_state(_arrow(), _ruler(units="PIXEL")), reviewed
    )

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    arrow, ruler = (
        ElementPath(
            ((GRAPHIC_ANNOTATION_SEQUENCE, index),), GRAPHIC_ANNOTATION_SEQUENCE
        )
        for index in (0, 1)
    )
    # The kept arrow waits on a decision on the two together too.
    assert getattr(result.evidence, "held") == (
        HeldAnnotation(arrow, Held.NOT_REVIEWED_TOGETHER),
        HeldAnnotation(ruler, Held.NOT_REVIEWED),
    )
    # The staged file carries no unreviewed text.
    assert b"SENTINEL" not in result.data
    held = [
        each
        for each in _material(result)
        if each.result.outcome is Outcome.HELD and not each.together
    ]
    assert [each.texts for each in held] == [
        annotation_texts(_arrow()),
        annotation_texts(_ruler(units="PIXEL")),
    ]
    assert "SENTINEL" not in repr(held)
    assert {pending.digest for pending in transform.annotation_queue.entries()} == {
        annotation_digest(_arrow()),
        annotation_digest(_ruler(units="PIXEL")),
    }


def test_a_kept_annotation_that_names_the_patient_is_held():
    named = _ruler(synthetic.PATIENTS_NAME)
    reviewed = _reviewed(named=(annotation_digest(named), Review.KEEP))

    _, result = _transformed(_presentation_state(named), reviewed)

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    (held,) = getattr(result.evidence, "held")
    assert held.reason is Held.ECHOES_IDENTIFIER
    assert synthetic.PATIENTS_NAME.encode() not in result.data


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_a_kept_annotation_whose_fill_the_drawing_shows_is_written():
    filled = _filled(pattern=_pattern())
    reviewed = _reviewed(filled=(annotation_digest(filled), Review.KEEP))

    _, result = _transformed(_presentation_state(filled), reviewed)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    (graphic,) = written.GraphicAnnotationSequence[0].GraphicObjectSequence
    assert graphic.FillStyleSequence[0].FillPattern == _pattern()
    (material,) = _material(result)
    assert material.result.outcome is Outcome.KEPT


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
@pytest.mark.parametrize(
    "annotation",
    [
        # A pattern that is not 32 x 32 bits cannot be drawn as a display
        # would tile it.
        _filled(pattern=_pattern()[:64]),
        # Nor can a fill mode that PS3.3 does not define.
        _filled(mode="HATCHED"),
    ],
)
def test_a_kept_annotation_that_its_drawing_leaves_out_is_held(annotation):
    # The reviewer decided without seeing it whole, so the decision cannot
    # release it.
    reviewed = _reviewed(annotation=(annotation_digest(annotation), Review.KEEP))

    _, result = _transformed(_presentation_state(annotation), reviewed)

    assert undrawn_objects(annotation) == 1
    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    (held,) = getattr(result.evidence, "held")
    assert held.reason is Held.NOT_DRAWN
    (material,) = _material(result)
    assert material.result.held_because is Held.NOT_DRAWN


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
@pytest.mark.parametrize(
    "annotation, undrawn",
    [
        # Each line dashed by a row of lettering: the standard says neither
        # which bit comes first nor how long a bit is along the line, so no
        # drawing can show what a display dashes. Each of the five is
        # dashed, and the three whose pattern differs from the first line's
        # look different from it too.
        (_lined(_line_patterns()), 8),
        # A dashed line without its Line Pattern, Type 1C here.
        (_lined([None]), 1),
        # A dashing style that PS3.3 does not define.
        (_lined([0xFFFFFFFF], dashing="DOTTED"), 1),
    ],
)
def test_a_kept_annotation_with_a_dashed_line_is_held(annotation, undrawn):
    reviewed = _reviewed(annotation=(annotation_digest(annotation), Review.KEEP))

    _, result = _transformed(_presentation_state(annotation), reviewed)

    assert undrawn_objects(annotation) == undrawn
    assert f"{undrawn} object(s) not drawn whole" in draw_annotation(annotation)
    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    (held,) = getattr(result.evidence, "held")
    assert held.reason is Held.NOT_DRAWN
    (material,) = _material(result)
    assert material.result.held_because is Held.NOT_DRAWN


def test_dashed_lines_of_different_patterns_have_different_digests():
    # A decision on one pattern is never taken for another, though both
    # are held.
    lettered = _lined(_line_patterns())
    blank = _lined([0] * len(LETTERING))

    assert annotation_digest(lettered) != annotation_digest(blank)


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
@pytest.mark.parametrize(
    "patterns, dashing",
    [
        ([None] * len(LETTERING), "SOLID"),
        # A pattern whose bits are all the same dashes the whole line in one
        # colour, so the line drawn solid shows all of it.
        ([0xFFFFFFFF] * len(LETTERING), "DASHED"),
        ([0] * len(LETTERING), "DASHED"),
    ],
)
def test_a_kept_annotation_whose_lines_the_drawing_shows_is_written(patterns, dashing):
    annotation = _lined(patterns, dashing=dashing)
    reviewed = _reviewed(annotation=(annotation_digest(annotation), Review.KEEP))

    _, result = _transformed(_presentation_state(annotation), reviewed)

    assert undrawn_objects(annotation) == 0
    assert "not drawn" not in draw_annotation(annotation)
    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    graphics = written.GraphicAnnotationSequence[0].GraphicObjectSequence
    assert [graphic.LineStyleSequence[0].LineDashingStyle for graphic in graphics] == [
        dashing
    ] * len(LETTERING)
    assert [
        graphic.LineStyleSequence[0].get("LinePattern") for graphic in graphics
    ] == (patterns)
    (material,) = _material(result)
    assert material.result.outcome is Outcome.KEPT


# Rows of a grid of solid strokes, 1 where a stroke is opaque and 0 where it
# is transparent, which spell lettering that a display shows and a drawing
# in one opacity hides.
OPACITY_MASK = ("10001011", "10001001", "11111001", "10001001", "10001011")


def _grid(mask=OPACITY_MASK):
    """An annotation of a solid stroke for each cell of ``mask``, opaque at 1."""
    objects = []
    for row, cells in enumerate(mask):
        for column, cell in enumerate(cells):
            objects.append(
                synthetic.item(
                    GraphicAnnotationUnits="PIXEL",
                    GraphicDimensions=2,
                    NumberOfGraphicPoints=2,
                    GraphicData=[
                        float(column * 4),
                        float(row * 4),
                        float(column * 4 + 3),
                        float(row * 4),
                    ],
                    GraphicType="POLYLINE",
                    LineStyleSequence=[
                        synthetic.item(
                            PatternOnColorCIELabValue=[65535, 32896, 32896],
                            PatternOnOpacity=float(cell),
                            LineThickness=1.0,
                            LineDashingStyle="SOLID",
                            ShadowStyle="OFF",
                            ShadowOffsetX=0.0,
                            ShadowOffsetY=0.0,
                            ShadowColorCIELabValue=[0, 32896, 32896],
                            ShadowOpacity=0.0,
                        )
                    ],
                )
            )
    return synthetic.item(
        GraphicLayer="LAYER",
        ReferencedImageSequence=[
            synthetic.reference(synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[0])
        ],
        GraphicObjectSequence=objects,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_strokes_whose_opacity_spells_lettering_are_held():
    # The drawing draws every stroke in one opacity, so the lettering that
    # the transparent strokes leave is not shown: the grid's drawing is the
    # same as an opaque grid's. Each stroke that looks different from the
    # first is counted, and a keep decision cannot release it.
    lettered = _grid()
    opaque = _grid(tuple("1" * 8 for _ in OPACITY_MASK))
    reviewed = _reviewed(annotation=(annotation_digest(lettered), Review.KEEP))

    _, result = _transformed(_presentation_state(lettered), reviewed)

    unlike_first = sum(
        cell != OPACITY_MASK[0][0] for row in OPACITY_MASK for cell in row
    )
    assert undrawn_objects(lettered) == unlike_first
    assert undrawn_objects(opaque) == 0
    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    (held,) = getattr(result.evidence, "held")
    assert held.reason is Held.NOT_DRAWN


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_a_kept_grid_of_alike_strokes_is_written():
    opaque = _grid(tuple("1" * 8 for _ in OPACITY_MASK))
    reviewed = _reviewed(annotation=(annotation_digest(opaque), Review.KEEP))

    _, result = _transformed(_presentation_state(opaque), reviewed)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    graphics = written.GraphicAnnotationSequence[0].GraphicObjectSequence
    assert len(graphics) == 40
    assert {graphic.LineStyleSequence[0].PatternOnOpacity for graphic in graphics} == {
        1.0
    }


@pytest.mark.parametrize(
    "first, second",
    [
        # A compound graphic in a style that the simple graphic beside it
        # lacks: opaque letters can hide among transparent strokes.
        (
            {
                "LineStyleSequence": [
                    {"LineDashingStyle": "SOLID", "PatternOnOpacity": 1.0}
                ]
            },
            {
                "LineStyleSequence": [
                    {"LineDashingStyle": "SOLID", "PatternOnOpacity": 0.0}
                ]
            },
        ),
        # A fill in another colour.
        (
            {"FillStyleSequence": [{"FillMode": "SOLID"}]},
            {
                "FillStyleSequence": [
                    {"FillMode": "SOLID", "PatternOnColorCIELabValue": [0, 0, 0]}
                ]
            },
        ),
    ],
)
def test_a_compound_graphic_unlike_a_graphic_object_is_counted(first, second):
    def styled(dataset, styles):
        for keyword, items in styles.items():
            setattr(dataset, keyword, [synthetic.item(**fields) for fields in items])
        return dataset

    item = synthetic.item(
        GraphicLayer="LAYER",
        GraphicObjectSequence=[
            styled(
                synthetic.item(
                    GraphicAnnotationUnits="PIXEL",
                    GraphicDimensions=2,
                    NumberOfGraphicPoints=2,
                    GraphicData=[1.0, 1.0, 40.0, 1.0],
                    GraphicType="POLYLINE",
                ),
                first,
            )
        ],
        CompoundGraphicSequence=[
            styled(
                synthetic.item(
                    CompoundGraphicUnits="PIXEL",
                    GraphicDimensions=2,
                    NumberOfGraphicPoints=2,
                    GraphicData=[1.0, 2.0, 40.0, 2.0],
                    CompoundGraphicType="ARROW",
                    CompoundGraphicInstanceID=1,
                ),
                second,
            )
        ],
    )

    assert undrawn_objects(item) == 1


def test_text_objects_in_different_styles_are_counted():
    def text(colour):
        return synthetic.item(
            AnchorPointAnnotationUnits="PIXEL",
            AnchorPoint=[10.0, 10.0],
            AnchorPointVisibility="N",
            UnformattedTextValue="A",
            TextStyleSequence=[
                synthetic.item(TextColorCIELabValue=[65535, 32896, colour])
            ],
        )

    alike = synthetic.item(GraphicLayer="LAYER", TextObjectSequence=[text(32896)] * 3)
    unlike = synthetic.item(
        GraphicLayer="LAYER",
        TextObjectSequence=[text(32896), text(0), text(32896)],
    )

    assert undrawn_objects(alike) == 0
    assert undrawn_objects(unlike) == 1


def test_identifiers_that_tell_objects_apart_are_not_an_appearance():
    def graphic(number):
        return synthetic.item(
            GraphicAnnotationUnits="PIXEL",
            GraphicDimensions=2,
            NumberOfGraphicPoints=2,
            GraphicData=[1.0, float(number), 40.0, float(number)],
            GraphicType="POLYLINE",
            GraphicGroupID=number,
            TrackingID=f"STROKE {number}",
            TrackingUID=f"2.25.{900 + number}",
        )

    item = synthetic.item(
        GraphicLayer="LAYER", GraphicObjectSequence=[graphic(1), graphic(2)]
    )

    assert undrawn_objects(item) == 0


# Annotations together


def _parts(*opacities):
    """Annotations that each hold an even share of an opaque grid's strokes.

    Each part's strokes are drawn at the opacity given for it; one part per
    opacity given.
    """
    strokes = list(_grid(tuple("1" * 8 for _ in OPACITY_MASK)).GraphicObjectSequence)
    count = len(opacities)
    parts = []
    for index, opacity in enumerate(opacities):
        part = _grid()
        share = strokes[
            index * len(strokes) // count : (index + 1) * len(strokes) // count
        ]
        part.GraphicObjectSequence = [copy.deepcopy(each) for each in share]
        for stroke in part.GraphicObjectSequence:
            stroke.LineStyleSequence[0].PatternOnOpacity = opacity
        parts.append(part)
    return parts


def _kept_alone(*annotations):
    return _reviewed(
        **{
            f"a{index}": (annotation_digest(each), Review.KEEP)
            for index, each in enumerate(annotations)
        }
    )


def test_the_digest_of_annotations_together_is_of_the_set():
    first, second = annotation_digest(_arrow()), annotation_digest(_ruler())

    assert together_digest([first, second]) == together_digest([second, first])
    assert together_digest([first, second]) != together_digest([first])
    assert together_digest([first, second]) != together_digest([first, second, first])
    assert together_digest([first]) != first


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_annotations_kept_alone_are_held_until_decided_on_together():
    # Each half of a grid shows nothing alone; only the two drawn as one do.
    first, second = _parts(1.0, 1.0)
    reviewed = _kept_alone(first, second)

    _, result = _transformed(_presentation_state(first, second), reviewed)

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    assert {each.reason for each in getattr(result.evidence, "held")} == {
        Held.NOT_REVIEWED_TOGETHER
    }
    (as_one,) = [each for each in _material(result) if each.together]
    assert as_one.digest == together_digest(
        [annotation_digest(first), annotation_digest(second)]
    )
    assert as_one.result.held_because is Held.NOT_REVIEWED_TOGETHER
    # The QC pack's drawing of them together draws all forty strokes.
    assert draw_annotation(as_one.item).count("<polyline") == 40


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_annotations_kept_together_are_written():
    first, second = _parts(1.0, 1.0)
    reviewed = _kept_alone(first, second)
    reviewed.record(
        together_digest([annotation_digest(first), annotation_digest(second)]),
        Review.KEEP,
    )

    _, result = _transformed(_presentation_state(first, second), reviewed)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert len(written.GraphicAnnotationSequence) == 2
    assert [each.result.outcome for each in _material(result)] == [Outcome.KEPT] * 3


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_annotations_removed_together_are_removed():
    parts = _parts(1.0, 1.0, 1.0)
    reviewed = _kept_alone(*parts)
    reviewed.record(
        together_digest([annotation_digest(each) for each in parts]),
        Review.REMOVE,
    )

    _, result = _transformed(_presentation_state(*parts), reviewed)

    # Every annotation is removed, so the Type 1 sequence would be empty.
    assert isinstance(result, run.Sequestered), result


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_a_decision_together_is_not_taken_for_another_set():
    first, second, third = _parts(1.0, 1.0, 1.0)
    reviewed = _kept_alone(first, second, third)
    reviewed.record(
        together_digest([annotation_digest(first), annotation_digest(second)]),
        Review.KEEP,
    )

    # Beside a third annotation, the two are a new set, never drawn as one.
    _, result = _transformed(_presentation_state(first, second, third), reviewed)

    assert isinstance(result.evidence, HeldEvidence)
    assert {each.reason for each in getattr(result.evidence, "held")} == {
        Held.NOT_REVIEWED_TOGETHER
    }


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
@pytest.mark.parametrize(
    "opacities, layers",
    [
        # The halves' strokes in different opacities, so the drawing of them
        # as one, in one opacity, hides what they spell together.
        ((1.0, 0.0), ("LAYER", "LAYER")),
        # The halves on layers that a display shows in different colours.
        ((1.0, 1.0), ("LAYER", "OTHER")),
    ],
)
def test_annotations_unlike_one_another_are_held_whatever_the_list_decides(
    opacities, layers
):
    first, second = _parts(*opacities)
    first.GraphicLayer, second.GraphicLayer = layers
    reviewed = _kept_alone(first, second)
    reviewed.record(
        together_digest([annotation_digest(first), annotation_digest(second)]),
        Review.KEEP,
    )
    dataset = _presentation_state(first, second)
    dataset.GraphicLayerSequence = [
        synthetic.item(
            GraphicLayer="LAYER",
            GraphicLayerOrder=1,
            GraphicLayerRecommendedDisplayCIELabValue=[65535, 32896, 32896],
        ),
        synthetic.item(
            GraphicLayer="OTHER",
            GraphicLayerOrder=2,
            GraphicLayerRecommendedDisplayCIELabValue=[0, 32896, 32896],
        ),
    ]

    _, result = _transformed(dataset, reviewed)

    assert undrawn_objects(first) == undrawn_objects(second) == 0
    assert isinstance(result.evidence, HeldEvidence)
    assert {each.reason for each in getattr(result.evidence, "held")} == {
        Held.NOT_DRAWN
    }


def _strokes(units, segments):
    """An annotation of polylines, each a segment, all in ``units``."""
    return synthetic.item(
        GraphicLayer="LAYER",
        GraphicObjectSequence=[
            synthetic.item(
                GraphicAnnotationUnits=units,
                GraphicDimensions=2,
                NumberOfGraphicPoints=2,
                GraphicData=list(segment),
                GraphicType="POLYLINE",
                GraphicFilled="N",
            )
            for segment in segments
        ],
    )


# Strokes of "HI" on a 128 by 128 displayed area: the verticals in pixels,
# the crossbar and serifs as fractions of the displayed area.
VERTICALS = (
    (16.0, 32.0, 16.0, 96.0),
    (48.0, 32.0, 48.0, 96.0),
    (96.0, 32.0, 96.0, 96.0),
)
CROSSBARS = (
    (0.125, 0.5, 0.375, 0.5),
    (0.6875, 0.25, 0.8125, 0.25),
    (0.6875, 0.75, 0.8125, 0.75),
)


# Annotations shown together on each image


def _on(annotation, *slices, frames=None):
    """The annotation, shown on the given CT slices, by index, and frames."""
    annotation.ReferencedImageSequence = [
        synthetic.reference(synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[index])
        for index in slices
    ]
    if frames is not None:
        for reference in annotation.ReferencedImageSequence:
            reference.ReferencedFrameNumber = list(frames)
    return annotation


def _sets(result):
    return sorted(each.digest for each in _material(result) if each.together)


def _set_of(*annotations):
    return together_digest([annotation_digest(each) for each in annotations])


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_each_set_shown_on_an_image_is_decided_on():
    # Complementary checkerboards on two slices, kept as they are shown.
    a, b, c, d = _parts(1.0, 1.0, 1.0, 1.0)
    shown = [_on(a, 0), _on(b, 1), _on(c, 0), _on(d, 1)]
    reviewed = _kept_alone(a, b, c, d)
    for pair in ((a, c), (b, d)):
        reviewed.record(_set_of(*pair), Review.KEEP)

    _, result = _transformed(_presentation_state(*shown, slices=2), reviewed)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    assert _sets(result) == sorted([_set_of(a, c), _set_of(b, d)])


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_a_decision_on_a_set_is_not_taken_once_its_images_change():
    # The same four strokes, the same full grid as one, but two references
    # changed, so that one slice shows the lettering of the first two.
    a, b, c, d = _parts(1.0, 1.0, 1.0, 1.0)
    reviewed = _kept_alone(a, b, c, d)
    for pair in ((a, c), (b, d)):
        reviewed.record(_set_of(*pair), Review.KEEP)
    reviewed.record(_set_of(a, b, c, d), Review.KEEP)
    shown = [_on(a, 0), _on(b, 0), _on(c, 1), _on(d, 1)]

    _, result = _transformed(_presentation_state(*shown, slices=2), reviewed)

    assert isinstance(result.evidence, HeldEvidence)
    assert {each.reason for each in getattr(result.evidence, "held")} == {
        Held.NOT_REVIEWED_TOGETHER
    }
    assert _sets(result) == sorted([_set_of(a, b), _set_of(c, d)])


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_an_annotation_without_images_of_its_own_is_shown_on_every_image():
    a, b, c = _parts(1.0, 1.0, 1.0)
    del a.ReferencedImageSequence

    _, result = _transformed(
        _presentation_state(a, _on(b, 0), _on(c, 1), slices=2), _kept_alone(a, b, c)
    )

    assert _sets(result) == sorted([_set_of(a, b), _set_of(a, c)])


def test_annotations_on_different_frames_are_shown_with_those_on_every_frame():
    a, b, c = _parts(1.0, 1.0, 1.0)
    shown = [_on(a, 0, frames=[1]), _on(b, 0, frames=[2]), _on(c, 0)]

    _, result = _transformed(_presentation_state(*shown), _kept_alone(a, b, c))

    # Frame 1 shows a and c, frame 2 b and c, and any other frame c alone.
    assert _sets(result) == sorted([_set_of(a, c), _set_of(b, c)])


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_annotations_whose_images_are_not_known_are_held_as_not_drawn():
    a, b = _parts(1.0, 1.0)
    _on(b, 0)
    del b.ReferencedImageSequence[0].ReferencedSOPInstanceUID
    reviewed = _kept_alone(a, b)
    reviewed.record(_set_of(a, b), Review.KEEP)

    _, result = _transformed(_presentation_state(a, b), reviewed)

    assert isinstance(result.evidence, HeldEvidence)
    assert {each.reason for each in getattr(result.evidence, "held")} >= {
        Held.NOT_DRAWN
    }


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_a_set_removed_on_one_image_leaves_the_others_to_be_decided_again():
    a, b, c = _parts(1.0, 1.0, 1.0)
    shown = [_on(a, 0), _on(b, 0, 1), _on(c, 1)]
    reviewed = _kept_alone(a, b, c)
    reviewed.record(_set_of(a, b), Review.REMOVE)
    reviewed.record(_set_of(b, c), Review.KEEP)

    _, result = _transformed(_presentation_state(*shown, slices=2), reviewed)

    # Removing a and b leaves c alone on the second slice, so it is written.
    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert len(written.GraphicAnnotationSequence) == 1
    assert _sets(result) == []


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
@pytest.mark.parametrize("split", [False, True])
def test_strokes_in_pixel_and_display_units_are_held(split):
    # Each panel shows fragments; only a display, on the one image, shows
    # what the strokes spell together.
    if split:
        annotations = [
            _strokes("PIXEL", VERTICALS),
            _strokes("DISPLAY", CROSSBARS),
        ]
    else:
        whole = _strokes("PIXEL", VERTICALS)
        whole.GraphicObjectSequence.extend(
            _strokes("DISPLAY", CROSSBARS).GraphicObjectSequence
        )
        annotations = [whole]
    reviewed = _kept_alone(*annotations)
    if split:
        reviewed.record(
            together_digest([annotation_digest(each) for each in annotations]),
            Review.KEEP,
        )

    _, result = _transformed(_presentation_state(*annotations), reviewed)

    assert isinstance(result.evidence, HeldEvidence)
    assert {each.reason for each in getattr(result.evidence, "held")} == {
        Held.NOT_DRAWN
    }
    assert undrawn_objects(together(annotations)) == 3
    assert undrawn_objects(_strokes("PIXEL", VERTICALS)) == 0
    assert undrawn_objects(_strokes("DISPLAY", CROSSBARS)) == 0


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_strokes_in_one_units_kept_together_are_written():
    annotations = [_strokes("PIXEL", VERTICALS), _strokes("PIXEL", VERTICALS[:1])]
    reviewed = _kept_alone(*annotations)
    reviewed.record(
        together_digest([annotation_digest(each) for each in annotations]),
        Review.KEEP,
    )

    _, result = _transformed(_presentation_state(*annotations), reviewed)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)


def test_a_text_whose_box_and_anchor_are_in_different_units_is_not_drawn_whole():
    text = _arrow()
    text.GraphicObjectSequence = []
    text.TextObjectSequence[0].AnchorPointAnnotationUnits = "DISPLAY"
    text.TextObjectSequence[0].AnchorPoint = [0.5, 0.5]

    assert undrawn_objects(text) == 1


def _dots(visibilities):
    """An annotation of identical labels, one per visibility, each anchored."""
    return synthetic.item(
        GraphicLayer="LAYER",
        TextObjectSequence=[
            synthetic.item(
                BoundingBoxAnnotationUnits="PIXEL",
                BoundingBoxTopLeftHandCorner=[10.0, 10.0],
                BoundingBoxBottomRightHandCorner=[20.0, 20.0],
                BoundingBoxTextHorizontalJustification="LEFT",
                AnchorPointAnnotationUnits="PIXEL",
                AnchorPoint=[float(30 + 4 * index), 50.0],
                AnchorPointVisibility=visibility,
                UnformattedTextValue=".",
            )
            for index, visibility in enumerate(visibilities)
        ],
    )


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_the_drawing_shows_which_anchors_a_display_shows():
    # Leaders to visible anchors only, so their pattern is what is drawn.
    pattern = "YN" * 20
    drawn = draw_annotation(_dots(pattern))

    assert drawn != draw_annotation(_dots("Y" * 40))
    assert drawn.count("<polyline") == pattern.count("Y")
    assert draw_annotation(_dots("N" * 40)).count("<polyline") == 0
    assert undrawn_objects(_dots(pattern)) == 0


def test_an_anchor_of_unknown_visibility_is_not_drawn_whole():
    dots = _dots("Y" * 3)
    del dots.TextObjectSequence[1].AnchorPointVisibility

    assert undrawn_objects(dots) == 1


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_labels_with_visible_and_hidden_anchors_are_written_as_drawn():
    pattern = "YN" * 20
    annotation = _dots(pattern)
    reviewed = _kept_alone(annotation)

    _, result = _transformed(_presentation_state(annotation), reviewed)

    # The reviewer saw exactly the leaders that a display shows.
    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert [
        each.AnchorPointVisibility
        for each in written.GraphicAnnotationSequence[0].TextObjectSequence
    ] == list(pattern)


# What a kept annotation keeps


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.parametrize(
    "keyword, value",
    [
        ("PatientBirthDate", "19700101"),
        ("RetrieveURL", "https://example.invalid/SENTINEL"),
    ],
)
def test_a_kept_annotation_keeps_only_what_its_module_defines(keyword, value):
    # An attribute that the Graphic Annotation Module does not define there,
    # which neither the drawing nor the text values show, takes its own rule.
    arrow = _arrow()
    setattr(arrow.GraphicObjectSequence[0], keyword, value)
    reviewed = _reviewed(arrow=(annotation_digest(arrow), Review.KEEP))

    _, result = _transformed(_presentation_state(arrow), reviewed)

    assert isinstance(result, run.Transformed), result
    assert value.encode() not in result.data
    written = pydicom.dcmread(io.BytesIO(result.data))
    stroke = written.GraphicAnnotationSequence[0].GraphicObjectSequence[0]
    assert stroke.get(keyword) in (None, "")
    assert stroke.GraphicData == arrow.GraphicObjectSequence[0].GraphicData
    assert (
        written.GraphicAnnotationSequence[0].TextObjectSequence[0].UnformattedTextValue
        == ARROW_TEXT
    )


# How each drawing is framed


def _rotated_ellipse():
    """An annotation of an ellipse at 45 degrees, centred at (2000, 2000).

    Its semi-axes are (700, 700) and (-630, 630) pixels, so it reaches
    hypot(700, 630) = 941.753683 pixels from its centre across and down,
    beyond the ends of its axes.
    """
    return synthetic.item(
        GraphicLayer="LAYER",
        GraphicObjectSequence=[
            synthetic.item(
                GraphicAnnotationUnits="PIXEL",
                GraphicDimensions=2,
                NumberOfGraphicPoints=4,
                GraphicData=[
                    1300.0,
                    1300.0,
                    2700.0,
                    2700.0,
                    2630.0,
                    1370.0,
                    1370.0,
                    2630.0,
                ],
                GraphicType="ELLIPSE",
                GraphicFilled="N",
            )
        ],
    )


def _pixel_frame(drawing):
    """Return the (x, y, width, height) of the pixel units panel's frame."""
    (frame,) = re.findall(r'viewBox="([^"]+)"[^>]*overflow="hidden"', drawing)[:1]
    return tuple(float(value) for value in frame.split())


@pytest.mark.parametrize("as_one", [False, True])
def test_a_rotated_ellipse_is_framed_whole(as_one):
    item = _rotated_ellipse()
    if as_one:
        item = together([item, _strokes("PIXEL", VERTICALS)])
    reach = math.hypot(700.0, 630.0)

    x, y, width, height = _pixel_frame(draw_annotation(item))

    for start, extent in ((x, width), (y, height)):
        assert start <= 2000.0 - reach
        assert start + extent >= 2000.0 + reach
    assert undrawn_objects(item) == 0


def test_a_list_is_taken_only_under_clean_graphics():
    with pytest.raises(PolicyError, match="Clean Graphics|clean graphics"):
        _transformed(
            _presentation_state(_arrow()),
            ReviewedAnnotations.empty(),
            options=(MODIFIED_DATES,),
        )


def test_the_method_digest_binds_the_list():
    composed = policy.compose_custom_policy(list(OPTIONS))
    empty = ReviewedAnnotations.empty()
    kept = _reviewed(arrow=(annotation_digest(_arrow()), Review.KEEP))

    def digest(reviewed):
        return method_digest.method_digest(
            composed,
            vocabulary=None,
            reviewed_roi_names=None,
            reviewed_annotations=(
                None if reviewed is None else reviewed.keyed_digest(KEY)
            ),
        )

    assert len({digest(None), digest(empty), digest(kept)}) == 3
    assert method_digest.FORMAT.endswith("/8")


def test_the_lists_digest_binds_the_annotations_list_only_where_given():
    salt = "5a" * 32
    reviewed = _reviewed(arrow=(annotation_digest(_arrow()), Review.KEEP))

    without = risk_assessment.lists_digest(salt, None, None, None)

    assert risk_assessment.lists_digest(salt, None, None, None, None) == without
    assert risk_assessment.lists_digest(salt, None, None, None, reviewed) != without
    assert risk_assessment.lists_digest(
        salt, None, None, None, ReviewedAnnotations.empty()
    ) not in {without, risk_assessment.lists_digest(salt, None, None, None, reviewed)}
    with pytest.raises(TypeError, match="reviewed_annotations"):
        risk_assessment.lists_digest(salt, None, None, None, {})


def test_the_release_report_counts_the_annotations_without_their_text():
    reviewed = _reviewed(arrow=(annotation_digest(_arrow()), Review.KEEP))
    _, kept = _transformed(_presentation_state(_arrow()), reviewed)
    _, held = _transformed(
        _presentation_state(_arrow(), _ruler(units="PIXEL")), reviewed
    )

    counts = annotation_counts({0: kept.qc, 1: held.qc})

    # The arrow kept alone, and held beside the ruler until the two are
    # decided on together; the annotations together are not counted.
    assert dict(counts.outcomes) == {Outcome.KEPT: 1, Outcome.HELD: 2}
    assert dict(counts.held) == {
        Held.NOT_REVIEWED: 1,
        Held.NOT_REVIEWED_TOGETHER: 1,
    }
    text = release_report.to_json(
        release_report.release_report(
            policy.compose_custom_policy(list(OPTIONS)),
            vocabulary=None,
            reviewed_roi_names=None,
            reviewed_annotations=reviewed.keyed_digest(KEY),
            annotations=counts,
        )
    )
    document = json.loads(text)
    assert document["annotations"] == {
        "outcomes": [
            {"outcome": "held", "count": 2},
            {"outcome": "kept", "count": 1},
        ],
        "held": [
            {"reason": "not-reviewed", "count": 1},
            {"reason": "not-reviewed-together", "count": 1},
        ],
    }
    assert document["method"]["reviewed_annotations"] == reviewed.keyed_digest(KEY)
    markdown = to_markdown(text)
    assert "## Graphic annotations" in markdown
    assert "| `not-reviewed` | `1` |" in markdown
    for value in (RULER_TEXT, ARROW_TEXT, annotation_digest(_ruler())):
        assert value not in text and value not in markdown


# The drawing and the QC pack


def test_the_drawing_draws_each_graphic_and_text_and_escapes_the_text():
    arrow = _arrow()
    arrow.TextObjectSequence[0].UnformattedTextValue = 'A <b> & "c"'

    drawing = draw_annotation(arrow)

    document = xml.dom.minidom.parseString(drawing)
    assert document.documentElement.tagName == "svg"
    assert "<script" not in drawing and "href" not in drawing
    assert "A &lt;b&gt; &amp;" in drawing
    assert "<polyline" in drawing
    assert "pixel units" in drawing and "display units" not in drawing
    assert draw_annotation(arrow) == drawing


@pytest.mark.parametrize(
    "graphic_type, data, element",
    [
        ("POINT", [5.0, 5.0], "<circle"),
        ("CIRCLE", [50.0, 50.0, 60.0, 50.0], "<circle"),
        ("ELLIPSE", [40.0, 50.0, 60.0, 50.0, 50.0, 45.0, 50.0, 55.0], "<ellipse"),
        ("INTERPOLATED", [1.0, 1.0, 5.0, 9.0, 9.0, 1.0], "<polyline"),
        ("POLYLINE", [1.0, 1.0, 5.0, 9.0, 9.0, 1.0, 1.0, 1.0], "<polygon"),
    ],
)
def test_each_graphic_type_is_drawn(graphic_type, data, element):
    item = synthetic.item(
        GraphicLayer="LAYER",
        GraphicObjectSequence=[
            synthetic.item(
                GraphicAnnotationUnits="DISPLAY",
                GraphicDimensions=2,
                NumberOfGraphicPoints=len(data) // 2,
                GraphicData=[value / 100 for value in data],
                GraphicType=graphic_type,
            )
        ],
    )

    drawing = draw_annotation(item)

    assert element in drawing
    assert "display units" in drawing
    assert "not drawn" not in drawing


def test_a_graphic_that_cannot_be_drawn_is_counted_not_guessed():
    item = synthetic.item(
        GraphicLayer="LAYER",
        GraphicObjectSequence=[
            synthetic.item(
                GraphicAnnotationUnits="PIXEL",
                GraphicDimensions=2,
                NumberOfGraphicPoints=1,
                GraphicData=[1.0, 2.0, 3.0],
                GraphicType="POLYLINE",
            ),
            synthetic.item(
                GraphicAnnotationUnits="MATRIX",
                GraphicDimensions=2,
                NumberOfGraphicPoints=1,
                GraphicData=[1.0, 2.0],
                GraphicType="POINT",
            ),
        ],
    )

    drawing = draw_annotation(item)

    assert "nothing drawn; 2 object(s) not drawn" in drawing


def test_a_stippled_fill_is_drawn_bit_for_bit():
    lettered = draw_annotation(_filled(pattern=_pattern()))
    blank = draw_annotation(_filled(pattern=bytes(128)))

    # The lettering is shown, each row's most significant bit leftmost, so
    # a reviewer can tell it from a blank pattern.
    assert _bitmap(lettered)[: len(LETTERING)] == [
        row.ljust(32, ".") for row in LETTERING
    ]
    assert _bitmap(lettered)[len(LETTERING) :] == ["." * 32] * (32 - len(LETTERING))
    assert _bitmap(blank) == ["." * 32] * 32
    assert lettered != blank
    assert "fill pattern 1" in lettered and "not drawn" not in lettered
    assert undrawn_objects(_filled(pattern=_pattern())) == 0
    # The square itself is shaded as filled.
    assert '<polygon points="1,1 40,1 40,40 1,40" fill-opacity="0.15"/>' in lettered


def test_a_solid_fill_is_shaded_with_no_pattern_panel():
    drawing = draw_annotation(_filled(mode="SOLID"))

    assert 'fill-opacity="0.15"' in drawing
    assert "fill pattern" not in drawing and "not drawn" not in drawing


def test_a_dashed_compound_graphic_is_counted_not_drawn_whole():
    style = synthetic.item(LineDashingStyle="DASHED", LinePattern=0x0F0F0F0F)
    item = synthetic.item(
        GraphicLayer="LAYER",
        CompoundGraphicSequence=[
            synthetic.item(
                CompoundGraphicUnits="PIXEL",
                GraphicDimensions=2,
                NumberOfGraphicPoints=2,
                GraphicData=[1.0, 1.0, 40.0, 1.0],
                CompoundGraphicType="RULER",
                CompoundGraphicInstanceID=1,
                LineStyleSequence=[style],
            )
        ],
    )

    assert undrawn_objects(item) == 1
    assert "1 object(s) not drawn whole" in draw_annotation(item)


def test_a_compound_graphic_is_drawn_in_its_own_units():
    item = synthetic.item(
        GraphicLayer="LAYER",
        CompoundGraphicSequence=[
            synthetic.item(
                CompoundGraphicUnits="DISPLAY",
                GraphicDimensions=2,
                NumberOfGraphicPoints=2,
                GraphicData=[0.2, 0.3, 0.4, 0.5],
                CompoundGraphicType="ARROW",
                CompoundGraphicInstanceID=1,
            )
        ],
    )

    drawing = draw_annotation(item)

    assert '<polyline points="200,300 400,500" fill="none" stroke-dasharray' in drawing
    assert "display units" in drawing
    assert undrawn_objects(item) == 0


def _entry(**fields):
    defaults = {
        "position": 0,
        "path": ElementPath(
            ((GRAPHIC_ANNOTATION_SEQUENCE, 0),), GRAPHIC_ANNOTATION_SEQUENCE
        ),
        "digest": annotation_digest(_ruler()),
        "texts": annotation_texts(_ruler()),
        "outcome": Outcome.HELD,
        "held_because": Held.NOT_REVIEWED,
        "drawing": draw_annotation(_ruler()),
    }
    return AnnotationEntry(**{**defaults, **fields})


def test_the_pack_lists_each_annotation_with_its_text_and_drawing():
    from .test_deidentify_qc_pack import (  # pylint: disable=import-outside-toplevel
        REFERENCE,
        _written,
    )

    entry = _entry()
    pack = QcPack(REFERENCE, (_written(),), annotations=(entry,))

    document = json.loads(qc_pack.to_json(pack))

    assert document["annotations"] == [
        {
            "position": 0,
            "element": str(entry.path),
            "digest": entry.digest,
            "texts": list(entry.texts),
            "outcome": "held",
            "held_because": "not-reviewed",
            "drawing": entry.drawing,
        }
    ]
    assert "SENTINEL" not in repr(entry) and "SENTINEL" not in repr(pack)
    with pytest.raises(QcPackError, match="without an instance"):
        QcPack(REFERENCE, (_written(),), annotations=(_entry(position=1),))


@pytest.mark.parametrize(
    "fields, match",
    [
        ({"digest": "AB" * 32}, "64 lowercase"),
        ({"outcome": Outcome.KEPT}, "exactly when it was held"),
        ({"held_because": None}, "exactly when it was held"),
        ({"drawing": "<html>"}, "SVG"),
        ({"texts": ["x"]}, "tuple of text"),
        ({"path": ElementPath((), "(0070,0009)")}, "Graphic Annotation Sequence"),
    ],
)
def test_an_annotation_entry_is_checked(fields, match):
    with pytest.raises(QcPackError, match=match):
        _entry(**fields)


# Recording decisions


def test_the_command_records_a_reviewers_decisions(tmp_path):
    custodian = tmp_path / "custodian"
    custodian.mkdir()
    listed = custodian / "annotations.json"
    decisions = tmp_path / "decisions.csv"
    arrow, ruler = annotation_digest(_arrow()), annotation_digest(_ruler())
    decisions.write_text(
        f"digest,decision\n{arrow},keep\n{ruler},REMOVE\n{arrow},keep\n",
        encoding="utf-8",
    )
    stdout, stderr = io.StringIO(), io.StringIO()

    status = reviewed_annotations_command.main(
        [str(listed), str(decisions)], stdout=stdout, stderr=stderr
    )

    assert status == reviewed_annotations_command.EXIT_RECORDED, stderr.getvalue()
    reviewed = ReviewedAnnotations.open(listed)
    assert (reviewed.get(arrow), reviewed.get(ruler)) == (Review.KEEP, Review.REMOVE)
    assert arrow not in stdout.getvalue() and ruler not in stdout.getvalue()
    assert "annotations in the list: 2" in stdout.getvalue()

    decisions.write_text(f"digest,decision\n{arrow},remove\n", encoding="utf-8")
    status = reviewed_annotations_command.main(
        [str(listed), str(decisions)], stdout=stdout, stderr=stderr
    )
    assert status == reviewed_annotations_command.EXIT_NOT_RECORDED
    assert arrow not in stderr.getvalue()
    assert ReviewedAnnotations.open(listed).get(arrow) is Review.KEEP
    status = reviewed_annotations_command.main(
        [str(listed), str(decisions), "--replace"], stdout=stdout, stderr=stderr
    )
    assert status == reviewed_annotations_command.EXIT_RECORDED
    assert ReviewedAnnotations.open(listed).get(arrow) is Review.REMOVE


@pytest.mark.parametrize(
    "text, match",
    [
        ("digest\nab\n", "columns digest and decision"),
        ("digest,decision\n", "no decisions"),
        ("digest,decision\nzz,keep\n", "line 2"),
        (f"digest,decision\n{'a' * 64},maybe\n", "keep or remove"),
        (
            f"digest,decision\n{'a' * 64},keep\n{'a' * 64},remove\n",
            "lines 2 and 3",
        ),
    ],
)
def test_a_decisions_file_is_checked(tmp_path, text, match):
    decisions = tmp_path / "decisions.csv"
    decisions.write_text(text, encoding="utf-8")
    with pytest.raises(ReviewedAnnotationsError, match=match):
        reviewed_annotations_command.read_decisions(decisions)


# The conformance statement


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_the_statement_says_how_clean_graphics_cleans_graphic_annotations():
    statement = conformance.conformance_statement(
        policy.compose_custom_policy([CLEAN_GRAPHICS]), vocabulary=None
    )

    entry = next(
        each for each in statement.attributes if each.tag == GRAPHIC_ANNOTATION_SEQUENCE
    )
    assert (entry.action, entry.superseded_by) == ("C", "")
    (cleaned,) = [each for each in statement.cleaned if each.option == CLEAN_GRAPHICS]
    assert cleaned.tags == (GRAPHIC_ANNOTATION_SEQUENCE,)
    assert not statement.pending
    text = conformance_markdown.render_markdown(statement)
    assert "reviewed annotations list" in text
    assert "a reviewer's decision on it" in text
