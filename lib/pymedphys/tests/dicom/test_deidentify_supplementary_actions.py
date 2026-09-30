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

"""Reviewed supplementary (L2) actions for attributes that Table E.1-1 omits."""

import re

from pymedphys._imports import pytest, tomlkit

from pymedphys._dicom.deidentify import standard, supplementary_actions

# The actions of Table E.1-1a that never keep the value as received.
REMOVING_ACTIONS = {"X", "Z", "D", "X/Z", "Z/D", "X/D", "X/Z/D"}


def _dictionary():
    return {
        attribute.tag: attribute
        for attribute in standard.load_data_dictionary().attributes
    }


def _table_e1_1():
    return {row.tag: row for row in standard.load_table_e1_1().attributes}


def test_every_person_name_that_table_e1_1_omits_has_an_action():
    listed = _table_e1_1()
    omitted = {
        tag
        for tag, attribute in _dictionary().items()
        if attribute.vr == "PN" and tag not in listed
    }

    # Checked by hand against the 2026d PS3.6 and PS3.15.
    assert omitted == {"(0014,0104)", "(0014,2006)", "(0040,A067)"}
    assert omitted <= set(supplementary_actions.load_supplementary_actions().rules)


def test_the_basic_profile_keeps_no_person_name():
    # Table E.1-1 and the supplementary actions together give every person
    # name in the dictionary an action that removes or replaces it.
    listed = _table_e1_1()
    rules = supplementary_actions.load_supplementary_actions().rules
    actions = {
        tag: listed[tag].basic_profile if tag in listed else rules[tag].action
        for tag, attribute in _dictionary().items()
        if attribute.vr == "PN"
    }

    assert len(actions) == 32
    assert set(actions.values()) <= REMOVING_ACTIONS


@pytest.mark.parametrize(
    "tag, keyword, action",
    [
        # Marked DICONDE in PS3.6 and used by none of the generated IODs, so
        # the action suits any Type an IOD gives them.
        ("(0014,0104)", "SecondaryReviewerName", "X/Z/D"),
        ("(0014,2006)", "EvaluatorName", "X/Z/D"),
        # Retired, like the other (Trial) person names, which Table E.1-1
        # removes.
        ("(0040,A067)", "DocumentAuthorTrial", "X"),
        # Kept as received and never set to NO, since the pixel data are
        # unchanged.
        ("(0028,0301)", "BurnedInAnnotation", "K"),
        ("(0028,0302)", "RecognizableVisualFeatures", "K"),
    ],
)
def test_actions(tag, keyword, action):
    rule = supplementary_actions.load_supplementary_actions().rules[tag]

    assert (rule.tag, rule.keyword, rule.action) == (tag, keyword, action)
    assert rule.note


def test_notes_describe_decisions_rather_than_cite_their_numbers():
    # Decision numbers belong to the design document and its register.
    for rule in supplementary_actions.load_supplementary_actions().rules.values():
        assert not re.search(r"\bD-[0-9]{3}\b", rule.note), rule.tag


def test_the_actions_follow_the_editions_of_the_tables():
    actions = supplementary_actions.load_supplementary_actions()

    assert actions.edition == standard.load_data_dictionary().edition
    assert actions.edition == standard.load_table_e1_1().edition
    assert actions.acknowledgement == f"DICOM PS3.6 {actions.edition}, © NEMA"


def test_the_rules_are_read_only():
    rules = supplementary_actions.load_supplementary_actions().rules

    with pytest.raises(TypeError):
        rules["(0010,0010)"] = rules["(0028,0301)"]  # type: ignore[index]


def _document():
    return tomlkit.parse(
        supplementary_actions.SUPPLEMENTARY_ACTIONS_PATH.read_text(encoding="utf-8")
    ).unwrap()


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _drop(document, tag):
    document["attribute"] = [
        rule for rule in document["attribute"] if rule["tag"] != tag
    ]


def _first(**fields):
    return lambda document: document["attribute"][0].update(fields)


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda d: d.update(schema="pymedphys-deid-supplementary-actions/0"),
            "schema",
        ),
        (lambda d: d.update(edition="2099a"), "edition"),
        (lambda d: d.update(acknowledgement="NEMA"), "acknowledgement"),
        (lambda d: d.update(attribute=1), "rules are not an array of tables"),
        (lambda d: d.update(attribute={}), "rules are not an array of tables"),
        (_first(extra=1), "rule 1 does not have"),
        (lambda d: d["attribute"][0].pop("keyword"), "rule 1 does not have"),
        (lambda d: d["attribute"][0].pop("note"), "rule 1 does not have"),
        (_first(tag="(7777,7777)"), "rule 1 is not an attribute of the data"),
        (_first(tag=[]), "rule 1 is not an attribute of the data"),
        (_first(keyword="EvaluatorName"), "rule 1 names"),
        (
            _first(tag="(0010,0010)", keyword="PatientName"),
            "rule 1 is listed in Table E.1-1",
        ),
        (
            _first(tag="(0008,0016)", keyword="SOPClassUID"),
            "rule 1 is of a VR that a roles file covers",
        ),
        (_first(action="retain"), "rule 1 has an action not defined in Table"),
        (_first(action="U*"), "rule 1 has an action not defined in Table"),
        (_first(action=[]), "rule 1 has an action not defined in Table"),
        (_first(note=""), "rule 1 has a note that is not non-empty text"),
        (_first(note=" "), "rule 1 has a note that is not non-empty text"),
        (lambda d: d["attribute"].append(dict(d["attribute"][0])), "repeats"),
        (lambda d: _drop(d, "(0014,2006)"), "has no action for (0014,2006)"),
    ],
)
def test_a_malformed_file_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(
        supplementary_actions.SupplementaryActionError, match=re.escape(message)
    ):
        supplementary_actions.load_supplementary_actions(
            _write(tmp_path / "supplementary_actions.toml", document)
        )


def test_a_file_that_cannot_be_read_is_rejected(tmp_path):
    with pytest.raises(
        supplementary_actions.SupplementaryActionError, match="could not be read"
    ):
        supplementary_actions.load_supplementary_actions(tmp_path / "missing.toml")
