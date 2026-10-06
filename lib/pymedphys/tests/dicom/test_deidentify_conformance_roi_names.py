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

"""How the conformance statement describes the cleaning of ROI Names (D-009)."""

import dataclasses
import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    descriptor_cleaning,
    instance_transform,
    policy,
    reviewed_roi_names,
    roi_names,
    run,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._nomenclature import tg263
from pymedphys.tests.dicom.test_deidentify_conformance import (
    _entry,
    _section,
    _statement,
)
from pymedphys.tests.dicom.test_deidentify_descriptor_cleaning import (
    _NOMENCLATURE,
    CLEAN_DESCRIPTORS_CODE,
    _codes,
    _structure_set,
    _transform,
    _transformed,
)
from pymedphys.tests.dicom.test_deidentify_method_digest import (
    VOCABULARY,
    _structure,
    _vocabulary,
)

ROI_NAME = "(3006,0026)"


def _published_vocabulary(monkeypatch, edition="TG263 vInvented"):
    """Take the method digest tests' invented vocabulary as published."""
    entries = [dataclasses.asdict(s) for s in VOCABULARY.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, edition, tg263.content_sha256(entries)
    )
    return VOCABULARY


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "PS3.15-E.3.5-02")
@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_roi_name_cleaning_is_described_only_where_roi_name_is_cleaned(preset):
    statement = _statement(preset)
    cleaned = _entry(statement, ROI_NAME).action == "C"
    assert (statement.roi_names is not None) == cleaned
    text = conformance_markdown.render_markdown(statement)
    assert ("## Cleaning ROI names" in text) == cleaned
    assert cleaned == (preset != "basic")


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_without_a_vocabulary_no_roi_name_is_renamed_automatically():
    statement = _statement("basic-clean-descriptors")
    assert statement.roi_names == conformance.RoiNameCleaning(edition=None)
    section = _section(
        conformance_markdown.render_markdown(statement), "Cleaning ROI names"
    )
    assert "without a vocabulary, so no ROI Name is renamed automatically" in section


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_an_unpublished_vocabulary_renames_no_roi_name():
    with pytest.raises(ValueError):
        roi_names.RoiNameVocabulary(VOCABULARY)
    statement = _statement("basic-clean-descriptors", VOCABULARY)
    assert statement.roi_names == conformance.RoiNameCleaning(edition=None)
    section = _section(
        conformance_markdown.render_markdown(statement), "Cleaning ROI names"
    )
    assert "not a published edition" in section
    assert "every ROI Name takes a reviewer's decision" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "PS3.15-E.3.5-02")
def test_a_published_vocabulary_is_named_with_its_edition(monkeypatch):
    vocabulary = _published_vocabulary(monkeypatch)
    statement = _statement("basic-clean-descriptors", vocabulary)
    assert statement.roi_names == conformance.RoiNameCleaning(edition="TG263 vInvented")
    section = _section(
        conformance_markdown.render_markdown(statement), "Cleaning ROI names"
    )
    assert "TG263 vInvented" in section
    assert statement.vocabulary_digest in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "PS3.15-E.3.5-02")
def test_the_described_automatic_renaming_is_the_engines(monkeypatch):
    vocabulary = roi_names.RoiNameVocabulary(_published_vocabulary(monkeypatch))
    section = _section(
        conformance_markdown.render_markdown(_statement("basic-clean-descriptors")),
        "Cleaning ROI names",
    )
    # The examples that the section gives, against a vocabulary holding them.
    for name, written in (("lung l", "Lung_L"), ("LUNG-L", "Lung_L")):
        (decision,) = roi_names.clean_roi_names(
            [name], vocabulary, identifiers=["DOE^JANE"]
        )
        assert decision.value == written
        assert f"`{name}`" in section
    (prefixed,) = roi_names.clean_roi_names(
        ["_Heart"], vocabulary, identifiers=["DOE^JANE"]
    )
    assert prefixed.value is None
    assert "`_Heart`" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "PS3.15-E.3.5-02")
def test_every_review_reason_is_described():
    described = set(conformance_markdown.ROI_REVIEW_REASONS)
    reasons = set(roi_names.Reason) - {
        roi_names.Reason.MATCHED,
        roi_names.Reason.EMPTY,
    }
    assert described == reasons
    section = _section(
        conformance_markdown.render_markdown(_statement("basic-clean-descriptors")),
        "Cleaning ROI names",
    )
    for text in conformance_markdown.ROI_REVIEW_REASONS.values():
        assert text in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "PS3.15-E.3.5-02")
def test_every_reviewer_decision_and_outcome_is_described():
    section = _section(
        conformance_markdown.render_markdown(_statement("basic-clean-descriptors")),
        "Cleaning ROI names",
    )
    for review in reviewed_roi_names.Review:
        assert f"`{review.value}`" in section
    assert set(conformance_markdown.ROI_OUTCOMES) == set(reviewed_roi_names.Outcome)
    for text in conformance_markdown.ROI_OUTCOMES.values():
        assert text in section
    assert "deletes the file from the staging area" in section
    assert "never written to the output" in section


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_the_manner_of_cleaning_roi_names_is_described_not_pending():
    statement = _statement("basic-clean-descriptors")
    assert conformance.PENDING_CLEANING not in statement.pending
    assert "other than ROI Name (3006,0026)" in conformance.PENDING_CLEANING


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_each_other_attribute_given_c_is_described_by_its_fallback_action(preset):
    statement = _statement(preset)
    composed = policy.compose_policy(preset)
    fallen_back = {
        e.tag: e
        for e in statement.attributes
        if e.superseded_by == conformance.CLEAN_DESCRIPTORS_FALLBACK
    }
    if preset == "basic-clean-descriptors":
        fallback = _statement("basic")
        given_c = [
            tag
            for tag, action in composed.actions.items()
            if action == "C" and tag != ROI_NAME
        ]
        assert given_c
        for tag in given_c:
            entry = _entry(statement, tag)
            if entry.superseded_by == conformance.SEQUENCE_NOT_CLEANED:
                continue
            assert entry.superseded_by == conformance.CLEAN_DESCRIPTORS_FALLBACK
            assert entry.policy_action == "C"
            expected = _entry(fallback, tag)
            assert (entry.action, entry.places, entry.elsewhere) == (
                expected.action,
                expected.places,
                expected.elsewhere,
            )
        # Every attribute other than ROI Name now has an action described.
        assert not {e.tag for e in statement.attributes if e.action == "C"} - {ROI_NAME}
        assert conformance.PENDING_CLEANING not in statement.pending
    elif "clean_descriptors" not in composed.options:
        assert not fallen_back
    if "C" in {e.action for e in statement.attributes if e.tag != ROI_NAME}:
        assert conformance.PENDING_CLEANING in statement.pending
    assert all(e.action != "C" and e.policy_action == "C" for e in fallen_back.values())


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_the_described_fallback_is_the_maintainers_decision():
    text = conformance_markdown.render_markdown(_statement("basic-clean-descriptors"))
    actions = _section(text, "Actions")
    assert (
        "takes the action that the policy gives it without Clean Descriptors"
    ) in actions
    assert "decided on 6 October 2026 (D-009)" in actions
    inserted = _section(text, "Attributes inserted")
    assert "not yet described" not in inserted


def _cleaning_published(monkeypatch):
    """Take the descriptor cleaning tests' invented vocabulary as published."""
    entries = [dataclasses.asdict(s) for s in _NOMENCLATURE.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
    )


def _released_codes(transform, dataset):
    """Return the gate's decision on one transformed instance, and its codes."""
    result = _transformed(transform, dataset)
    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    decision = instance_transform.ReleaseGate()(
        result.data, result.evidence, (result.evidence,)
    )
    return written, decision, _codes(written)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "PS3.15-E.3.5-02")
def test_the_described_holding_of_a_roi_name_is_the_engines(monkeypatch):
    _cleaning_published(monkeypatch)
    held = conformance_markdown.ROI_OUTCOMES[reviewed_roi_names.Outcome.HELD]
    assert held.startswith("an empty value")
    assert "holds its instance for review" in held
    written, decision, codes = _released_codes(
        _transform(), _structure_set("lung_l", "SURGEONS ROI")
    )
    assert written.StructureSetROISequence[1].ROIName == ""
    assert isinstance(decision, run.HoldForReview)
    assert CLEAN_DESCRIPTORS_CODE not in codes

    emptied = conformance_markdown.ROI_OUTCOMES[
        reviewed_roi_names.Outcome.EMPTIED_UNREVIEWED
    ]
    assert "released without the Clean Descriptors code" in emptied
    written, decision, codes = _released_codes(
        _transform(empty_held=True), _structure_set("SURGEONS ROI")
    )
    assert written.StructureSetROISequence[0].ROIName == ""
    assert isinstance(decision, run.Release)
    assert CLEAN_DESCRIPTORS_CODE not in codes


@pytest.mark.deid_requirement("PS3.15-E.1.3-01", "PS3.15-E.3.5-02")
def test_the_described_condition_for_the_clean_descriptors_code_is_the_engines(
    monkeypatch,
):
    _cleaning_published(monkeypatch)
    section = _section(
        conformance_markdown.render_markdown(_statement("basic-clean-descriptors")),
        "Attributes inserted",
    )
    assert "pooled human review" not in section
    assert (
        "only in an instance in which every ROI Name (3006,0026) was renamed by "
        "the automatic tier, was empty, or took a reviewer's decision"
    ) in section
    assert "where that action removes or replaces it, the instance still meets" in (
        section
    )
    assert "another attribute given C that that action keeps" in section
    # Renamed automatically, so the instance gains the code.
    _, decision, codes = _released_codes(_transform(), _structure_set("lung_l"))
    assert isinstance(decision, run.Release)
    assert CLEAN_DESCRIPTORS_CODE in codes
    # Another descriptor given C, which its Basic Profile action removes,
    # keeps it.
    written, decision, codes = _released_codes(
        _transform(),
        _structure_set("lung_l", StudyDescription="SENTINEL STUDY"),
    )
    assert "StudyDescription" not in written
    assert CLEAN_DESCRIPTORS_CODE in codes


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_a_policy_whose_fallback_cannot_be_composed_is_pending(preset):
    statement = _statement(preset)
    composed = policy.compose_policy(preset)
    try:
        descriptor_cleaning.fallback_policy(composed)
        refused = False
    except policy.PolicyError:
        refused = "clean_descriptors" in composed.options
    assert (conformance.PENDING_FALLBACK in statement.pending) == refused
    assert refused == (preset == "tps-import")
    if refused:
        with pytest.raises(policy.PolicyError):
            instance_transform.InstanceTransform(
                composed,
                DeidKey(bytes(32)),
                cleaning=descriptor_cleaning.DescriptorCleaning(
                    None, reviewed_roi_names.ReviewedNames.empty()
                ),
                unvalidated_policy=True,
            )


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_the_described_hyphen_and_reverse_order_matching_is_the_engines(monkeypatch):
    vocabulary = _vocabulary(
        _structure("Lung_L", "L_Lung"), _structure("Lungs-PTV", "PTV-Lungs")
    )
    entries = [dataclasses.asdict(s) for s in vocabulary.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
    )
    accepted = roi_names.RoiNameVocabulary(vocabulary)
    section = _section(
        conformance_markdown.render_markdown(
            _statement("basic-clean-descriptors", vocabulary)
        ),
        "Cleaning ROI names",
    )
    assert "primary or reverse-order" in section
    assert "`Lungs-PTV`" in section
    assert "`l lung` becomes the reverse-order `L_Lung`" in section
    for name, written in (
        ("l lung", "L_Lung"),
        ("LUNGS-ptv", "Lungs-PTV"),
        ("Lungs_PTV", None),
        ("Lungs PTV", None),
    ):
        (decision,) = roi_names.clean_roi_names(
            [name], accepted, identifiers=["DOE^JANE"]
        )
        assert decision.value == written


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_the_described_echo_check_is_the_engines(monkeypatch):
    vocabulary = roi_names.RoiNameVocabulary(_published_vocabulary(monkeypatch))
    reason = conformance_markdown.ROI_REVIEW_REASONS[roi_names.Reason.ECHOES_IDENTIFIER]
    assert "a word of more than one character" in reason
    # A one-character word, such as the `L` of `lung l`, is not an echo.
    (renamed,) = roi_names.clean_roi_names(
        ["lung l"], vocabulary, identifiers=["L^QUILLON"]
    )
    assert renamed.value == "Lung_L"
    (echo,) = roi_names.clean_roi_names(
        ["Heart"], vocabulary, identifiers=["HEART^QUILLON"]
    )
    assert echo.value is None
    assert echo.reason is roi_names.Reason.ECHOES_IDENTIFIER


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_the_described_checks_of_reviewed_names_are_the_engines():
    section = _section(
        conformance_markdown.render_markdown(_statement("basic-clean-descriptors")),
        "Cleaning ROI names",
    )
    keep = reviewed_roi_names.ReviewedName(reviewed_roi_names.Review.KEEP, None)
    reviewed = reviewed_roi_names.ReviewedNames(
        None, {"Quillon": keep, "Boost": keep, "BOOST": keep}
    )
    held = reviewed_roi_names.Outcome.HELD
    # A kept name that echoes an identifier is held.
    assert "a kept or mapped name that echoes an identifier" in section
    (echo,) = reviewed_roi_names.clean_roi_names(
        ["Quillon"], None, reviewed, identifiers=["QUILLON^JO"]
    )
    assert (echo.outcome, echo.held_because) == (
        held,
        roi_names.Reason.ECHOES_IDENTIFIER,
    )
    # Names written the same but for case are duplicates; empty names are not.
    assert "ignoring case" in section
    assert "Several empty names are not duplicates." in section
    results = reviewed_roi_names.clean_roi_names(
        ["Boost", "BOOST", "", " "], None, reviewed, identifiers=["DOE^JANE"]
    )
    assert [(r.outcome, r.held_because) for r in results] == [
        (held, roi_names.Reason.WOULD_DUPLICATE),
        (held, roi_names.Reason.WOULD_DUPLICATE),
        (reviewed_roi_names.Outcome.EMPTY, None),
        (reviewed_roi_names.Outcome.EMPTY, None),
    ]
    # A name the list does not cover is held.
    (unreviewed,) = reviewed_roi_names.clean_roi_names(
        ["Ring"], None, reviewed, identifiers=["DOE^JANE"]
    )
    assert unreviewed.outcome is held


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_a_run_with_a_reviewed_list_records_a_different_digest():
    section = _section(
        conformance_markdown.render_markdown(_statement("basic-clean-descriptors")),
        "Cleaning ROI names",
    )
    assert "records the list's keyed digest in its method digest" in section
