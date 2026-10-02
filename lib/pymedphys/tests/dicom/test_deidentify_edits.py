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

"""What each planned element of a data set becomes, and the values collected.

Every file is synthetic and encoded by hand. Values that must never appear in
a result's ``repr`` carry the text ``SENTINEL``.
"""

import pickle

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import edits, elements, source, walker
from pymedphys._dicom.deidentify.edits import EditKind
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.uids import UIDOutcome, replacement_uid

from .test_deidentify_file_layout import EXPLICIT, _explicit, _file
from .test_deidentify_walker import (
    BEAM_SEQUENCE,
    OTHER_IDS,
    _by_path,
    _path,
    _rt_plan,
    _rt_plan_data_set,
    _rules,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
INSTANCE_UID = "2.25.7700192"
RT_PLAN_CLASS = "1.2.840.10008.5.1.4.1.1.481.5"


def _edits(data_set=None, rules=None):
    data_set = _rt_plan_data_set() if data_set is None else data_set
    evidence = source.read_source(_file(EXPLICIT, data_set))
    plan = walker.plan_instance(evidence, rules or _rules(), _rt_plan())
    return plan, edits.edit_instance(evidence, plan, KEY)


def _collected(result):
    return {value.source: (value.vr, value.value) for value in result.source_values}


def test_each_element_has_one_edit_in_file_order():
    plan, result = _edits()

    assert [edit.path for edit in result.edits] == [e.path for e in plan.elements]
    assert [edit.action for edit in result.edits] == [e.action for e in plan.elements]
    assert not result.sequestrations
    assert not result.not_collected

    found = {edit.path: edit for edit in result.edits}
    assert found[_path("(0008,0005)")].kind is EditKind.KEEP
    assert found[_path("(0028,0010)")].kind is EditKind.KEEP
    assert found[BEAM_SEQUENCE].kind is EditKind.KEEP
    assert found[_path("(0009,1001)")].kind is EditKind.REMOVE
    assert found[OTHER_IDS].kind is EditKind.REMOVE
    assert found[_path(("(0010,1002)", 0), "(0010,0020)")].kind is EditKind.REMOVE
    assert found[_path(("(300A,00B0)", 0), "(300A,00C2)")].kind is EditKind.REMOVE


def test_uids_are_replaced_by_their_keyed_replacement_unless_registered():
    _, result = _edits()
    found = {edit.path: edit for edit in result.edits}

    instance = found[_path("(0008,0018)")]
    assert instance.kind is EditKind.REPLACE
    assert instance.values == (replacement_uid(KEY, INSTANCE_UID),)
    assert instance.uid_outcomes == (UIDOutcome.REPLACED,)

    sop_class = found[_path("(0008,0016)")]
    assert sop_class.kind is EditKind.REPLACE
    assert sop_class.values == (RT_PLAN_CLASS,)
    assert sop_class.uid_outcomes == (UIDOutcome.RETAINED,)


def test_d_writes_the_dummy_value_and_the_second_where_the_source_equals_it():
    _, result = _edits()
    label = {edit.path: edit for edit in result.edits}[_path("(300A,0002)")]
    assert (label.kind, label.values) == (EditKind.REPLACE, ("DEIDENTIFIED",))

    _, result = _edits(_explicit(0x300A0002, "SH", b"deidentified"))
    (label,) = result.edits
    assert label.values == ("DE-IDENTIFIED",)


def test_patients_name_and_id_wait_for_their_pseudonyms():
    # D-005: Patient's Name and Patient ID take the subject's keyed
    # pseudonyms under Z and D, which a later step gives.
    _, result = _edits(
        _explicit(0x00100010, "PN", b"SENTINEL^NAME ")
        + _explicit(0x00100020, "LO", b"SENTINEL ID ")
    )

    assert [edit.kind for edit in result.edits] == [EditKind.PENDING] * 2
    assert [edit.values for edit in result.edits] == [(), ()]


def test_z_empties_and_c_waits_for_cleaning():
    _, result = _edits(
        _explicit(0x00080020, "DA", b"20240229")
        + _explicit(0x300A0003, "LO", b"SENTINEL DESC "),
        _rules("basic-clean-descriptors"),
    )
    study_date, description = result.edits

    assert (study_date.action, study_date.kind) == ("Z", EditKind.EMPTY)
    assert (description.action, description.kind) == ("C", EditKind.PENDING)


def test_every_removed_or_replaced_value_is_collected_with_its_vr():
    _, result = _edits()
    collected = _collected(result)

    assert collected[_path("(0010,0010)")] == ("PN", "SENTINEL^NAME")
    assert collected[_path("(0009,1001)")] == ("LO", "SENTINEL PRIV")
    assert collected[_path("(0008,9999)")] == ("LO", "SENTINEL UNKN")
    assert collected[_path("(0008,0018)")] == ("UI", INSTANCE_UID)
    assert collected[_path(("(300A,00B0)", 0), "(300A,00C2)")] == (
        "LO",
        "SENTINEL BEAM",
    )
    # The descendants of a removed sequence, nested ones included.
    nested = _path(("(0010,1002)", 0), ("(0010,1002)", 0), "(0010,0020)")
    assert collected[nested] == ("LO", "SENTINEL ID")
    encrypted = collected[_path(("(0400,0500)", 0), "(0400,0520)")]
    assert encrypted == ("OB", b"SENTINEL ENCR\x00")
    # Kept values and sequences are not.
    assert _path("(0028,0010)") not in collected
    assert BEAM_SEQUENCE not in collected
    assert all(value.codecs == ("latin_1",) for value in result.source_values)


def test_only_the_planned_values_and_the_sequences_that_hold_them_are_read(
    monkeypatch,
):
    read = []
    original = elements.read_element

    def recording(dataset, path, *args, **kwargs):
        read.append(path)
        return original(dataset, path, *args, **kwargs)

    monkeypatch.setattr(elements, "read_element", recording)
    plan, _ = _edits()
    elements_by_path = _by_path(plan)

    containers = {
        walker.ElementPath(path.items[:depth], tag)
        for path in plan.to_decode()
        for depth, (tag, _) in enumerate(path.items)
    }
    character_set = _path("(0008,0005)")
    assert set(read) <= set(plan.to_decode()) | containers | {character_set}
    assert set(plan.to_decode()) <= set(read)
    assert _path("(0028,0010)") not in read
    assert not elements_by_path[_path("(0028,0010)")].consumers


def test_a_value_that_is_only_collected_and_cannot_be_decoded_is_listed():
    # Study Description (0008,1030), removed, with a byte outside the
    # Default Character Repertoire.
    _, result = _edits(_explicit(0x00081030, "LO", b"SENTINEL \xe9"))

    (description,) = result.edits
    assert description.kind is EditKind.REMOVE
    assert not result.sequestrations
    assert not result.source_values
    (missing,) = result.not_collected
    assert missing.path == _path("(0008,1030)")
    assert "SENTINEL" not in missing.reason


def test_a_value_that_its_action_needs_and_cannot_be_decoded_sequesters():
    _, result = _edits(_explicit(0x300A0002, "SH", b"SENTINEL \xe9"))

    (sequestration,) = result.sequestrations
    assert sequestration == walker.Sequestration(
        _path("(300A,0002)"), "D", "SH", walker.SequesterReason.UNDECODABLE
    )
    assert str(sequestration) == (
        "D on (300A,0002) needs its value, which cannot be decoded, so the "
        "instance must be sequestered"
    )
    assert not result.edits


def test_an_unsupported_character_set_sequesters_the_instance():
    _, result = _edits(
        _explicit(0x00080005, "CS", b"ISO_IR 999")
        + _explicit(0x00100010, "PN", b"SENTINEL^NAME ")
    )

    (sequestration,) = result.sequestrations
    assert sequestration.path == _path("(0008,0005)")
    assert sequestration.reason is walker.SequesterReason.UNSUPPORTED_CHARACTER_SET
    assert not result.edits


def test_a_sequestered_plan_is_not_edited():
    plan, result = _edits(_explicit(0x300A00B0, "OB", b"SENTINEL"))

    assert plan.sequestrations
    assert result.sequestrations == plan.sequestrations
    assert not result.edits
    assert not result.source_values


def test_results_hold_no_value_in_their_reprs():
    _, result = _edits()
    _, failed = _edits(_explicit(0x00081030, "LO", b"SENTINEL \xe9"))
    shown = (
        repr(result)
        + repr(failed)
        + "".join(repr(edit) for edit in result.edits)
        + "".join(repr(missing) for missing in failed.not_collected)
        + repr(pickle.loads(pickle.dumps(result.edits)))
    )

    assert "SENTINEL" not in shown
    assert "DEIDENTIFIED" not in shown
    assert INSTANCE_UID not in shown
