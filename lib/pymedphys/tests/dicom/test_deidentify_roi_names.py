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

"""Automatic cleaning of ROI Names against a TG-263 vocabulary.

Every vocabulary here is invented, in the shape of the TG-263 spreadsheet's
entries, and every identifier is synthetic. An invented vocabulary is
accepted only while its digest is added to the published editions.
"""

import dataclasses
from unittest import mock

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import roi_names
from pymedphys._dicom.deidentify.roi_names import Reason
from pymedphys._nomenclature import tg263, tg263_published


def _structure(primary, reverse):
    return tg263.Structure(
        target_type="Anatomic",
        major_category="Invented",
        minor_category="",
        anatomic_group="",
        primary_name=primary,
        reverse_order_name=reverse,
        description="",
        fma_id=None,
    )


def _nomenclature(*names):
    return tg263.Nomenclature(
        source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
        attribution=tg263.ATTRIBUTION,
        structures=tuple(_structure(primary, reverse) for primary, reverse in names),
    )


def _digest(nomenclature):
    return tg263.content_sha256(
        [dataclasses.asdict(s) for s in nomenclature.structures]
    )


def _published(nomenclature):
    """Return the vocabulary of an invented nomenclature taken as published."""
    published = {"TG263 vInvented": _digest(nomenclature)}
    with mock.patch.dict(roi_names.PUBLISHED_TG263, published):
        return roi_names.RoiNameVocabulary(nomenclature)


VOCABULARY = _published(
    _nomenclature(
        ("Lung_L", "L_Lung"),
        ("Lung_R", "R_Lung"),
        ("Heart", "Heart"),
        ("SpinalCord", "SpinalCord"),
        ("Hand_L", "L_Hand"),
        ("Bowel_Small", "Small_Bowel"),
        ("VB_S", "S_VB"),
        ("VBs", "VBs"),
        ("Lungs-PTV", "Lungs-PTV"),
        ("Kidney_R-GTV", "R_Kidney-GTV"),
    )
)


def _clean(names, identifiers=()):
    return roi_names.clean_roi_names(names, VOCABULARY, identifiers=identifiers)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "name",
    [
        "Lung_L",
        "lung l",
        "LUNG-L",
        "Lung L",
        " lung_l ",
        "lung__l",
        "lungl",
        "L u-n_g L",
    ],
)
def test_a_name_that_matches_once_case_whitespace_and_separators_are_disregarded_is_written_in_the_vocabularys_spelling(
    name,
):
    (decision,) = _clean([name])
    assert decision == roi_names.RoiNameDecision(Reason.MATCHED, "Lung_L")
    assert decision.renamed


def test_a_reverse_order_name_is_written_in_its_own_spelling():
    assert _clean(["l lung"]) == (roi_names.RoiNameDecision(Reason.MATCHED, "L_Lung"),)


def test_a_name_with_one_spelling_in_both_columns_matches():
    assert _clean(["HEART"]) == (roi_names.RoiNameDecision(Reason.MATCHED, "Heart"),)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "name",
    [
        "Lung_L1",
        "Lung.L",
        "Lung_Lt",
        "Lung/L",
        "Heart~",
        "Heart Dr Smith",
        "lung l 2026-10-01",
        "Hand",
    ],
)
def test_a_near_match_goes_to_review(name):
    # Each differs by a character that is not a disregarded separator.
    (decision,) = _clean([name])
    assert decision == roi_names.RoiNameDecision(Reason.UNMATCHED, None)
    assert not decision.renamed


@pytest.mark.parametrize(
    "name",
    [
        "Lung L",  # no-break space
        "Ｌｕｎｇ_Ｌ",  # full-width letters
        "Lung_K",  # Kelvin sign, which casefolds to k
        "Lung\tL",
        "Lung_L\x00x",
        "Lungé_L",
        "肺_L",
    ],
)
def test_a_name_with_a_character_outside_printable_ascii_goes_to_review(name):
    assert _clean([name]) == (roi_names.RoiNameDecision(Reason.UNMATCHED, None),)


@pytest.mark.parametrize("name", ["", " ", "\x00", "  \x00 "])
def test_an_empty_name_stays_empty(name):
    assert _clean([name]) == (roi_names.RoiNameDecision(Reason.EMPTY, ""),)


@pytest.mark.parametrize("name", ["-", "_ _", "---"])
def test_a_name_of_separators_alone_goes_to_review(name):
    assert _clean([name]) == (roi_names.RoiNameDecision(Reason.UNMATCHED, None),)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "name",
    ["_Heart", "_Lung_L", "  _Heart", "_Heart\x00", "__heart", "-Heart", " - Lung L"],
)
def test_a_name_with_a_leading_underscore_or_hyphen_goes_to_review(name):
    # TG-263 marks a structure not used for dose evaluation, such as an
    # optimisation contour, with a leading "_", so "_Heart" is not "Heart".
    assert _clean([name]) == (roi_names.RoiNameDecision(Reason.UNMATCHED, None),)


def test_a_prefixed_name_does_not_stop_the_plain_name_being_renamed():
    assert _clean(["_Heart", "Heart"]) == (
        roi_names.RoiNameDecision(Reason.UNMATCHED, None),
        roi_names.RoiNameDecision(Reason.MATCHED, "Heart"),
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_name_that_matches_more_than_one_vocabulary_name_goes_to_review():
    # VB_S and VBs normalise alike, as in the 2017-08-15 edition.
    assert _clean(["vb s"]) == (roi_names.RoiNameDecision(Reason.AMBIGUOUS, None),)


def test_a_vocabulary_name_that_is_ambiguous_is_not_written_even_when_spelt_exactly():
    assert _clean(["VB_S"]) == (roi_names.RoiNameDecision(Reason.AMBIGUOUS, None),)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_different_names_that_would_be_written_as_one_vocabulary_name_go_to_review():
    decisions = _clean(["Lung_L", "LUNG-L", "Heart"])
    assert decisions == (
        roi_names.RoiNameDecision(Reason.WOULD_DUPLICATE, None),
        roi_names.RoiNameDecision(Reason.WOULD_DUPLICATE, None),
        roi_names.RoiNameDecision(Reason.MATCHED, "Heart"),
    )


def test_a_primary_and_a_reverse_order_name_of_one_structure_are_not_duplicates():
    # They are written as different names, so the import sees no duplicate.
    assert _clean(["lung l", "l lung"]) == (
        roi_names.RoiNameDecision(Reason.MATCHED, "Lung_L"),
        roi_names.RoiNameDecision(Reason.MATCHED, "L_Lung"),
    )


def test_names_that_differ_only_by_padding_are_one_name():
    assert _clean(["Lung_L", "Lung_L ", "Lung_L\x00"]) == (
        (roi_names.RoiNameDecision(Reason.MATCHED, "Lung_L"),) * 3
    )


def test_the_same_name_twice_is_renamed_twice():
    # The source already repeats it; cleaning adds no duplicate.
    assert _clean(["lung l", "lung l"]) == (
        (roi_names.RoiNameDecision(Reason.MATCHED, "Lung_L"),) * 2
    )


def test_a_name_whose_twin_echoes_an_identifier_is_still_a_duplicate():
    # Only "lungl" holds the identifier's word. A reviewer could map it to the
    # vocabulary name that its twin would take.
    decisions = _clean(["lung l", "lungl"], identifiers=["LungL^Alex"])
    assert [d.reason for d in decisions] == [
        Reason.WOULD_DUPLICATE,
        Reason.ECHOES_IDENTIFIER,
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-11")
@pytest.mark.parametrize(
    "identifier",
    [
        "Hand^Alex",  # family name
        "Alex^Hand",  # given name, so reordered names are caught
        "HAND^ALEX^^DR",
        "Hand-Smith^Alex",  # a hyphenated family name
        "Smith^Alex=Hand^Alex",  # another component group
        "Dr Alex Hand",
        "hand",
    ],
)
def test_a_name_that_echoes_a_known_identifier_goes_to_review(identifier):
    (decision,) = _clean(["Hand L"], identifiers=[identifier])
    assert decision == roi_names.RoiNameDecision(Reason.ECHOES_IDENTIFIER, None)


@pytest.mark.parametrize("identifier", ["HEART-1", "heart 1"])
def test_an_identifier_echoed_by_a_whole_name_once_separators_are_disregarded_goes_to_review(
    identifier,
):
    vocabulary = _published(_nomenclature(("Heart1", "Heart1")))
    decisions = roi_names.clean_roi_names(
        ["heart1"], vocabulary, identifiers=[identifier]
    )
    assert decisions == (roi_names.RoiNameDecision(Reason.ECHOES_IDENTIFIER, None),)


@pytest.mark.parametrize(
    "identifier",
    [
        "Handley^Alex",  # a longer word containing the token
        "L^Alex",  # single characters, such as initials, are not compared
        "",
        "Alex^Smith",
        "12345678",
    ],
)
def test_a_name_that_does_not_echo_an_identifier_is_renamed(identifier):
    assert _clean(["Hand L"], identifiers=[identifier]) == (
        roi_names.RoiNameDecision(Reason.MATCHED, "Hand_L"),
    )


def test_a_name_echoes_an_identifier_through_the_spelling_it_would_take():
    # "lungl" has no word "lung", but its vocabulary spelling Lung_L has.
    assert _clean(["lungl"], identifiers=["Lung^Alex"]) == (
        roi_names.RoiNameDecision(Reason.ECHOES_IDENTIFIER, None),
    )


def test_an_identifier_echoes_only_through_the_names_it_shares_a_word_with():
    decisions = _clean(["Hand L", "Heart"], identifiers=["Hand^Alex"])
    assert [d.reason for d in decisions] == [
        Reason.ECHOES_IDENTIFIER,
        Reason.MATCHED,
    ]


def test_identifiers_with_characters_outside_ascii_are_compared_by_their_words():
    assert _clean(["Hand L"], identifiers=["HAND^Zoë"])[0].reason is (
        Reason.ECHOES_IDENTIFIER
    )


def test_identifiers_can_be_any_iterable_and_are_read_once():
    decisions = _clean(["Hand L", "Heart"], identifiers=iter(["Hand^Alex"]))
    assert [d.reason for d in decisions] == [
        Reason.ECHOES_IDENTIFIER,
        Reason.MATCHED,
    ]


def test_without_names_there_are_no_decisions():
    assert _clean([]) == tuple()


def test_decisions_follow_the_order_of_the_names():
    decisions = _clean(["Heart", "liver", "Lung R", ""])
    assert [d.reason for d in decisions] == [
        Reason.MATCHED,
        Reason.UNMATCHED,
        Reason.MATCHED,
        Reason.EMPTY,
    ]
    assert [d.value for d in decisions] == ["Heart", None, "Lung_R", ""]


def test_a_decision_holds_no_source_value():
    # The vocabulary's spelling is all a decision carries, so neither its
    # fields nor its repr can show a source name.
    decisions = _clean(["Dr Hand's lung", "lung l"])
    assert [dataclasses.astuple(d) for d in decisions] == [
        (Reason.UNMATCHED, None),
        (Reason.MATCHED, "Lung_L"),
    ]
    assert "Dr Hand" not in repr(decisions)


@pytest.mark.parametrize(
    "names, identifiers",
    [
        ([b"Lung_L"], ()),
        ([None], ()),
        ("Lung_L", ()),
        (["Lung_L"], "Hand^Alex"),
        (["Lung_L"], [b"Hand^Alex"]),
    ],
)
def test_names_and_identifiers_must_be_sequences_of_text(names, identifiers):
    with pytest.raises(TypeError) as error:
        roi_names.clean_roi_names(names, VOCABULARY, identifiers=identifiers)
    assert "Lung" not in str(error.value)
    assert "Hand" not in str(error.value)


def test_the_vocabulary_is_taken_from_a_tg263_nomenclature_only():
    with pytest.raises(TypeError):
        roi_names.RoiNameVocabulary(["Lung_L"])


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_nomenclature_without_the_tg263_attribution_is_rejected():
    nomenclature = dataclasses.replace(
        _nomenclature(("Lung_L", "L_Lung")), attribution="An institutional list"
    )
    with pytest.raises(ValueError, match="TG-263"):
        roi_names.RoiNameVocabulary(nomenclature)


def test_the_vocabulary_lists_the_names_it_can_write():
    assert VOCABULARY.names == frozenset(
        {
            "Lung_L",
            "L_Lung",
            "Lung_R",
            "R_Lung",
            "Heart",
            "SpinalCord",
            "Hand_L",
            "L_Hand",
            "Bowel_Small",
            "Small_Bowel",
            "VB_S",
            "S_VB",
            "VBs",
            "Lungs-PTV",
            "Kidney_R-GTV",
            "R_Kidney-GTV",
        }
    )


def test_a_vocabulary_entry_outside_printable_ascii_is_never_written():
    vocabulary = _published(_nomenclature(("Lungé_L", "L_Lungé"), ("Heart", "Heart")))
    assert vocabulary.names == frozenset({"Heart"})
    decisions = roi_names.clean_roi_names(
        ["Lungé_L", "lunge l"], vocabulary, identifiers=()
    )
    assert [d.reason for d in decisions] == [Reason.UNMATCHED, Reason.UNMATCHED]


def test_the_vocabulary_repr_is_short():
    assert repr(VOCABULARY) == "RoiNameVocabulary(names=16)"


def test_a_loaded_vocabulary_file_cleans_names(tmp_path):
    path = tmp_path / "tg263.json"
    path.write_text(tg263.to_json(_nomenclature(("Lung_L", "L_Lung"))), "utf-8")
    vocabulary = _published(tg263.load_json(path))
    assert roi_names.clean_roi_names(["LUNG L"], vocabulary, identifiers=()) == (
        roi_names.RoiNameDecision(Reason.MATCHED, "Lung_L"),
    )


@pytest.mark.parametrize(
    "name, spelling",
    [
        ("Lungs-PTV", "Lungs-PTV"),
        ("lungs - ptv", "Lungs-PTV"),
        ("LUNGS-PTV", "Lungs-PTV"),
        ("kidney r-gtv", "Kidney_R-GTV"),
        ("Kidney_R - GTV", "Kidney_R-GTV"),
        ("r kidney-gtv", "R_Kidney-GTV"),
    ],
)
def test_a_vocabulary_name_with_a_hyphen_matches_a_hyphen_in_the_same_place(
    name, spelling
):
    assert _clean([name]) == (roi_names.RoiNameDecision(Reason.MATCHED, spelling),)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "name", ["Lungs PTV", "Lungs_PTV", "LungsPTV", "Lung-s PTV", "Kidney-R GTV"]
)
def test_a_vocabulary_name_with_a_hyphen_is_not_matched_without_it(name):
    # TG-263 writes "-" for a subtraction: Lungs-PTV is the lungs minus the
    # PTV, so "Lungs PTV" could be another structure.
    assert _clean([name]) == (roi_names.RoiNameDecision(Reason.UNMATCHED, None),)


def test_a_hyphen_still_separates_where_the_vocabulary_name_has_none():
    assert _clean(["LUNG-L", "Bowel-Small"]) == (
        roi_names.RoiNameDecision(Reason.MATCHED, "Lung_L"),
        roi_names.RoiNameDecision(Reason.MATCHED, "Bowel_Small"),
    )


def test_a_name_matching_with_and_without_its_hyphen_is_ambiguous():
    vocabulary = _published(
        _nomenclature(("Lungs-PTV", "Lungs-PTV"), ("LungsPTV", "LungsPTV"))
    )
    decisions = roi_names.clean_roi_names(["lungs-ptv"], vocabulary, identifiers=())
    assert decisions == (roi_names.RoiNameDecision(Reason.AMBIGUOUS, None),)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_an_unpublished_vocabulary_is_refused():
    # A converted workbook extended with a local name carries AAPM's
    # attribution, as the converter writes it for every TG-263 workbook.
    extended = _nomenclature(("Lung_L", "L_Lung"), ("ClinicX_Lung", "Lung_ClinicX"))
    assert extended.attribution == tg263.ATTRIBUTION
    with pytest.raises(ValueError, match="published edition"):
        roi_names.RoiNameVocabulary(extended)


def test_the_published_edition_is_the_one_pymedphys_downloads():
    pinned = tg263_published.PUBLISHED

    assert roi_names.PUBLISHED_TG263 == {pinned.sheet: pinned.content_sha256}
