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
"""The reviewed descriptors list, and the decisions it gives descriptor values.

Every descriptor value and identifier here is synthetic.
"""

import hashlib
import hmac
import json
import os
import pathlib
from unittest import mock

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import keys
from pymedphys._dicom.deidentify import reviewed_descriptors as reviewed
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    Held,
    Outcome,
    ReviewedDescriptor,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")

SERIES_DESCRIPTION = "(0008,103E)"  # LO
SEQUENCE_NAME = "(0018,0024)"  # SH, a reviewed rule for text Table E.1-1 omits
IMAGE_COMMENTS = "(0020,4000)"  # LT
ADMITTING_DIAGNOSES = "(0008,1080)"  # LO, 1-n
KEEP = ReviewedDescriptor(Review.KEEP)
EMPTY = ReviewedDescriptor(Review.EMPTY)


def _map(to):
    return ReviewedDescriptor(Review.MAP, to)


@pytest.fixture(name="home", autouse=True)
def fixture_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


def _list(*decisions):
    listed = reviewed.ReviewedDescriptors.empty()
    for tag, value, decision in decisions:
        listed.record(tag, value, decision)
    return listed


def test_the_attributes_are_the_text_descriptors_that_clean_descriptors_cleans():
    attributes = reviewed.descriptor_attributes()

    assert attributes[SERIES_DESCRIPTION] == "LO"
    assert attributes[IMAGE_COMMENTS] == "LT"
    assert attributes[SEQUENCE_NAME] == "SH"
    # ROI Name has its own list; sequences, binary values, and code strings
    # given C, and attributes that are never C, are not descriptors.
    for tag in (
        "(3006,0026)",  # ROI Name
        "(0008,1084)",  # Admitting Diagnoses Code Sequence
        "(0016,002B)",  # Maker Note, OB
        "(0400,0565)",  # Reason for the Attribute Modification, CS
        "(0008,0080)",  # Institution Name, X under every option
        "(0010,0010)",  # Patient's Name
    ):
        assert tag not in attributes
    assert set(attributes.values()) <= set(reviewed.MAX_CHARACTERS)
    with pytest.raises(TypeError):
        attributes[SERIES_DESCRIPTION] = "SH"


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_reviewed_decisions_are_reused_on_later_runs(tmp_path):
    path = tmp_path / "custodian" / "reviewed-descriptors.json"
    path.parent.mkdir()
    first = reviewed.ReviewedDescriptors.open(path)
    first.record(SERIES_DESCRIPTION, "AX T1 POST", KEEP)
    first.record(SERIES_DESCRIPTION, "Dr Ng protocol", _map("Protocol A"))
    first.record(IMAGE_COMMENTS, "Called Mrs Ng\r\nre: prep", EMPTY)
    first.save()

    later = reviewed.ReviewedDescriptors.open(path)

    assert len(later) == 3
    assert later.get(SERIES_DESCRIPTION, "AX T1 POST") == KEEP
    assert later.get(SERIES_DESCRIPTION, "Dr Ng protocol") == _map("Protocol A")
    assert later.get(IMAGE_COMMENTS, "Called Mrs Ng\r\nre: prep") == EMPTY
    assert later.get(SERIES_DESCRIPTION, "ax t1 post") is None
    # A decision is for one attribute.
    assert later.get("(0018,1030)", "AX T1 POST") is None


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_list_never_shows_a_value():
    listed = _list(
        (SERIES_DESCRIPTION, "AX T1 POST", KEEP),
        (SERIES_DESCRIPTION, "Dr Ng protocol", _map("Protocol A")),
    )

    shown = repr(listed) + repr(listed.get(SERIES_DESCRIPTION, "Dr Ng protocol"))

    for value in ("AX", "POST", "Ng", "Protocol"):
        assert value not in shown


@pytest.mark.parametrize(
    "decision",
    [
        lambda: ReviewedDescriptor(Review.MAP),
        lambda: ReviewedDescriptor(Review.KEEP, "Chest"),
        lambda: ReviewedDescriptor(Review.MAP, ""),
        lambda: ReviewedDescriptor(Review.MAP, " Chest"),
        lambda: ReviewedDescriptor(Review.MAP, "Chest\nAbdomen"),
        lambda: ReviewedDescriptor(Review.MAP, "Thorax Ü"),
        lambda: ReviewedDescriptor("keep"),
    ],
)
def test_a_mapping_needs_a_printable_ascii_value(decision):
    with pytest.raises((TypeError, ValueError)) as error:
        decision()

    assert "Chest" not in str(error.value) and "Thorax" not in str(error.value)


@pytest.mark.parametrize(
    "tag, to",
    [
        (SEQUENCE_NAME, "S" * 17),  # SH holds 16
        (SERIES_DESCRIPTION, "S" * 65),  # LO holds 64
        (SERIES_DESCRIPTION, "Chest\\Abdomen"),  # a second value
    ],
)
def test_a_mapping_must_fit_the_attributes_vr(tag, to):
    with pytest.raises(reviewed.ReviewedDescriptorsError, match="value to write"):
        _list((tag, "Chest", _map(to)))


def test_text_vrs_can_map_to_a_backslash_and_long_values():
    listed = _list(
        (IMAGE_COMMENTS, "Chest", _map("left\\right " + "x" * 1000)),
        (SEQUENCE_NAME, "Chest", _map("S" * 16)),
    )

    assert len(listed) == 2


@pytest.mark.parametrize(
    "tag, value",
    [
        (SERIES_DESCRIPTION, ""),
        (SERIES_DESCRIPTION, " AX T1"),
        (SERIES_DESCRIPTION, "AX T1\x00"),
        (SERIES_DESCRIPTION, "AX\\T1"),  # two values of LO
        (SERIES_DESCRIPTION, "AX\nT1"),  # LO holds no control character
        (IMAGE_COMMENTS, "AX\x1bT1"),  # ESC is not allowed even in LT
        (SERIES_DESCRIPTION, "AX\ud800"),
        (SERIES_DESCRIPTION, 3),
    ],
)
def test_a_reviewed_value_must_be_one_unpadded_value_of_its_vr(tag, value):
    with pytest.raises(reviewed.ReviewedDescriptorsError) as error:
        _list((tag, value, KEEP))

    assert "AX" not in str(error.value)


@pytest.mark.parametrize(
    "tag", ["(3006,0026)", "(0008,0080)", "(0008,1084)", "(0008,103e)", None]
)
def test_only_a_descriptor_that_clean_descriptors_cleans_can_be_decided_on(tag):
    with pytest.raises(reviewed.ReviewedDescriptorsError, match="not a descriptor"):
        _list((tag, "AX T1", KEEP))


def test_text_vrs_keep_their_line_breaks_and_backslashes():
    listed = _list((IMAGE_COMMENTS, "line one\r\nline\\two\tend", KEEP))

    assert listed.get(IMAGE_COMMENTS, "line one\r\nline\\two\tend") == KEEP


def test_a_non_ascii_value_can_be_reviewed():
    listed = _list((SERIES_DESCRIPTION, "Thorax nativ Ü", _map("Thorax")))

    assert listed.get(SERIES_DESCRIPTION, "Thorax nativ Ü") == _map("Thorax")


def test_a_different_decision_replaces_the_recorded_one_only_when_asked():
    listed = _list((SERIES_DESCRIPTION, "AX T1", KEEP))
    listed.record(SERIES_DESCRIPTION, "AX T1", KEEP)

    with pytest.raises(reviewed.ReviewedDescriptorsError, match="already has a"):
        listed.record(SERIES_DESCRIPTION, "AX T1", EMPTY)
    listed.record(SERIES_DESCRIPTION, "AX T1", EMPTY, replace=True)

    assert listed.get(SERIES_DESCRIPTION, "AX T1") == EMPTY and len(listed) == 1


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize("where", ["config", "protected"])
def test_the_list_is_refused_inside_a_protected_directory(tmp_path, where):
    if where == "config":
        directory = pathlib.Path.home() / ".pymedphys"
    else:
        directory = tmp_path / "output"
    directory.mkdir()

    with pytest.raises(reviewed.ReviewedDescriptorsError, match="refusing"):
        reviewed.ReviewedDescriptors.open(
            directory / "reviewed.json", protected_dirs=[tmp_path / "output"]
        )


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


GOOD = {
    "format": reviewed.FORMAT,
    "attributes": {
        SERIES_DESCRIPTION: {
            "AX T1": {"review": "keep"},
            "Dr Ng": {"review": "map", "to": "Protocol"},
        },
        IMAGE_COMMENTS: {"Mrs Ng called": {"review": "empty"}},
    },
}


@pytest.mark.parametrize(
    "document",
    [
        [],
        {**GOOD, "format": "pymedphys-deid-reviewed-descriptors/0"},
        {**GOOD, "format": "pymedphys-deid-reviewed-roi-names/1"},
        {**GOOD, "format": []},
        {**GOOD, "format": {}},
        {**GOOD, "extra": 1},
        {"format": reviewed.FORMAT},
        {**GOOD, "attributes": []},
        {**GOOD, "attributes": {SERIES_DESCRIPTION: []}},
        {**GOOD, "attributes": {SERIES_DESCRIPTION: {}}},
        {**GOOD, "attributes": {"(3006,0026)": {"AX T1": {"review": "keep"}}}},
        {**GOOD, "attributes": {SERIES_DESCRIPTION: {"AX T1": {"review": "x"}}}},
        {**GOOD, "attributes": {SERIES_DESCRIPTION: {"AX T1": "keep"}}},
        {
            **GOOD,
            "attributes": {
                SERIES_DESCRIPTION: {"AX T1": {"review": "keep", "to": "AX"}}
            },
        },
        {**GOOD, "attributes": {SERIES_DESCRIPTION: {"AX T1": {"review": "map"}}}},
        {
            **GOOD,
            "attributes": {SEQUENCE_NAME: {"AX T1": {"review": "map", "to": "AX" * 9}}},
        },
        {**GOOD, "attributes": {SERIES_DESCRIPTION: {" AX T1": {"review": "keep"}}}},
        {**GOOD, "attributes": {SERIES_DESCRIPTION: {"AX\\T1": {"review": "keep"}}}},
    ],
)
def test_a_malformed_list_is_refused_without_quoting_it(tmp_path, document):
    path = _write(tmp_path / "reviewed.json", document)

    with pytest.raises(reviewed.ReviewedDescriptorsError) as error:
        reviewed.ReviewedDescriptors.open(path)

    for value in ("AX", "Ng", "Protocol"):
        assert value not in str(error.value)


def test_a_list_with_a_repeated_value_is_refused(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_text(
        '{"format": "%s", "attributes": {"%s": {"AX": {"review": "keep"}, '
        '"AX": {"review": "empty"}}}}' % (reviewed.FORMAT, SERIES_DESCRIPTION),
        encoding="utf-8",
    )

    with pytest.raises(
        reviewed.ReviewedDescriptorsError,
        match="item 2 of an object in the list is repeated",
    ):
        reviewed.ReviewedDescriptors.open(path)


def test_an_unreadable_list_is_refused_without_its_text(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_bytes(b'{"format": "x", "attributes": {"Ng chest": \xff')

    with pytest.raises(
        reviewed.ReviewedDescriptorsError, match="could not be read"
    ) as error:
        reviewed.ReviewedDescriptors.open(path)

    assert error.value.__cause__ is None and error.value.__suppress_context__


def test_an_empty_list_is_never_saved():
    with pytest.raises(reviewed.ReviewedDescriptorsError, match="no file"):
        reviewed.ReviewedDescriptors.empty().save()


def test_the_saved_list_is_sorted_and_round_trips(tmp_path):
    path = _write(tmp_path / "reviewed.json", GOOD)
    listed = reviewed.ReviewedDescriptors.open(path)
    listed.record(SERIES_DESCRIPTION, "A value", EMPTY)
    listed.record(SEQUENCE_NAME, "*tfl3d1", KEEP)
    listed.save()

    document = json.loads(path.read_text(encoding="utf-8"))
    assert list(document["attributes"]) == [
        SERIES_DESCRIPTION,
        SEQUENCE_NAME,
        IMAGE_COMMENTS,
    ]
    assert list(document["attributes"][SERIES_DESCRIPTION]) == [
        "A value",
        "AX T1",
        "Dr Ng",
    ]
    assert reviewed.ReviewedDescriptors.open(path).get(SEQUENCE_NAME, "*tfl3d1") == KEEP


@posix_only
def test_the_saved_list_is_readable_only_by_its_owner(tmp_path):
    path = tmp_path / "reviewed.json"
    listed = reviewed.ReviewedDescriptors.open(path)
    listed.record(SERIES_DESCRIPTION, "AX T1", KEEP)
    listed.save()

    assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home", "reviewed.json"]


def test_a_failed_save_leaves_the_previous_list_and_no_partial_file(tmp_path):
    path = _write(tmp_path / "reviewed.json", GOOD)
    before = path.read_bytes()
    listed = reviewed.ReviewedDescriptors.open(path)
    listed.record(SERIES_DESCRIPTION, "A value", EMPTY)

    with mock.patch.object(os, "replace", side_effect=OSError("disk")):
        with pytest.raises(OSError):
            listed.save()

    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home", "reviewed.json"]


def test_a_snapshot_keeps_the_decisions_as_they_stood_and_is_never_saved():
    listed = _list((SERIES_DESCRIPTION, "AX T1", KEEP))
    snapshot = listed.snapshot()
    listed.record(SERIES_DESCRIPTION, "AX T2", KEEP)
    snapshot.record(IMAGE_COMMENTS, "Note", EMPTY)

    assert len(snapshot) == 2 and snapshot.get(SERIES_DESCRIPTION, "AX T2") is None
    assert len(listed) == 2 and listed.get(IMAGE_COMMENTS, "Note") is None
    with pytest.raises(reviewed.ReviewedDescriptorsError, match="no file"):
        snapshot.save()


def test_the_keyed_digest_is_the_hmac_of_the_lists_canonical_form():
    key = keys.DeidKey.generate()
    listed = _list(
        (SERIES_DESCRIPTION, "Thorax Ü", KEEP),
        (IMAGE_COMMENTS, "x", _map("y")),
    )

    canonical = listed.canonical_bytes()

    assert canonical == (
        '{"attributes":{"(0008,103E)":{"Thorax Ü":{"review":"keep"}},'
        '"(0020,4000)":{"x":{"review":"map","to":"y"}}},'
        f'"format":"{reviewed.FORMAT}"}}'
    ).encode("utf-8")
    assert (
        listed.keyed_digest(key) == key.derive(reviewed.DIGEST_DOMAIN, canonical).hex()
    )


def test_the_keyed_digest_ignores_the_order_of_recording_and_changes_with_any_decision():
    key = keys.DeidKey.generate()
    first = _list((SERIES_DESCRIPTION, "A", KEEP), (IMAGE_COMMENTS, "B", EMPTY))
    second = _list((IMAGE_COMMENTS, "B", EMPTY), (SERIES_DESCRIPTION, "A", KEEP))
    changed = [
        _list((SERIES_DESCRIPTION, "A", KEEP), (IMAGE_COMMENTS, "B", KEEP)),
        _list((SERIES_DESCRIPTION, "A", KEEP), (IMAGE_COMMENTS, "C", EMPTY)),
        _list((SERIES_DESCRIPTION, "A", KEEP), ("(0018,1030)", "B", EMPTY)),
        _list((SERIES_DESCRIPTION, "A", KEEP)),
    ]

    digest = first.keyed_digest(key)

    assert second.keyed_digest(key) == digest
    assert len({digest, *(listed.keyed_digest(key) for listed in changed)}) == 5
    assert first.keyed_digest(keys.DeidKey.generate()) != digest
    assert digest != hashlib.sha256(first.canonical_bytes()).hexdigest()
    assert digest != hmac.new(b"", first.canonical_bytes(), "sha256").hexdigest()


@pytest.mark.parametrize("key", [None, b"0" * 32, "0" * 64])
def test_the_keyed_digest_needs_a_deidentification_key(key):
    with pytest.raises(TypeError):
        _list().keyed_digest(key)


def _clean(tag, values, listed, identifiers=(), **options):
    return reviewed.clean_descriptor_values(
        tag, values, listed, identifiers=identifiers, **options
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_reviewers_decision_to_keep_map_or_empty_a_value_is_applied():
    listed = _list(
        (SERIES_DESCRIPTION, "AX T1 POST", KEEP),
        (SERIES_DESCRIPTION, "Dr Ng protocol", _map("Protocol A")),
        (SERIES_DESCRIPTION, "for Mrs Ng", EMPTY),
    )

    results = _clean(
        SERIES_DESCRIPTION, ["AX T1 POST ", "Dr Ng protocol", "for Mrs Ng\x00"], listed
    )

    assert [(r.outcome, r.held_because, r.value) for r in results] == [
        (Outcome.KEPT, None, "AX T1 POST"),
        (Outcome.MAPPED, None, "Protocol A"),
        (Outcome.EMPTIED, None, ""),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_value_the_list_does_not_cover_is_held_and_emptied_only_when_chosen():
    listed = _list((SERIES_DESCRIPTION, "AX T1", KEEP))

    held = _clean(SERIES_DESCRIPTION, ["ax t1", "Mr Ng's scan"], listed)
    emptied = _clean(SERIES_DESCRIPTION, ["Mr Ng's scan"], listed, empty_held=True)

    assert [(r.outcome, r.held_because, r.value) for r in held] == [
        (Outcome.HELD, Held.UNREVIEWED, None),
        (Outcome.HELD, Held.UNREVIEWED, None),
    ]
    assert [(r.outcome, r.held_because, r.value) for r in emptied] == [
        (Outcome.EMPTIED_UNREVIEWED, Held.UNREVIEWED, "")
    ]


def test_an_empty_value_stays_empty_without_review():
    results = _clean(SERIES_DESCRIPTION, ["", "  ", "\x00"], _list())

    assert {(r.outcome, r.value) for r in results} == {(Outcome.EMPTY, "")}


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "value, decision",
    [
        ("Ng Jane chest", KEEP),
        ("Protocol 7", _map("Jane protocol")),
        ("Scan MRN 99-1234", KEEP),
    ],
)
def test_a_reviewed_value_that_echoes_an_identifier_is_held(value, decision):
    listed = _list((SERIES_DESCRIPTION, value, decision))

    (result,) = _clean(
        SERIES_DESCRIPTION, [value], listed, identifiers=["NG^JANE", "991234"]
    )
    (emptied,) = _clean(
        SERIES_DESCRIPTION,
        [value],
        listed,
        identifiers=["NG^JANE", "991234"],
        empty_held=True,
    )

    assert (result.outcome, result.held_because, result.value) == (
        Outcome.HELD,
        Held.ECHOES_IDENTIFIER,
        None,
    )
    assert (emptied.outcome, emptied.value) == (Outcome.EMPTIED_UNREVIEWED, "")


def test_an_emptying_decision_is_never_held_for_an_echo():
    listed = _list((SERIES_DESCRIPTION, "Ng Jane chest", EMPTY))

    (result,) = _clean(
        SERIES_DESCRIPTION, ["Ng Jane chest"], listed, identifiers=["NG^JANE"]
    )

    assert (result.outcome, result.value) == (Outcome.EMPTIED, "")


def test_each_value_of_a_multi_valued_attribute_is_decided_alone():
    listed = _list(
        (ADMITTING_DIAGNOSES, "Fracture", KEEP),
        (ADMITTING_DIAGNOSES, "Fall at Ng home", EMPTY),
    )

    results = _clean(
        ADMITTING_DIAGNOSES, ["Fracture", "Fall at Ng home", "Other"], listed
    )

    assert [r.outcome for r in results] == [
        Outcome.KEPT,
        Outcome.EMPTIED,
        Outcome.HELD,
    ]


@pytest.mark.parametrize(
    "values, identifiers", [("AX T1", []), (["AX T1"], "NG"), ([3], []), ([], [3])]
)
def test_values_and_identifiers_must_be_sequences_of_strings(values, identifiers):
    with pytest.raises(TypeError) as error:
        _clean(SERIES_DESCRIPTION, values, _list(), identifiers=identifiers)

    assert "AX" not in str(error.value) and "NG" not in str(error.value)


def test_cleaning_needs_a_descriptor_attribute():
    with pytest.raises(ValueError, match="not a descriptor"):
        _clean("(0010,0010)", ["NG^JANE"], _list())


def test_results_never_show_a_value():
    listed = _list((SERIES_DESCRIPTION, "AX T1 POST", KEEP))

    shown = repr(_clean(SERIES_DESCRIPTION, ["AX T1 POST", "Ng scan"], listed))

    assert "AX" not in shown and "Ng" not in shown


def test_the_review_queue_lists_each_distinct_held_value_once():
    queue = reviewed.DescriptorReviewQueue()
    listed = _list((SERIES_DESCRIPTION, "Ng Jane chest", KEEP))
    for values in (["Ng Jane chest", "Other "], ["Other"]):
        results = _clean(SERIES_DESCRIPTION, values, listed, identifiers=["NG^JANE"])
        queue.add(SERIES_DESCRIPTION, values, results)
    queue.add(IMAGE_COMMENTS, ["Other"], _clean(IMAGE_COMMENTS, ["Other"], listed))

    entries = queue.entries()

    assert [(e.tag, e.value, e.reasons, e.elements) for e in entries] == [
        (SERIES_DESCRIPTION, "Ng Jane chest", {Held.ECHOES_IDENTIFIER}, 1),
        (SERIES_DESCRIPTION, "Other", {Held.UNREVIEWED}, 2),
        (IMAGE_COMMENTS, "Other", {Held.UNREVIEWED}, 1),
    ]
    assert "Other" not in repr(entries) + repr(queue)


def test_the_review_queue_needs_one_result_per_value():
    with pytest.raises(ValueError, match="one result for each value"):
        reviewed.DescriptorReviewQueue().add(SERIES_DESCRIPTION, ["a", "b"], ())


def test_the_report_counts_give_held_values_by_reason_and_values_by_outcome():
    queue = reviewed.DescriptorReviewQueue()
    listed = _list((SERIES_DESCRIPTION, "AX T1", KEEP))
    values = ["AX T1", "AX T1", "Ng", "Ng", ""]
    queue.add(
        SERIES_DESCRIPTION,
        values,
        _clean(SERIES_DESCRIPTION, values, listed, identifiers=["NG"], empty_held=True),
    )

    counts = queue.report_counts()

    assert dict(counts.held) == {Held.UNREVIEWED: 1}
    assert dict(counts.outcomes) == {
        Outcome.KEPT: 2,
        Outcome.EMPTIED_UNREVIEWED: 2,
        Outcome.EMPTY: 1,
    }
    with pytest.raises(TypeError):
        counts.held[Held.UNREVIEWED] = 2


@pytest.mark.parametrize(
    "value, echoes",
    [
        ("Jane Ng chest", True),  # a reordered name, word by word
        ("Scan MRN 99-1234", True),  # a reformatted identifier among words
        ("ref991234x", True),
        ("Lung window", False),  # NG only as a word, not inside one
        ("Scan MRN 99-123", False),
        ("JANENG", True),  # the given name run into the family name
        ("Ng-Jane", True),
        ("PROTOCOLJANE", True),
    ],
)
def test_an_identifier_is_found_by_word_or_within_the_values_letters_and_digits(
    value, echoes
):
    assert reviewed.echoes_identifier(value, ["NG^JANE", "991234"]) is echoes
