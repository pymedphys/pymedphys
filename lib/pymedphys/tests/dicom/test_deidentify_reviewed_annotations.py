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

import io
import json
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
from pymedphys._dicom.deidentify.annotation_drawing import draw_annotation
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


def _ruler(text=RULER_TEXT):
    """An annotation of a measurement, whose label stands in for a name."""
    return synthetic.item(
        GraphicLayer="LAYER",
        TextObjectSequence=[
            synthetic.item(
                AnchorPointAnnotationUnits="DISPLAY",
                AnchorPoint=[0.5, 0.5],
                AnchorPointVisibility="N",
                UnformattedTextValue=text,
            )
        ],
    )


def _presentation_state(*annotations):
    dataset = synthetic.instance(
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        "2.25.701",
        "2.25.700",
        ReferencedSeriesSequence=[
            synthetic.item(
                SeriesInstanceUID=synthetic.CT_SERIES,
                ReferencedImageSequence=[
                    synthetic.reference(
                        synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[0]
                    )
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

    transform, result = _transformed(_presentation_state(_arrow(), _ruler()), reviewed)

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    path = ElementPath(((GRAPHIC_ANNOTATION_SEQUENCE, 1),), GRAPHIC_ANNOTATION_SEQUENCE)
    assert getattr(result.evidence, "held") == (
        HeldAnnotation(path, Held.NOT_REVIEWED),
    )
    # The staged file carries no unreviewed text.
    assert b"SENTINEL" not in result.data
    held = [each for each in _material(result) if each.result.outcome is Outcome.HELD]
    assert [each.texts for each in held] == [annotation_texts(_ruler())]
    assert "SENTINEL" not in repr(held)
    (pending,) = transform.annotation_queue.entries()
    assert pending.digest == annotation_digest(_ruler())


def test_a_kept_annotation_that_names_the_patient_is_held():
    named = _ruler(synthetic.PATIENTS_NAME)
    reviewed = _reviewed(named=(annotation_digest(named), Review.KEEP))

    _, result = _transformed(_presentation_state(named), reviewed)

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    (held,) = getattr(result.evidence, "held")
    assert held.reason is Held.ECHOES_IDENTIFIER
    assert synthetic.PATIENTS_NAME.encode() not in result.data


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
    _, held = _transformed(_presentation_state(_arrow(), _ruler()), reviewed)

    counts = annotation_counts({0: kept.qc, 1: held.qc})

    assert dict(counts.outcomes) == {Outcome.KEPT: 2, Outcome.HELD: 1}
    assert dict(counts.held) == {Held.NOT_REVIEWED: 1}
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
            {"outcome": "held", "count": 1},
            {"outcome": "kept", "count": 2},
        ],
        "held": [{"reason": "not-reviewed", "count": 1}],
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
        ({"path": ElementPath((), GRAPHIC_ANNOTATION_SEQUENCE)}, "item's"),
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
