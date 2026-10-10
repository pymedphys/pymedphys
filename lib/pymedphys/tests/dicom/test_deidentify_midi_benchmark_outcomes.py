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

"""Score MIDI checks that markers, curation, or the source explain (D-018)."""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.midi_answer_key import parse_check
from pymedphys._dicom.deidentify.policy import compose_policy

from .test_deidentify_midi_benchmark import (
    CT_IOD,
    FAILED,
    MAPPING,
    _check,
    _released_ct,
    read_answer_check,
)


@pytest.mark.parametrize(
    "keyword, value, place",
    [
        ("PatientIdentityRemoved", "YES", "<(0012,0062)>"),
        ("LongitudinalTemporalInformationModified", "REMOVED", "<(0028,0303)>"),
    ],
)
@pytest.mark.parametrize("iod", [CT_IOD, None])
def test_a_kept_value_that_a_marker_replaces_is_a_deliberate_difference(
    keyword, value, place, iod
):
    released = _released_ct()
    setattr(released, keyword, value)
    check = read_answer_check("text_retained", place, text="NO")
    rules = ElementRules(compose_policy("basic"))
    tables = load_iod_tables()

    scored = benchmark.score_check(
        check, released, MAPPING, rules, None if iod is None else tables.iods[iod]
    )
    missing = benchmark.score_check(check, _released_ct(), MAPPING, rules)

    assert scored == benchmark.Scored(
        benchmark.Result.FAILED, "marker", deliberate=True
    )
    # A marker that the release lacks explains nothing.
    assert missing == FAILED


@pytest.mark.parametrize(
    "categories, expected",
    [
        (
            {"tcia_rev": "TEST-REV"},
            benchmark.Scored(benchmark.Result.FAILED, "K", deliberate=True),
        ),
        (
            {"tcia_p15": "TEST-P15"},
            benchmark.Scored(benchmark.Result.FAILED, "K", deliberate=True),
        ),
        ({"hipaa_z": "TEST-Z", "tcia_rev": "TEST-REV"}, FAILED),
        ({}, FAILED),
    ],
)
def test_a_removed_text_that_the_policy_keeps_is_deliberate_only_for_tcia(
    categories, expected
):
    # The Basic Profile keeps Modality; a check under HIPAA scores under it.
    check = parse_check(
        _check("text_removed", "<(0008,0060)>", text="CT", **categories)
    )

    assert (
        benchmark.score_check(
            check,
            _released_ct(),
            MAPPING,
            ElementRules(compose_policy("basic")),
            load_iod_tables().iods[CT_IOD],
        )
        == expected
    )


def test_a_removed_text_in_a_sequence_that_the_policy_removes_is_a_finding():
    released = _released_ct()
    released.ReferencedStudySequence = [pydicom.Dataset()]
    released.ReferencedStudySequence[0].ReferencedSOPInstanceUID = "2.25.77"
    check = parse_check(
        _check(
            "text_removed",
            "<(0008,1110)>[<0000>]<(0008,1155)>",
            text="2.25.77",
            tcia_rev="TEST-REV",
        )
    )

    assert (
        benchmark.score_check(
            check,
            released,
            MAPPING,
            ElementRules(compose_policy("basic")),
            load_iod_tables().iods[CT_IOD],
        )
        == FAILED
    )


@pytest.mark.parametrize(
    "action, place, gap",
    [
        # The source has no KVP and no Study Date value.
        ("tag_retained", "<(0018,0060)>", True),
        ("text_notnull", "<(0008,0020)>", True),
        # The source has Rows, so its absence is the release's.
        ("tag_retained", "<(0028,0010)>", False),
        ("text_notnull", "<(0028,0010)>", False),
    ],
)
def test_a_present_check_that_fails_on_the_source_too_is_a_source_gap(
    action, place, gap
):
    source = _released_ct()
    source.Rows = 2
    check = read_answer_check(action, place)

    scored = benchmark.source_gap(check, source, FAILED)

    assert scored == (
        benchmark.Scored(
            benchmark.Result.FAILED, "absent from the source", source_gap=True
        )
        if gap
        else FAILED
    )


def test_only_a_finding_of_a_present_check_can_be_a_source_gap():
    source = _released_ct()
    deliberate = benchmark.Scored(benchmark.Result.FAILED, "X", deliberate=True)

    assert (
        benchmark.source_gap(
            read_answer_check("tag_retained", "<(0018,0060)>"), source, deliberate
        )
        == deliberate
    )
    assert (
        benchmark.source_gap(
            read_answer_check("text_retained", "<(0018,0060)>", text="120"),
            source,
            FAILED,
        )
        == FAILED
    )
    assert (
        benchmark.source_gap(
            read_answer_check("tag_retained", "<(0018,0060)>"), None, FAILED
        )
        == FAILED
    )
