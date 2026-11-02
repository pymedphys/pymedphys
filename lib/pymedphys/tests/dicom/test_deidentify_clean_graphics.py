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

"""The Clean Graphics Option, claimed where its graphics take their Basic actions.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    clean_graphics,
    conformance,
    conformance_markdown,
    policy,
    release_report,
    run,
    standard,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.element_rules import ElementRules, RuleSource
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    TransformReason,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.run_qc import PixelRiskMaterial

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CLEAN_GRAPHICS = clean_graphics.CLEAN_GRAPHICS
BASIC_PROFILE_CODE = "113100"
CLEAN_DESCRIPTORS_CODE = "113105"
CLEAN_GRAPHICS_CODE = "113103"
# The rows of Table E.1-1 that Clean Graphics gives C, and their Basic
# Profile actions.
GRAPHICS_ROWS = {
    "(50xx,xxxx)": "X",
    "(0070,0001)": "D",
    "(60xx,4000)": "X",
    "(60xx,3000)": "X",
}
# The rows that stay masked or name a repeating group, and a sequence.
REPEATING_ROWS = ("(50xx,xxxx)", "(60xx,4000)", "(60xx,3000)")
GRAPHIC_ANNOTATION_SEQUENCE = "(0070,0001)"
DE_IDENTIFICATION_METHOD = 0x00120063
DE_IDENTIFICATION_METHOD_CODES = 0x00120064


def _rules(options):
    return ElementRules(policy.compose_custom_policy(options))


def _transform(options, cleaning=None):
    return InstanceTransform(
        policy.compose_custom_policy(options),
        KEY,
        cleaning=cleaning,
        unvalidated_policy=True,
    )


def _ct():
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    return dataset


def _with_overlay(dataset, group=0x6000, data=True):
    """Add an overlay group, with Overlay Data unless ``data`` is False."""
    dataset.add_new(group << 16 | 0x0010, "US", 4)  # Overlay Rows
    dataset.add_new(group << 16 | 0x0011, "US", 4)  # Overlay Columns
    dataset.add_new(group << 16 | 0x0022, "LO", "SENTINEL DESCRIPTION")
    dataset.add_new(group << 16 | 0x0040, "CS", "G")  # Overlay Type
    dataset.add_new(group << 16 | 0x0050, "SS", [1, 1])  # Overlay Origin
    dataset.add_new(group << 16 | 0x0100, "US", 1)  # Overlay Bits Allocated
    dataset.add_new(group << 16 | 0x0102, "US", 0)  # Overlay Bit Position
    dataset.add_new(group << 16 | 0x1500, "LO", "SENTINEL LABEL")
    dataset.add_new(group << 16 | 0x4000, "LT", "SENTINEL COMMENTS")
    if data:
        dataset.add_new(group << 16 | 0x3000, "OW", b"SENTINEL")
    return dataset


def _with_curve(dataset, group=0x5000):
    """Add a retired curve group, which the CT Image IOD does not define."""
    dataset.add_new(group << 16 | 0x0005, "US", 2)  # Curve Dimensions
    dataset.add_new(group << 16 | 0x0010, "US", 1)  # Number of Points
    dataset.add_new(group << 16 | 0x0020, "CS", "POLY")  # Type of Data
    dataset.add_new(group << 16 | 0x0022, "LO", "SENTINEL CURVE")
    dataset.add_new(group << 16 | 0x3000, "OW", b"SENTINEL")  # Curve Data
    return dataset


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _written(transform, dataset):
    result = _transformed(transform, dataset)
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data))


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


def test_clean_graphics_gives_c_to_its_four_rows_of_table_e1_1():
    rows = {
        row.tag: row.basic_profile
        for row in standard.load_table_e1_1().attributes
        if row.options.get(CLEAN_GRAPHICS) == "C"
    }

    assert rows == GRAPHICS_ROWS


def test_the_engine_applies_clean_graphics():
    assert CLEAN_GRAPHICS in policy.ENGINE_OPTIONS
    composed = policy.compose_custom_policy([CLEAN_GRAPHICS])
    policy.refuse_unapplied_options(composed)

    assert composed.actions["(60xx,3000)"] == "C"


@pytest.mark.parametrize("tag", list(GRAPHICS_ROWS))
def test_each_row_that_clean_graphics_cleans_takes_its_basic_profile_action(tag):
    rules = _rules([CLEAN_GRAPHICS])

    assert rules.row_action(tag) == GRAPHICS_ROWS[tag]
    assert _rules([]).row_action(tag) == GRAPHICS_ROWS[tag]


@pytest.mark.parametrize(
    "tag, entry",
    [
        ("(6000,3000)", "(60xx,3000)"),
        ("(601E,3000)", "(60xx,3000)"),
        ("(6002,4000)", "(60xx,4000)"),
        ("(5000,3000)", "(50xx,xxxx)"),
        ("(501E,0022)", "(50xx,xxxx)"),
        ("(0070,0001)", "(0070,0001)"),
    ],
)
def test_an_element_of_a_graphics_row_has_the_rows_basic_profile_action(tag, entry):
    for options in ([CLEAN_GRAPHICS], [CLEAN_GRAPHICS, "clean_descriptors"]):
        rule = _rules(options).rule(tag)

        assert (rule.source, rule.entry) == (RuleSource.TABLE, entry)
        assert rule.action == GRAPHICS_ROWS[entry]


def test_a_masked_row_that_no_option_gives_c_keeps_its_action():
    # Only Clean Graphics gives C to a masked row, so no other option's
    # action is changed.
    for row in standard.load_table_e1_1().attributes:
        if "x" not in row.tag:
            continue
        for option, action in row.options.items():
            assert option == CLEAN_GRAPHICS or action != "C", (row.tag, option)


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_overlays_are_removed_and_the_instance_claims_clean_graphics():
    source = _with_overlay(_with_overlay(_ct()), group=0x6002)

    written = _written(_transform([CLEAN_GRAPHICS]), source)

    assert not [tag for tag in written.keys() if 0x6000 <= tag.group <= 0x601E]
    assert "SENTINEL" not in str(written)
    assert _codes(written) == [BASIC_PROFILE_CODE, CLEAN_GRAPHICS_CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_curves_are_removed_and_the_instance_claims_clean_graphics():
    source = _with_curve(_with_curve(_ct()), group=0x501E)

    written = _written(_transform([CLEAN_GRAPHICS]), source)

    assert not [tag for tag in written.keys() if 0x5000 <= tag.group <= 0x501E]
    assert "SENTINEL" not in str(written)
    assert _codes(written) == [BASIC_PROFILE_CODE, CLEAN_GRAPHICS_CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_a_graphic_annotation_sequence_is_removed_where_the_iod_omits_it():
    source = _ct()
    annotation = pydicom.Dataset()
    annotation.GraphicLayer = "SENTINEL LAYER"
    source.GraphicAnnotationSequence = [annotation]

    written = _written(_transform([CLEAN_GRAPHICS]), source)

    assert "GraphicAnnotationSequence" not in written
    assert _codes(written) == [BASIC_PROFILE_CODE, CLEAN_GRAPHICS_CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_an_overlay_that_may_lie_in_pixel_data_sequesters_the_instance():
    # Without Overlay Data, the overlay may lie in unused bits of Pixel
    # Data (PS3.3 before 2004). This slice has no Pixel Data in which to
    # clear it, so the option cannot be shown to remove it.
    source = _with_overlay(_ct(), data=False)

    result = _transformed(_transform([CLEAN_GRAPHICS]), source)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.OVERLAY_IN_PIXEL_DATA,)
    # The QC pack still shows the instance's indicator, as under the Basic
    # Profile, which releases it without claiming Clean Graphics.
    assert any(isinstance(material, PixelRiskMaterial) for material in result.qc)
    basic = _written(_transform([]), source)
    assert _codes(basic) == [BASIC_PROFILE_CODE]


def test_an_overlay_with_its_own_data_beside_one_without_still_sequesters():
    source = _with_overlay(_with_overlay(_ct()), group=0x6002, data=False)

    result = _transformed(_transform([CLEAN_GRAPHICS]), source)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.OVERLAY_IN_PIXEL_DATA,)


def test_the_overlay_reason_is_a_transform_reason_of_the_release_report():
    reason = release_report.sequestration_reason(TransformReason.OVERLAY_IN_PIXEL_DATA)

    assert (reason.stage, reason.code) == ("transform", "overlay-in-pixel-data")


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_clean_graphics_with_clean_descriptors_claims_both():
    cleaning = DescriptorCleaning(None, ReviewedNames.empty())
    source = _with_overlay(_ct())
    source.StudyDescription = "SENTINEL STUDY"

    written = _written(
        _transform([CLEAN_GRAPHICS, "clean_descriptors"], cleaning), source
    )

    assert "SENTINEL" not in str(written)
    assert _codes(written) == [
        BASIC_PROFILE_CODE,
        CLEAN_DESCRIPTORS_CODE,
        CLEAN_GRAPHICS_CODE,
    ]


def _items(data):
    dataset = pydicom.dcmread(io.BytesIO(data))
    return [
        item.get("CodeValue") for item in dataset.DeidentificationMethodCodeSequence
    ]


def _without_markers(data):
    dataset = pydicom.dcmread(io.BytesIO(data))
    # The method digest differs with the policy, and the codes with the
    # options claimed.
    del dataset[DE_IDENTIFICATION_METHOD]
    del dataset[DE_IDENTIFICATION_METHOD_CODES]
    return dataset


# The corpus plants markers in UI elements, which pydicom warns of on reading.
@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
@pytest.mark.filterwarnings("ignore:Invalid value for VR UI:UserWarning")
def test_every_corpus_instance_is_written_as_under_the_basic_profile():
    # The corpus plants a marker in each attribute of Table E.1-1 that its
    # IODs define, Overlay Data among them. Clean Graphics, which cleans
    # nothing yet, writes what the Basic Profile writes, and claims the
    # option.
    basic, graphics = _transform([]), _transform([CLEAN_GRAPHICS])
    released = 0
    for file in corpus_module.build_corpus().files:
        record = InstanceRecord.from_file(file.data)
        expected = basic(file.data, record)
        found = graphics(file.data, record)

        assert type(found) is type(expected), file.manifest.iod
        if isinstance(expected, run.Sequestered):
            assert found.reasons == expected.reasons, file.manifest.iod
            continue
        released += 1
        assert _without_markers(found.data) == _without_markers(expected.data)
        # The option's code follows the items already present and the
        # profile's code.
        assert _items(found.data) == [*_items(expected.data), CLEAN_GRAPHICS_CODE]
    assert released


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
def test_the_statement_gives_each_graphics_row_its_basic_profile_action():
    statement = conformance.conformance_statement(
        policy.compose_custom_policy([CLEAN_GRAPHICS]), vocabulary=None
    )

    by_tag = {entry.tag: entry for entry in statement.attributes}
    for tag in REPEATING_ROWS:
        entry = by_tag[tag]
        assert (entry.action, entry.policy_action) == (GRAPHICS_ROWS[tag], "C")
        assert entry.superseded_by == conformance.GRAPHICS_NOT_CLEANED
    annotation = by_tag[GRAPHIC_ANNOTATION_SEQUENCE]
    assert (annotation.action, annotation.policy_action) == ("D", "C")
    assert annotation.superseded_by == conformance.SEQUENCE_NOT_CLEANED
    assert not any(entry.action == "C" for entry in statement.attributes)
    # Nothing is left to describe, and every written instance claims the
    # option without review.
    assert not statement.pending
    assert statement.markers.codes == (BASIC_PROFILE_CODE, CLEAN_GRAPHICS_CODE)
    assert not statement.markers.review_codes


def test_the_statement_says_how_graphics_are_removed_and_when_it_sequesters():
    statement = conformance.conformance_statement(
        policy.compose_custom_policy([CLEAN_GRAPHICS]), vocabulary=None
    )

    text = conformance_markdown.render_markdown(statement)

    assert "No cleaner for overlays and curves is designed yet" in text
    assert "Curve Data (50xx,xxxx)" in text
    assert "overlay-in-pixel-data" in text
    assert "Options whose policies the engine applies" in text
    applied = next(
        line
        for line in text.splitlines()
        if line.startswith("- Options whose policies the engine applies")
    )
    assert "Clean Graphics Option" in applied


@pytest.mark.parametrize("preset", ["basic", "basic-clean-descriptors"])
def test_a_policy_without_clean_graphics_describes_no_graphics_fallback(preset):
    statement = conformance.conformance_statement(
        policy.compose_policy(preset), vocabulary=None
    )

    assert not any(
        entry.superseded_by == conformance.GRAPHICS_NOT_CLEANED
        for entry in statement.attributes
    )
    text = conformance_markdown.render_markdown(statement)
    assert "No cleaner for overlays and curves is designed yet" not in text
