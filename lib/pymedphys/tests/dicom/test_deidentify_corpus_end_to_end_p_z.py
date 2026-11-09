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

"""The second half of the policies' end-to-end runs over the synthetic corpus.

:mod:`~pymedphys.tests.dicom.test_deidentify_corpus_end_to_end` runs each
policy whose name begins with a letter from a to o, and holds every check
of a policy's run and the tests that need no policy's run. This module runs
the other policies, from p to z, through the same checks: each test here
calls the first half's test of the same name and cites the same
requirements, so the register names both halves' tests. CI runs this module
in a part of its own, so that neither half reaches the time limit.
"""

import inspect

from pymedphys._imports import pytest

from . import test_deidentify_corpus_end_to_end as first_half
from .test_deidentify_corpus_end_to_end import SECOND_HALF

# The first half's fixture, which pytest finds here by its name.
from .test_deidentify_corpus_end_to_end import (  # noqa: F401  # pylint: disable = unused-import
    fixture_published,
)

pytestmark = pytest.mark.pydicom


@pytest.fixture(
    name="policy_run",
    scope="module",
    params=[corpus_run.param() for corpus_run in SECOND_HALF],
)
def fixture_policy_run(request, published):  # pylint: disable = unused-argument
    yield first_half._run(request.param)  # pylint: disable = protected-access


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-03", "PS3.15-E.1.1-09")
def test_each_run_releases_all_but_the_instances_it_must_withhold(policy_run):
    first_half.test_each_run_releases_all_but_the_instances_it_must_withhold(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_each_cleaned_image_is_listed_and_previewed_frame_by_frame(policy_run):
    first_half.test_each_cleaned_image_is_listed_and_previewed_frame_by_frame(
        policy_run
    )


@pytest.mark.deid_requirement(
    "MIDI-BP-01",
    "PS3.15-E.1.1-01",
    "PS3.15-E.1.1-04",
    "PS3.15-E.1.1-06",
    "PS3.15-E.1.1-09",
    "PS3.15-E.3.10-02",
    "MIDI-BP-05",
    "MIDI-BP-11",
    "MIDI-BP-13",
)
def test_no_published_file_holds_a_marker(policy_run):
    first_half.test_no_published_file_holds_a_marker(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_a_kept_marker_anywhere_but_its_place_is_found(policy_run):
    first_half.test_a_kept_marker_anywhere_but_its_place_is_found(policy_run)


@pytest.mark.deid_requirement("MIDI-BP-14", "PS3.15-E.1.1-02")
def test_released_images_keep_their_transfer_syntax_and_pixels(policy_run):
    first_half.test_released_images_keep_their_transfer_syntax_and_pixels(policy_run)


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.1-01", "PS3.15-E.1.1-09")
def test_no_released_file_keeps_a_numeric_marker_at_its_place(policy_run):
    first_half.test_no_released_file_keeps_a_numeric_marker_at_its_place(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_each_kept_marker_is_kept_at_its_place(policy_run):
    first_half.test_each_kept_marker_is_kept_at_its_place(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_each_sequence_of_content_items_a_run_keeps_keeps_its_items(policy_run):
    first_half.test_each_sequence_of_content_items_a_run_keeps_keeps_its_items(
        policy_run
    )


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.1.1-09")
def test_no_released_file_keeps_a_removed_sequence_without_a_marker(policy_run):
    first_half.test_no_released_file_keeps_a_removed_sequence_without_a_marker(
        policy_run
    )


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_no_warning_or_log_record_shows_a_marker(policy_run):
    first_half.test_no_warning_or_log_record_shows_a_marker(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.1.1-05", "PS3.15-E.3.5-01")
def test_every_released_instance_claims_the_policys_options(policy_run):
    first_half.test_every_released_instance_claims_the_policys_options(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.3.2-02")
def test_recognizable_visual_features_is_no_exactly_where_the_option_is_claimed(
    policy_run,
):
    first_half.test_recognizable_visual_features_is_no_exactly_where_the_option_is_claimed(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.3.1-02")
def test_burned_in_annotation_is_no_exactly_where_the_option_is_claimed(policy_run):
    first_half.test_burned_in_annotation_is_no_exactly_where_the_option_is_claimed(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-05", "PS3.15-E.2-01")
def test_every_released_instance_carries_the_profiles_markers(policy_run):
    first_half.test_every_released_instance_carries_the_profiles_markers(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01", "MIDI-BP-14")
def test_instances_keep_their_reviewed_dummy_values(policy_run):
    first_half.test_instances_keep_their_reviewed_dummy_values(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.1.1-04", "MIDI-BP-03")
def test_each_registration_ties_its_images_to_the_frame_as_written(policy_run):
    first_half.test_each_registration_ties_its_images_to_the_frame_as_written(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-04", "MIDI-BP-03")
def test_the_rt_image_names_its_plan_as_written(policy_run):
    first_half.test_the_rt_image_names_its_plan_as_written(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.1.1-04", "MIDI-BP-03")
def test_the_enhanced_rt_images_name_their_plan_as_written(policy_run):
    first_half.test_the_enhanced_rt_images_name_their_plan_as_written(policy_run)


@pytest.mark.deid_requirement("PS3.15-E.3.4-01", "MIDI-BP-03")
def test_the_patient_dose_report_names_the_ct_dose_report_as_written(policy_run):
    first_half.test_the_patient_dose_report_names_the_ct_dose_report_as_written(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-04", "MIDI-BP-03")
def test_the_rt_ion_plan_and_its_record_name_what_they_reference_as_written(policy_run):
    first_half.test_the_rt_ion_plan_and_its_record_name_what_they_reference_as_written(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01", "MIDI-BP-03")
def test_each_interlock_users_institution_code_sequence_is_released_as_reviewed(
    policy_run,
):
    first_half.test_each_interlock_users_institution_code_sequence_is_released_as_reviewed(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-04", "MIDI-BP-03")
def test_the_brachy_and_summary_records_name_what_they_reference_as_written(policy_run):
    first_half.test_the_brachy_and_summary_records_name_what_they_reference_as_written(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-04", "MIDI-BP-03")
def test_the_delivery_instructions_name_what_they_reference_as_written(policy_run):
    first_half.test_the_delivery_instructions_name_what_they_reference_as_written(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
def test_the_brachy_records_source_manufacturer_is_emptied_or_kept(policy_run):
    first_half.test_the_brachy_records_source_manufacturer_is_emptied_or_kept(
        policy_run
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_roi_names_take_the_vocabulary_spelling_or_the_reviewed_decision(policy_run):
    first_half.test_roi_names_take_the_vocabulary_spelling_or_the_reviewed_decision(
        policy_run
    )


def _checks(namespace):
    """Return the tests in ``namespace`` that read a policy's run, by name."""
    return {
        name: function
        for name, function in namespace.items()
        if name.startswith("test")
        and callable(function)
        and "policy_run" in inspect.signature(function).parameters
    }


def _citations(function):
    return [
        mark.args
        for mark in getattr(function, "pytestmark", [])
        if mark.name == "deid_requirement"
    ]


def test_each_check_of_a_policys_run_runs_in_both_halves():
    """A check added to the first half fails here until this half runs it too."""
    first, here = _checks(vars(first_half)), _checks(globals())

    assert first
    assert sorted(here) == sorted(first)
    for name, function in here.items():
        assert _citations(function) == _citations(first[name]), name
        assert f"first_half.{name}(" in inspect.getsource(function), name
