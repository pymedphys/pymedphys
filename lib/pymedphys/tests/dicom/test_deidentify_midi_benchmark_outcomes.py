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

"""Score MIDI checks that the policy, the markers, or the source explain (D-018)."""

import collections

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_sources as sources
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.file_layout import ElementPath, Location, Region
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.midi_answer_key import parse_check
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.reasons import RunReason
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    ReleaseReason,
)

from .test_deidentify_midi_benchmark import (
    CT_IOD,
    FAILED,
    MAPPING,
    STUDY_DESCRIPTION,
    _check,
    _released_ct,
    _score,
    read_answer_check,
)


def test_a_kept_check_on_what_the_policy_removes_is_a_deliberate_difference():
    # Study Description is X under the Basic Profile, and a private
    # attribute is removed whatever its creator.
    assert _score(
        "text_retained", "<(0008,1030)>", text=STUDY_DESCRIPTION
    ) == benchmark.Scored(benchmark.Result.FAILED, "X", deliberate=True)
    assert _score("tag_retained", '<(0019,"OTHER CREATOR",93)>') == benchmark.Scored(
        benchmark.Result.FAILED, "X", deliberate=True
    )


def test_a_kept_check_in_a_sequence_that_the_policy_removes_is_deliberate():
    # Referenced Study Sequence is X/Z under the Basic Profile and Type 3 in
    # the CT Image IOD, so the walker removes it with what it holds, whatever
    # the attribute's own action.
    assert _score(
        "tag_retained", "<(0008,1110)>[<0000>]<(0008,1150)>"
    ) == benchmark.Scored(benchmark.Result.FAILED, "X", deliberate=True)


@pytest.mark.parametrize("action", ["tag_retained", "text_notnull"])
def test_a_compound_action_that_selects_removal_is_deliberate(action):
    # Series Date is X/D and Type 3 in the CT Image IOD: the walker selects X.
    assert _score(action, "<(0008,0021)>") == benchmark.Scored(
        benchmark.Result.FAILED, "X", deliberate=True
    )


@pytest.mark.parametrize(
    "action, place, iod",
    [
        # RT Plan Date is X/D and Type 2 in the RT Plan IOD: the walker
        # selects D, so the attribute must be present with a dummy value.
        ("tag_retained", "<(300A,0006)>", "RT Plan"),
        ("text_notnull", "<(300A,0006)>", "RT Plan"),
        # Patient Species Description is X/Z/D and Type 1C in the CT Image
        # IOD: D, so neither its absence nor an empty value is deliberate.
        ("tag_retained", "<(0010,2201)>", "CT Image"),
        ("text_notnull", "<(0010,2201)>", "CT Image"),
        # A plain Z on a Type 1 attribute selects D.
        (
            "text_notnull",
            "<(300A,0614)>[<0000>]<(300A,0610)>[<0000>]<(300A,0611)>",
            "C-Arm Photon-Electron Radiation",
        ),
        # Referenced Image Sequence is X/Z/U* and Type 1C inside Referenced
        # Spatial Registration Sequence in the RT Dose IOD: the walker keeps
        # it as a container (U), so it does not explain its items' absence.
        (
            "tag_retained",
            "<(300C,0116)>[<0000>]<(0008,1140)>[<0000>]<(0008,1150)>",
            "RT Dose",
        ),
    ],
)
def test_a_missing_attribute_that_the_selected_action_replaces_is_a_finding(
    action, place, iod
):
    assert _score(action, place, iod=iod) == FAILED


def test_a_kept_check_on_what_the_policy_keeps_is_a_finding():
    # The Basic Profile keeps Rows, so its absence is not deliberate.
    assert _score("tag_retained", "<(0028,0010)>") == FAILED


@pytest.mark.parametrize(
    "place",
    [
        # Patient's Name is Z and Study Instance UID is U: the policy
        # replaces them, so a file without them breaks the policy.
        "<(0010,0010)>",
        "<(0020,000D)>",
        # The CT Image IOD defines Derivation Code Sequence, which the
        # Basic Profile therefore keeps; without the IOD it would be removed.
        "<(0008,9215)>",
    ],
)
def test_a_missing_attribute_that_the_policy_replaces_or_keeps_is_a_finding(place):
    assert _score("tag_retained", place) == FAILED


def test_without_the_iod_no_failure_is_deliberate():
    # The walker selects no action without the IOD, so nothing explains a
    # failure, even of an attribute that the policy removes.
    assert _score("tag_retained", "<(0008,9215)>", iod=None) == FAILED
    assert (
        _score("text_retained", "<(0008,1030)>", text=STUDY_DESCRIPTION, iod=None)
        == FAILED
    )


def test_changed_pixel_data_is_never_deliberate():
    assert _score("pixels_retained", "<(7FE0,0010)>", text="0" * 32) == FAILED


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
    "categories",
    [{"tcia_rev": "TEST-REV"}, {"tcia_p15": "TEST-P15"}, {"hipaa_z": "TEST-Z"}, {}],
)
def test_a_removed_text_that_the_policy_keeps_is_a_finding(categories):
    # The Basic Profile keeps Modality. A kept value could still carry an
    # identifier, so no category makes its failure deliberate.
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
        == FAILED
    )


@pytest.mark.parametrize(
    "value, answer, expected",
    [
        ("3", "3", ("IS", "1 to 4 digits", True)),
        ("20240131", "20240131", ("IS", "8 digits, a date", True)),
        ("20241399", "2024", ("IS", "8 digits", False)),
        ("123456789", "123456789", ("IS", "9 or more digits", True)),
    ],
)
def test_a_removed_text_is_described_by_its_shape(value, answer, expected):
    source = _released_ct()
    source.SeriesNumber = value
    check = read_answer_check("text_removed", "<(0020,0011)>", text=answer)

    assert sources.removed_shape(source, check) == expected


def test_a_removed_text_of_another_vr_is_described_by_its_vr():
    check = read_answer_check("text_removed", "<(0008,0060)>", text="ct")

    assert sources.removed_shape(_released_ct(), check) == ("CS", "not IS", False)
    assert sources.removed_shape(pydicom.Dataset(), check) == (
        "none",
        "absent",
        False,
    )


@pytest.mark.parametrize(
    "place, expected",
    [
        ("<(0018,0060)>", "absent"),
        ("<(0008,0020)>", "empty"),
        ("<(0008,0060)>", "value"),
    ],
)
def test_the_source_state_says_whether_the_attribute_and_a_value_are_there(
    place, expected
):
    check = read_answer_check("tag_retained", place)

    assert sources.source_state(_released_ct(), check) == expected


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


def test_a_withheld_instance_is_counted_by_where_its_reasons_were_found():
    beam = ElementPath(items=(("(300A,00B0)", 2),), tag="(300A,00C3)")
    reasons = (
        ReleaseReason(
            Decision.QC_REVIEW,
            ReasonCode.RESIDUAL_TEXT,
            ElementPath(items=(), tag="(0010,0010)"),
            Location(Region.DATA_SET, beam, "ST"),
        ),
        ReleaseReason(Decision.WITHHOLD, ReasonCode.UNCOLLECTED, beam),
        ReleaseReason(
            Decision.WITHHOLD,
            ReasonCode.RESIDUAL_OUTSIDE_DATA_SET,
            beam,
            Location(Region.TRAILING),
        ),
        RunReason.INTERNAL_ERROR,
    )

    places = sources.reason_places(reasons)
    rows = sources.place_rows(collections.Counter([*places, *places]))

    assert places == {
        ("residual-text", "(0010,0010)", "(300A,00B0)/(300A,00C3)", "ST"),
        ("uncollected", "(300A,00B0)/(300A,00C3)", "", ""),
        ("residual-outside-data-set", "(300A,00B0)/(300A,00C3)", "trailing-bytes", ""),
    }
    assert rows[0]["instances"] == 2
    assert {row["code"] for row in rows} == {
        "residual-text",
        "uncollected",
        "residual-outside-data-set",
    }
