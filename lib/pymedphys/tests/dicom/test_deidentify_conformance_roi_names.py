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

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    policy,
    reviewed_roi_names,
    roi_names,
)
from pymedphys._nomenclature import tg263
from pymedphys.tests.dicom.test_deidentify_conformance import (
    _entry,
    _section,
    _statement,
)
from pymedphys.tests.dicom.test_deidentify_method_digest import VOCABULARY

ROI_NAME = "(3006,0026)"


def _published_vocabulary(monkeypatch, edition="TG263 vInvented"):
    """Take the method digest tests' invented vocabulary as published."""
    entries = [dataclasses.asdict(s) for s in VOCABULARY.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, edition, tg263.content_sha256(entries)
    )
    return VOCABULARY


@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_roi_name_cleaning_is_described_only_where_roi_name_is_cleaned(preset):
    statement = _statement(preset)
    cleaned = _entry(statement, ROI_NAME).action == "C"
    assert (statement.roi_names is not None) == cleaned
    text = conformance_markdown.render_markdown(statement)
    assert ("## Cleaning ROI names" in text) == cleaned
    assert cleaned == (preset != "basic")


def test_without_a_vocabulary_no_roi_name_is_renamed_automatically():
    statement = _statement("basic-clean-descriptors")
    assert statement.roi_names == conformance.RoiNameCleaning(edition=None)
    section = _section(
        conformance_markdown.render_markdown(statement), "Cleaning ROI names"
    )
    assert "without a vocabulary, so no ROI Name is renamed automatically" in section


def test_an_unpublished_vocabulary_renames_no_roi_name():
    with pytest.raises(ValueError):
        roi_names.RoiNameVocabulary(VOCABULARY)
    statement = _statement("basic-clean-descriptors", VOCABULARY)
    assert statement.roi_names == conformance.RoiNameCleaning(edition=None)
    section = _section(
        conformance_markdown.render_markdown(statement), "Cleaning ROI names"
    )
    assert "not a published edition" in section


def test_a_published_vocabulary_is_named_with_its_edition(monkeypatch):
    vocabulary = _published_vocabulary(monkeypatch)
    statement = _statement("basic-clean-descriptors", vocabulary)
    assert statement.roi_names == conformance.RoiNameCleaning(edition="TG263 vInvented")
    section = _section(
        conformance_markdown.render_markdown(statement), "Cleaning ROI names"
    )
    assert "TG263 vInvented" in section
    assert statement.vocabulary_digest in section


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
    assert "staging area" in section
    assert "never written to the output" in section


def test_cleaning_of_roi_names_is_not_pending():
    statement = _statement("basic-clean-descriptors")
    assert conformance.PENDING_CLEANING in statement.pending
    assert "other than ROI Name (3006,0026)" in conformance.PENDING_CLEANING
