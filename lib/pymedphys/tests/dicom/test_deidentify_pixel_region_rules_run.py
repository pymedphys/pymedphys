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

"""Reviewed region rules applied by the Clean Pixel Data Option.

A rule's regions are blacked out in every frame beside the text finder's,
the instance is still held for review, the QC pack records which regions a
rule gave, the release report counts the regions by what gave them, and a
later run given the reviewer's verdict blacks them out again without the
rules. Every file is synthetic, every manufacturer and model name invented,
and every finder a stand-in that gives fixed regions.
"""

import io
import json
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    method_digest,
    qc_pack,
    release_report,
    release_report_markdown,
    risk_assessment,
    run,
    run_report,
)
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
)
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    black_out,
    finder_description,
    redaction_problem,
)
from pymedphys._dicom.deidentify.pixel_region_rules import (
    PixelRegionRules,
    RuleKey,
)
from pymedphys._dicom.deidentify.policy import (
    CLEAN_PIXEL_DATA,
    PolicyError,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.qc_attestation import Redaction, RedactionVerdict
from pymedphys._dicom.deidentify.qc_pack import QcPackError, RedactionEntry
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    PixelDataReason,
    TransformReason,
)
from pymedphys._dicom.deidentify.redaction_review import read_redaction_review
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.run_qc import RedactionMaterial
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_references as synthetic
from .test_deidentify_pixel_cleaning import (
    BOX,
    KEY,
    Finder,
    _ct,
    _frame,
    _inside,
    _pixels,
    _replaced,
    _source,
)
from .test_deidentify_redaction_review import _attest, _codes, _run, _write

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

MANUFACTURER, MODEL = "Acme Imaging", "Scanner 9"
# The bottom two rows of a frame of six rows and eight columns, where the
# invented scanner burns its text.
BAND = TextBox(4, 0, 6, 8)
RULE = RuleKey(synthetic.CT_IMAGE_STORAGE, MANUFACTURER, MODEL, 6, 8)


def _policy():
    return compose_custom_policy([CLEAN_PIXEL_DATA])


def _rules(*boxes):
    rules = PixelRegionRules.empty()
    rules.record(RULE, boxes or (BAND,))
    return rules


def _scanned(frames, model=MODEL):
    """A CT slice of the invented scanner, holding ``frames``."""
    dataset = _ct(frames)
    dataset.Manufacturer = MANUFACTURER
    dataset.ManufacturerModelName = model
    return dataset


def _transform(rules=None, finder=None):
    return InstanceTransform(
        _policy(),
        KEY,
        finder=Finder() if finder is None else finder,
        pixel_region_rules=_rules() if rules is None else rules,
        unvalidated_policy=True,
    )


def _transformed(transform, data):
    return transform(data, InstanceRecord.from_file(data))


# Blacking out a rule's regions.


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_rules_regions_are_blacked_out_in_every_frame_beside_the_finders():
    frames = np.stack([_frame(start=100), _frame(start=900), _frame(start=50)])
    source = _source(_scanned(frames))

    redaction = black_out(
        source, source.dataset(), Finder(frames={1}), rules=(BAND, BAND)
    )

    assert redaction.rule_boxes == (BAND,)
    assert [(r.frame, r.boxes) for r in redaction.regions] == [
        (0, (BAND,)),
        (1, (BOX, BAND)),
        (2, (BAND,)),
    ]
    assert redaction.reason is PixelDataReason.TEXT_BLACKED_OUT
    output = _replaced(source, redaction)
    pixels = _pixels(output)
    band = _inside(frames.shape[1:], BAND)
    found = band | _inside(frames.shape[1:])
    for index, inside in enumerate((band, found, band)):
        assert np.all(pixels[index][inside] == frames[index].min())
        assert np.array_equal(pixels[index][~inside], frames[index][~inside])
    assert not redaction_problem(source, output, redaction)


def test_a_redaction_without_rules_records_none():
    source = _source(_scanned(_frame()))

    redaction = black_out(source, source.dataset(), Finder())

    assert not redaction.rule_boxes


def test_a_rules_region_is_never_clipped():
    source = _source(_scanned(_frame()))

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder(), rules=(TextBox(4, 0, 7, 8),))

    assert refused.value.reason is TransformReason.REDACTION_MISMATCH


@pytest.mark.parametrize(
    "finder, rules",
    [(None, (BAND,)), (Finder(), ((4, 0, 6, 8),))],
)
def test_rules_need_a_finder_and_text_boxes(finder, rules):
    source = _source(_scanned(_frame()))

    with pytest.raises(TypeError):
        black_out(source, source.dataset(), finder, rules=rules)


# The transform.


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_an_image_that_a_rule_matches_is_blacked_out_and_held_for_review():
    frame = _frame()
    data = synthetic.written(_scanned(frame))

    result = _transformed(_transform(finder=Finder(boxes=())), data)

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    assert result.evidence.held == (  # pylint: disable=no-member
        HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),
    )
    written = pydicom.dcmread(io.BytesIO(result.data))
    pixels = pydicom.pixels.pixel_array(written)
    band = _inside(frame.shape, BAND)
    assert np.all(pixels[band] == frame.min())
    assert np.array_equal(pixels[~band], frame[~band])
    assert "BurnedInAnnotation" not in written
    (material,) = [item for item in result.qc if isinstance(item, RedactionMaterial)]
    assert material.rule_boxes == (BAND,)
    assert material.regions == ((0, (BAND,)),)


@pytest.mark.parametrize(
    "keyword, value",
    [("ManufacturerModelName", "Scanner 10"), ("Manufacturer", "ACME IMAGING")],
)
def test_an_image_of_another_kind_takes_no_rule(keyword, value):
    dataset = _scanned(_frame())
    setattr(dataset, keyword, value)

    result = _transformed(
        _transform(finder=Finder(boxes=())), synthetic.written(dataset)
    )

    assert isinstance(result, run.Transformed), result
    assert result.evidence.held == (  # pylint: disable=no-member
        HeldPixelData(PixelDataReason.NO_TEXT_FOUND),
    )
    (material,) = [item for item in result.qc if isinstance(item, RedactionMaterial)]
    assert material.rule_boxes == () and material.regions == ()


def test_rules_are_given_only_with_clean_pixel_data():
    with pytest.raises(PolicyError, match="region rules"):
        InstanceTransform(
            compose_policy("basic"),
            KEY,
            pixel_region_rules=_rules(),
            unvalidated_policy=True,
        )


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_the_rules_keyed_digest_is_an_input_to_the_method_digest():
    rules = _rules()
    digest = method_digest.method_digest(
        _policy(),
        vocabulary=None,
        reviewed_roi_names=None,
        text_finder=finder_description(Finder()),
        pixel_region_rules=rules.keyed_digest(KEY),
    )

    result = _transformed(_transform(rules), synthetic.written(synthetic.rt_plan()))

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert digest in written.DeidentificationMethod
    assert digest != method_digest.method_digest(
        _policy(),
        vocabulary=None,
        reviewed_roi_names=None,
        text_finder=finder_description(Finder()),
    )


def test_a_rule_recorded_after_the_transform_is_made_does_not_apply():
    rules = PixelRegionRules.empty()
    transform = _transform(rules, Finder(boxes=()))
    rules.record(RULE, (BAND,))

    result = _transformed(transform, synthetic.written(_scanned(_frame())))

    assert result.evidence.held == (  # pylint: disable=no-member
        HeldPixelData(PixelDataReason.NO_TEXT_FOUND),
    )
    # The run's QC pack binds the rules that it applied, not those recorded
    # since.
    applied = transform.reporter.reviewed_lists[2]
    assert applied.canonical_bytes() == PixelRegionRules.empty().canonical_bytes()


def test_a_transform_without_rules_binds_none():
    transform = InstanceTransform(
        _policy(), KEY, finder=Finder(), unvalidated_policy=True
    )
    assert transform.reporter.reviewed_lists == (None, None, None)


# The method digest's member.

DIGEST = "6d1f0f2f3f86e7a3ffb6d0f0c1d4d0c2f8b6e5a4d3c2b1a0f9e8d7c6b5a49382"


def test_the_rules_digest_is_a_member_that_shows_only_in_its_component():
    clean = _policy()
    before = method_digest.method_digest_components(
        clean, vocabulary=None, reviewed_roi_names=None
    )

    after = method_digest.method_digest_components(
        clean, vocabulary=None, reviewed_roi_names=None, pixel_region_rules=DIGEST
    )

    assert after.pixel_region_rules == DIGEST and before.pixel_region_rules is None
    assert after.method_digest != before.method_digest
    document = json.loads(
        method_digest.canonical_bytes(
            clean,
            method_digest.digest_inputs(
                vocabulary=None, reviewed_roi_names=None, pixel_region_rules=DIGEST
            ),
        )
    )
    assert document["pixel_region_rules"] == DIGEST
    assert after.method_digest != method_digest.method_digest(
        clean, vocabulary=None, reviewed_roi_names=DIGEST
    )


@pytest.mark.parametrize("value", ["A" * 64, "0" * 63, "SENTINEL" * 8, b"0" * 64])
def test_the_rules_digest_must_be_64_lowercase_hexadecimal_digits(value):
    with pytest.raises((TypeError, ValueError), match="pixel_region_rules") as raised:
        method_digest.digest_inputs(
            vocabulary=None, reviewed_roi_names=None, pixel_region_rules=value
        )

    assert "SENTINEL" not in str(raised.value)


# The QC pack's record of a rule's regions.


def _entry(regions, rule_boxes, frames=2):
    return RedactionEntry(
        0, PixelDataReason.TEXT_BLACKED_OUT, frames, 6, 8, regions, None, rule_boxes
    )


def test_the_pack_records_which_regions_a_rule_gave():
    entry = _entry(((0, (BOX, BAND)), (1, (BAND,))), (BAND,))

    assert entry.rule_boxes == (BAND,)


@pytest.mark.parametrize(
    "regions, rule_boxes",
    [
        # Not in every frame.
        (((0, (BOX, BAND)),), (BAND,)),
        (((0, (BOX, BAND)), (1, (BOX,))), (BAND,)),
        # Not sorted, repeated, or not boxes.
        (((0, (BOX, BAND)), (1, (BOX, BAND))), (BAND, BOX)),
        (((0, (BAND,)), (1, (BAND,))), (BAND, BAND)),
        (((0, (BAND,)), (1, (BAND,))), [BAND]),
        (((0, (BAND,)), (1, (BAND,))), ((4, 0, 6, 8),)),
    ],
)
def test_the_pack_refuses_a_rules_region_that_is_not_in_every_frame(
    regions, rule_boxes
):
    with pytest.raises(QcPackError, match="rule"):
        _entry(regions, rule_boxes)


# The release report's counts.


def _report(**run_fields):
    return release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None, **run_fields
    )


def test_the_report_counts_the_regions_by_what_gave_them():
    counts = release_report.PixelRegionCounts(detected=3, rule=2)

    document = release_report.report_document(_report(pixel_regions=counts))
    markdown = release_report_markdown.to_markdown(
        release_report.to_json(_report(pixel_regions=counts))
    )

    assert document["pixel_regions"] == {"detected": 3, "rule": 2}
    section = markdown.split("## Pixel regions", 1)[1].split("\n## ", 1)[0]
    assert [line for line in section.splitlines() if line.startswith("| ")] == [
        "| Source | Regions |",
        "| --- | --- |",
        "| Text finder | `3` |",
        "| Region rules | `2` |",
    ]


def test_the_report_counts_no_regions_by_default_under_the_option_only():
    clean = release_report.report_document(_report())
    basic = release_report.report_document(
        release_report.release_report(
            compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
        )
    )

    assert clean["pixel_regions"] == {"detected": 0, "rule": 0}
    assert basic["pixel_regions"] is None


@pytest.mark.parametrize(
    "counts",
    [
        release_report.PixelRegionCounts(detected=-1),
        release_report.PixelRegionCounts(rule=True),  # type: ignore[arg-type]
        {"detected": 0, "rule": 0},
    ],
)
def test_the_report_refuses_counts_that_are_not_whole_numbers(counts):
    with pytest.raises(release_report.ReleaseReportError, match="pixel_regions"):
        release_report.report_document(_report(pixel_regions=counts))


def test_the_report_refuses_counts_without_the_option():
    report = release_report.release_report(
        compose_policy("basic"),
        vocabulary=None,
        reviewed_roi_names=None,
        pixel_regions=release_report.PixelRegionCounts(),
    )

    with pytest.raises(release_report.ReleaseReportError, match="pixel_regions"):
        release_report.report_document(report)


# A first run with rules, and a second run given its reviewer's verdicts.

_MATCHED, _ALSO_MATCHED, _OTHER = "0-matched.dcm", "1-matched.dcm", "2-other.dcm"


def _images():
    datasets = {
        _MATCHED: _scanned(_frame(start=100)),
        _ALSO_MATCHED: _scanned(_frame(start=200)),
        _OTHER: _scanned(_frame(start=300), model="Scanner 10"),
    }
    for number, dataset in enumerate(datasets.values()):
        dataset.SOPInstanceUID = f"2.25.30{number + 1}"
        dataset.InstanceNumber = number + 1
    return {name: synthetic.written(dataset) for name, dataset in datasets.items()}


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_reviewed_rules_regions_are_released_again_without_the_rules(tmp_path):
    source = tmp_path / "source"
    _write(source, _images())

    first = _run(tmp_path / "first", source, _transform())

    pack = json.loads(first.qc_pack.read_text("utf-8"))
    names = {
        entry["position"]: Path(entry["source"]).name for entry in pack["instances"]
    }
    redactions = {names[entry["position"]]: entry for entry in pack["redactions"]}
    assert redactions[_MATCHED]["regions"] == [
        {"frame": 0, "boxes": [[1, 2, 3, 5], [4, 0, 6, 8]]}
    ]
    assert redactions[_MATCHED]["rule_boxes"] == [[4, 0, 6, 8]]
    assert redactions[_OTHER]["rule_boxes"] == []
    report = json.loads(
        (tmp_path / "first" / "release" / run_report.RELEASE_REPORT).read_text("utf-8")
    )
    assert report["pixel_regions"] == {"detected": 3, "rule": 2}
    assert report["method"]["pixel_region_rules"] == _rules().keyed_digest(KEY)
    # The pack binds the rules that the run applied, under its own salt, for
    # a risk assessment of the run, since the report's digest is keyed.
    bound = pack["reviewed_lists"]
    assert bound["sha256"] == risk_assessment.lists_digest(
        bound["salt"], None, None, _rules()
    )
    assert {outcome.status for outcome in first.outcomes} == {
        run.Status.HELD_FOR_REVIEW
    }

    positions = {name: position for position, name in names.items()}
    _attest(
        first.qc_pack.parent,
        (RedactionVerdict(positions[_MATCHED], Redaction.ACCEPTED),),
    )
    # The second run has no rules, and a finder that finds nothing: the
    # accepted image's regions come from the reviewed pack alone.
    second = _run(
        tmp_path / "second",
        source,
        InstanceTransform(
            _policy(),
            KEY,
            finder=Finder(boxes=()),
            redaction_review=read_redaction_review(first.qc_pack.parent),
            unvalidated_policy=True,
        ),
    )

    entries = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
    dispositions = {
        Path(entry["source"]).name: entry["disposition"] for entry in entries
    }
    assert dispositions == {
        _MATCHED: "released",
        _ALSO_MATCHED: "held-for-review",
        _OTHER: "held-for-review",
    }
    (output,) = [entry["output"] for entry in entries if entry["output"]]
    written = pydicom.dcmread(tmp_path / "second" / "release" / output)
    frame = _frame(start=100)
    inside = _inside(frame.shape, BAND) | _inside(frame.shape)
    pixels = pydicom.pixels.pixel_array(written)
    assert np.all(pixels[inside] == frame.min())
    assert np.array_equal(pixels[~inside], frame[~inside])
    assert written.BurnedInAnnotation == "NO"
    assert "113101" in _codes(written)
    second_report = json.loads(
        (tmp_path / "second" / "release" / run_report.RELEASE_REPORT).read_text("utf-8")
    )
    # The images held again, without rules, have none of the rules' regions.
    assert second_report["pixel_regions"] == {"detected": 0, "rule": 0}
    assert second_report["method"]["pixel_region_rules"] is None
    assert qc_pack.FORMAT == "pymedphys-deid-qc-pack/18"
