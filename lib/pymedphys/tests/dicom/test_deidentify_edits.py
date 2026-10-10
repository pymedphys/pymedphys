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

from pymedphys._dicom.deidentify import edits, elements, residuals, source, walker
from pymedphys._dicom.deidentify.dummy_values import DummyElement
from pymedphys._dicom.deidentify.edits import EditKind
from pymedphys._dicom.deidentify.element_rules import RuleSource
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity, patient_pseudonym
from pymedphys._dicom.deidentify.uids import UIDOutcome, replacement_uid

from .test_deidentify_file_layout import EXPLICIT, _explicit, _file, _item
from .test_deidentify_walker import (
    BEAM_SEQUENCE,
    OTHER_IDS,
    PHOTO_ITEM,
    PHOTOS,
    _by_path,
    _Overridden,
    _path,
    _patient_setup_photo,
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


def _refusing(monkeypatch, *paths):
    """Make each of ``paths`` a value that cannot be decoded."""
    original = elements.read_element

    def refusing(dataset, path, *args, **kwargs):
        if path in paths:
            raise elements.UndecodableElement(path, "could not be decoded")
        return original(dataset, path, *args, **kwargs)

    monkeypatch.setattr(elements, "read_element", refusing)


def _collected(result):
    return {value.source: (value.vr, value.value) for value in result.source_values}


def test_each_element_has_one_edit_in_file_order():
    plan, result = _edits()

    assert [edit.path for edit in result.edits] == [e.path for e in plan.elements]
    assert [edit.action for edit in result.edits] == [e.action for e in plan.elements]
    assert not result.sequestrations
    assert not result.not_collected
    # Every value is in the Default Character Repertoire, or read in a
    # Specific Character Set.
    assert not result.read_as_latin_1

    found = {edit.path: edit for edit in result.edits}
    assert found[_path("(0008,0005)")].kind is EditKind.KEEP
    assert found[_path("(0028,0010)")].kind is EditKind.KEEP
    assert found[BEAM_SEQUENCE].kind is EditKind.KEEP
    assert found[_path("(0009,1001)")].kind is EditKind.REMOVE
    assert found[OTHER_IDS].kind is EditKind.REMOVE
    assert found[_path(("(0010,1002)", 0), "(0010,0020)")].kind is EditKind.REMOVE
    assert found[_path(("(0010,1002)", 0), "(0010,0020)")].removed_with == OTHER_IDS
    assert found[OTHER_IDS].removed_with is None
    assert found[_path(("(300A,00B0)", 0), "(300A,00C2)")].kind is EditKind.REMOVE


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
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


def test_registered_uids_are_left_out_of_the_residual_search():
    # A UID that the pinned tables register names no one, and stays in the
    # output wherever it is kept, so searching for it would find it in every
    # instance.
    _, result = _edits()
    collected = {value.source for value in result.source_values}

    assert _path("(0008,0018)") in collected
    assert _path("(0008,0016)") not in collected
    assert result.registered_uids == (_path("(0008,0016)"),)


@pytest.mark.parametrize(
    "encoded, collected",
    [
        # Each registered UID of a multi-valued UI is left out, and the rest
        # still searched for, whatever its padding.
        (b"1.2.840.10008.5.1.4.1.1.2\\1.2.3.4\x00", "1.2.3.4"),
        (b"1.2.840.10008.5.1.4.1.1.2\x00", None),
    ],
    ids=["mixed", "padded"],
)
def test_registered_uids_are_left_out_of_a_removed_value(encoded, collected):
    path = _path("(0008,001A)")
    _, result = _edits(_explicit(0x0008001A, "UI", encoded))
    found = {value.source: value.value for value in result.source_values}

    assert result.registered_uids == (path,)
    assert found.get(path) == collected


def test_an_empty_uid_value_is_not_registered():
    _, result = _edits(_explicit(0x0008001A, "UI", b""))

    assert not result.registered_uids


@pytest.mark.deid_requirement("PS3.15-E.1.1-01", "MIDI-BP-03")
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


def test_a_value_that_is_only_collected_and_cannot_be_decoded_is_listed(
    monkeypatch,
):
    # Study Description (0008,1030), removed.
    _refusing(monkeypatch, _path("(0008,1030)"))
    _, result = _edits(_explicit(0x00081030, "LO", b"SENTINEL DESC "))

    (description,) = result.edits
    assert description.kind is EditKind.REMOVE
    assert not result.sequestrations
    assert not result.source_values
    (missing,) = result.not_collected
    assert missing.path == _path("(0008,1030)")
    assert "SENTINEL" not in missing.reason


def test_a_value_that_its_action_needs_and_cannot_be_decoded_sequesters(
    monkeypatch,
):
    _refusing(monkeypatch, _path("(300A,0002)"))
    _, result = _edits(_explicit(0x300A0002, "SH", b"SENTINEL"))

    (sequestration,) = result.sequestrations
    assert sequestration == walker.Sequestration(
        _path("(300A,0002)"), "D", "SH", walker.SequesterReason.UNDECODABLE
    )
    assert str(sequestration) == (
        "D on (300A,0002) needs its value, which cannot be decoded, so the "
        "instance must be sequestered"
    )
    assert not result.edits


def test_removed_text_outside_iso_646_without_a_character_set_is_collected():
    # As decided on 1 October 2026, text with bytes outside the Default
    # Character Repertoire where no Specific Character Set applies is read
    # as ISO 8859-1 where it is removed, nested or not, so that every byte
    # can be searched for.
    _, result = _edits(
        _explicit(0x00081030, "LO", b"SENTINEL \xe9")
        + _explicit(
            0x00101002, "SQ", _item(_explicit(0x00100020, "LO", b"SENTINEL \xe9"))
        )
    )

    assert not result.sequestrations
    assert not result.not_collected
    assert _collected(result) == {
        _path("(0008,1030)"): ("LO", "SENTINEL \xe9"),
        _path(("(0010,1002)", 0), "(0010,0020)"): ("LO", "SENTINEL \xe9"),
    }
    assert result.read_as_latin_1 == (
        _path("(0008,1030)"),
        _path(("(0010,1002)", 0), "(0010,0020)"),
    )


def test_replaced_text_outside_iso_646_without_a_character_set_is_replaced():
    _, result = _edits(_explicit(0x300A0002, "SH", b"SENTINEL \xe9"))

    assert not result.sequestrations
    (label,) = result.edits
    assert (label.kind, label.values) == (EditKind.REPLACE, ("DEIDENTIFIED",))
    assert _collected(result) == {_path("(300A,0002)"): ("SH", "SENTINEL \xe9")}
    assert result.read_as_latin_1 == (_path("(300A,0002)"),)


@pytest.mark.parametrize(
    "tag, vr", [(0x00081030, "LO"), (0x300A0002, "SH")], ids=["removed", "replaced"]
)
def test_text_with_an_escape_and_no_character_set_is_collected_byte_for_byte(tag, vr):
    # pydicom would read ESC ( B as a switch to ISO 646 and drop it, so the
    # value is read from its bytes, before any escape sequence is
    # interpreted, and a copy of those bytes left in a file is still found.
    original = b"SENTINEL\x1b(B\xe9XYZ"
    _, result = _edits(_explicit(tag, vr, original + b" "))

    assert not result.sequestrations
    (collected,) = result.source_values
    assert collected.value == original.decode("latin-1")
    search = residuals.find_residuals(b"\x00" * 16 + original, [collected])
    assert search.findings

    (edit,) = result.edits
    assert edit.kind is (EditKind.REMOVE if vr == "LO" else EditKind.REPLACE)


def test_cleaned_text_outside_iso_646_without_a_character_set_sequesters():
    _, result = _edits(
        _explicit(0x300A0003, "LO", b"SENTINEL \xe9"),
        _rules("basic-clean-descriptors"),
    )

    (sequestration,) = result.sequestrations
    assert sequestration == walker.Sequestration(
        _path("(300A,0003)"), "C", "LO", walker.SequesterReason.UNDECODABLE
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
    # With no character set to read the data set's text in, nothing in it is
    # collected, and each value to collect is listed.
    assert not result.source_values
    assert [missing.path for missing in result.not_collected] == [_path("(0010,0010)")]
    assert "SENTINEL" not in "".join(m.reason for m in result.not_collected)


def test_an_item_with_its_own_character_set_is_read_under_an_unsupported_one(
    monkeypatch,
):
    # An item's own Specific Character Set replaces the one it would inherit
    # (PS3.5 Section 7.5.3), so its text can be read where the data set's
    # cannot.
    data_set = (
        _explicit(0x00080005, "CS", b"ISO_IR 999")
        + _explicit(0x00100010, "PN", b"SENTINEL^NAME ")
        + _explicit(
            0x00101002,
            "SQ",
            _item(
                _explicit(0x00080005, "CS", b"ISO_IR 192")
                + _explicit(0x00100020, "LO", b"SENTINEL ID ")
            )
            + _item(_explicit(0x00100020, "LO", b"SENTINEL ID 2 ")),
        )
        + _explicit(0x00101040, "LO", b"SENTINEL ADDR ")
    )
    evidence = source.read_source(_file(EXPLICIT, data_set))
    plan = walker.plan_instance(evidence, _rules(), _rt_plan())
    reads = []
    original = source.SourceEvidence.dataset

    def counted(self):
        reads.append(self)
        return original(self)

    monkeypatch.setattr(source.SourceEvidence, "dataset", counted)
    result = edits.edit_instance(evidence, plan, KEY)

    (sequestration,) = result.sequestrations
    assert sequestration.path == _path("(0008,0005)")
    assert sequestration.reason is walker.SequesterReason.UNSUPPORTED_CHARACTER_SET
    assert not result.edits
    assert _collected(result) == {
        _path(("(0010,1002)", 0), "(0008,0005)"): ("CS", "ISO_IR 192"),
        _path(("(0010,1002)", 0), "(0010,0020)"): ("LO", "SENTINEL ID"),
    }
    # Text that inherits the unsupported character set is not read.
    assert [missing.path for missing in result.not_collected] == [
        _path("(0010,0010)"),
        _path(("(0010,1002)", 1), "(0010,0020)"),
        _path("(0010,1040)"),
    ]
    assert "SENTINEL" not in "".join(m.reason for m in result.not_collected)
    # The source is read once, however many values cannot be.
    assert len(reads) == 1


def test_a_sequestered_plan_is_not_edited():
    plan, result = _edits(_explicit(0x300A00B0, "OB", b"SENTINEL"))

    assert plan.sequestrations
    assert result.sequestrations == plan.sequestrations
    assert not result.edits
    # Beam Sequence is kept, so it has no value to collect.
    assert not result.source_values
    assert not result.not_collected


def test_a_sequestered_plan_still_collects_every_value_that_decodes():
    # Responsible Person (0010,2297) is required by the RT Plan IOD, so its
    # plain X sequesters the plan (D-020).
    data_set = (
        _explicit(0x00080016, "UI", RT_PLAN_CLASS.encode() + b"\x00")
        + _explicit(0x00080018, "UI", INSTANCE_UID.encode())
        + _explicit(0x00081030, "LO", b"SENTINEL \xe9")
        + _explicit(
            0x00101002, "SQ", _item(_explicit(0x00100020, "LO", b"SENTINEL ID "))
        )
        + _explicit(0x00102297, "PN", b"SENTINEL^NAME ")
    )
    plan, result = _edits(data_set)

    assert [each.reason for each in plan.sequestrations] == [
        walker.SequesterReason.REQUIRED_BY_IOD
    ]
    # A sequestered plan still plans every element, with its consumers.
    assert [element.path for element in plan.elements] == [
        _path("(0008,0016)"),
        _path("(0008,0018)"),
        _path("(0008,1030)"),
        OTHER_IDS,
        _path(("(0010,1002)", 0), "(0010,0020)"),
        _path("(0010,2297)"),
    ]
    assert result.sequestrations == plan.sequestrations
    assert not result.edits
    assert not result.not_collected
    assert _collected(result) == {
        _path("(0008,0018)"): ("UI", INSTANCE_UID),
        _path("(0008,1030)"): ("LO", "SENTINEL \xe9"),
        _path(("(0010,1002)", 0), "(0010,0020)"): ("LO", "SENTINEL ID"),
        _path("(0010,2297)"): ("PN", "SENTINEL^NAME"),
    }
    assert result.read_as_latin_1 == (_path("(0008,1030)"),)
    assert result.registered_uids == (_path("(0008,0016)"),)
    assert "SENTINEL" not in repr(result)
    assert INSTANCE_UID not in repr(result)


def test_a_sequestration_while_editing_keeps_the_values_before_and_after_it(
    monkeypatch,
):
    # Beam Name (300A,00C2) is removed from a kept Beam Sequence (300A,00B0).
    first_beam = _path(("(300A,00B0)", 0), "(300A,00C2)")
    second_beam = _path(("(300A,00B0)", 1), "(300A,00C2)")
    _refusing(monkeypatch, _path("(300A,0002)"), first_beam)
    data_set = (
        _explicit(0x00080018, "UI", INSTANCE_UID.encode())
        + _explicit(0x00081030, "LO", b"SENTINEL DESC ")
        + _explicit(0x300A0002, "SH", b"SENTINEL")
        + _explicit(
            0x300A00B0,
            "SQ",
            _item(_explicit(0x300A00C2, "LO", b"SENTINEL BEAM "))
            + _item(_explicit(0x300A00C2, "LO", b"SENTINEL BEAM 2 ")),
        )
    )
    plan, result = _edits(data_set)

    assert not plan.sequestrations
    # D on Plan Label (300A,0002) needs its value.
    assert result.sequestrations == (
        walker.Sequestration(
            _path("(300A,0002)"), "D", "SH", walker.SequesterReason.UNDECODABLE
        ),
    )
    assert not result.edits
    assert _collected(result) == {
        _path("(0008,0018)"): ("UI", INSTANCE_UID),
        _path("(0008,1030)"): ("LO", "SENTINEL DESC"),
        second_beam: ("LO", "SENTINEL BEAM 2"),
    }
    # The value that the sequestering failure could not read, and one that is
    # only collected, are listed, in file order.
    assert [missing.path for missing in result.not_collected] == [
        _path("(300A,0002)"),
        first_beam,
    ]
    shown = repr(result) + "".join(repr(m) for m in result.not_collected)
    assert "SENTINEL" not in shown
    assert INSTANCE_UID not in shown


def test_an_unsupported_character_set_in_an_item_keeps_the_other_values(
    monkeypatch,
):
    _refusing(monkeypatch, _path("(300A,0002)"))
    in_item = (("(0010,1002)", 0),)
    data_set = (
        _explicit(0x00081030, "LO", b"SENTINEL DESC ")
        + _explicit(
            0x00101002,
            "SQ",
            _item(
                _explicit(0x00080005, "CS", b"ISO_IR 999")
                + _explicit(0x00100020, "LO", b"SENTINEL ID ")
            )
            + _item(_explicit(0x00100020, "LO", b"SENTINEL ID 2 ")),
        )
        + _explicit(0x300A0002, "SH", b"SENTINEL")
        + _explicit(0x300A0003, "LO", b"SENTINEL PLAN ")
    )
    _, result = _edits(data_set)

    # Collection carries on past the first sequestration, and finds the
    # second.
    assert result.sequestrations == (
        walker.Sequestration(
            walker.ElementPath(in_item, "(0008,0005)"),
            "X",
            "CS",
            walker.SequesterReason.UNSUPPORTED_CHARACTER_SET,
        ),
        walker.Sequestration(
            _path("(300A,0002)"), "D", "SH", walker.SequesterReason.UNDECODABLE
        ),
    )
    assert not result.edits
    collected = _collected(result)
    assert collected[_path("(0008,1030)")] == ("LO", "SENTINEL DESC")
    assert collected[_path(("(0010,1002)", 1), "(0010,0020)")] == (
        "LO",
        "SENTINEL ID 2",
    )
    assert collected[_path("(300A,0003)")][1] == "SENTINEL PLAN"
    assert [missing.path for missing in result.not_collected] == [
        walker.ElementPath(in_item, "(0008,0005)"),
        walker.ElementPath(in_item, "(0010,0020)"),
        _path("(300A,0002)"),
    ]
    assert "SENTINEL" not in "".join(m.reason for m in result.not_collected)
    assert "SENTINEL" not in repr(result)


def test_results_hold_no_value_in_their_reprs(monkeypatch):
    _, result = _edits()
    _, latin_1 = _edits(
        _explicit(0x00081030, "LO", b"SENTINEL \xe9")
        + _person_identification_codes(b"SENTINEL")
    )
    assert latin_1.read_as_latin_1
    _refusing(monkeypatch, _path("(0008,1030)"))
    _, failed = _edits(_explicit(0x00081030, "LO", b"SENTINEL DESC "))
    assert failed.not_collected
    shown = (
        repr(result)
        + repr(failed)
        + repr(latin_1)
        + "".join(repr(edit) for edit in latin_1.edits)
        + "".join(repr(edit) for edit in result.edits)
        + "".join(repr(missing) for missing in failed.not_collected)
        + repr(pickle.loads(pickle.dumps(result.edits)))
    )

    assert "SENTINEL" not in shown
    assert "DEIDENTIFIED" not in shown
    assert INSTANCE_UID not in shown


def test_a_kept_sequence_whose_items_cannot_be_read_sequesters(monkeypatch):
    original = elements.read_element

    def refusing(dataset, path, *args, **kwargs):
        if path == BEAM_SEQUENCE:
            raise elements.UndecodableElement(path, "has items that cannot be read")
        return original(dataset, path, *args, **kwargs)

    monkeypatch.setattr(elements, "read_element", refusing)
    _, result = _edits()

    (sequestration,) = result.sequestrations
    assert (sequestration.path, sequestration.action) == (BEAM_SEQUENCE, "K")
    assert sequestration.reason is walker.SequesterReason.UNDECODABLE
    assert not result.edits
    # The values outside it are collected, and those in it listed.
    collected = _collected(result)
    assert collected[_path("(0010,0010)")] == ("PN", "SENTINEL^NAME")
    assert collected[_path(("(0010,1002)", 0), "(0010,0020)")] == (
        "LO",
        "SENTINEL ID",
    )
    assert [missing.path for missing in result.not_collected] == [
        _path(("(300A,00B0)", 0), "(300A,00C2)")
    ]


def test_a_removed_sequence_whose_items_cannot_be_read_is_not_collected(
    monkeypatch,
):
    original = elements.read_element

    def refusing(dataset, path, *args, **kwargs):
        if path == OTHER_IDS:
            raise elements.UndecodableElement(path, "has items that cannot be read")
        return original(dataset, path, *args, **kwargs)

    monkeypatch.setattr(elements, "read_element", refusing)
    _, result = _edits()

    assert not result.sequestrations
    missing = {each.path for each in result.not_collected}
    assert missing == {
        _path(("(0010,1002)", 0), "(0010,0020)"),
        _path(("(0010,1002)", 0), ("(0010,1002)", 0), "(0010,0020)"),
    }


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_patients_name_and_id_take_the_pseudonyms_of_a_given_identity():
    evidence = source.read_source(
        _file(
            EXPLICIT,
            _explicit(0x00100010, "PN", b"SENTINEL^NAME ")
            + _explicit(0x00100020, "LO", b"SENTINEL ID "),
        )
    )
    plan = walker.plan_instance(evidence, _rules(), _rt_plan())
    identity = SubjectIdentity.from_patient_id("SENTINEL ID")
    pseudonym = patient_pseudonym(KEY, identity)

    result = edits.edit_instance(evidence, plan, KEY, identity)

    assert [(edit.kind, edit.values) for edit in result.edits] == [
        (EditKind.REPLACE, (pseudonym.patients_name,)),
        (EditKind.REPLACE, (pseudonym.patient_id,)),
    ]
    # The source values are still collected.
    assert {value.source for value in result.source_values} == {
        edit.path for edit in result.edits
    }


def test_a_sequence_kept_under_u_is_kept_and_its_items_are_edited():
    data_set = _explicit(
        0x300A00B0, "SQ", _item(_explicit(0x300A00C2, "LO", b"SENTINEL BEAM "))
    )
    _, result = _edits(data_set, _Overridden({"(300A,00B0)": "U"}))
    sequence, name = result.edits

    assert (sequence.path, sequence.action) == (BEAM_SEQUENCE, "U")
    assert (sequence.kind, sequence.values) == (EditKind.KEEP, ())
    assert name.kind is EditKind.REMOVE
    assert BEAM_SEQUENCE not in _collected(result)


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_a_sequence_kept_under_u_by_its_iod_is_kept_and_its_uids_replaced():
    # X/Z/U* on Referenced Image Sequence (0008,1140), Type 1 in an
    # X-Ray Angiographic Image, resolves to U.
    data_set = _explicit(
        0x00081140,
        "SQ",
        _item(
            _explicit(0x00081150, "UI", RT_PLAN_CLASS.encode() + b"\x00")
            + _explicit(0x00081155, "UI", INSTANCE_UID.encode())
        ),
    )
    evidence = source.read_source(_file(EXPLICIT, data_set))
    iod = load_iod_tables().iods["X-Ray Angiographic Image"]
    plan = walker.plan_instance(evidence, _rules(), iod)
    sequence, class_uid, instance_uid = edits.edit_instance(evidence, plan, KEY).edits

    assert (sequence.action, sequence.kind) == ("U", EditKind.KEEP)
    assert class_uid.values == (RT_PLAN_CLASS,)
    assert instance_uid.values == (replacement_uid(KEY, INSTANCE_UID),)


def test_each_sequence_is_read_once_however_many_items_it_has(monkeypatch):
    read = []
    original = elements.read_element

    def recording(dataset, path, *args, **kwargs):
        read.append(path)
        return original(dataset, path, *args, **kwargs)

    monkeypatch.setattr(elements, "read_element", recording)
    beam = _item(_explicit(0x300A00C2, "LO", b"SENTINEL BEAM "))
    _, result = _edits(_explicit(0x300A00B0, "SQ", beam * 50))

    assert len(result.source_values) == 50
    assert read.count(BEAM_SEQUENCE) == 1


def test_an_items_character_set_is_inherited_or_its_own():
    data_set = _explicit(0x00080005, "CS", b"ISO_IR 100") + _explicit(
        0x00101002,
        "SQ",
        _item(
            _explicit(0x00080005, "CS", b"ISO_IR 192")
            + _explicit(0x00100020, "LO", b"SENTINEL ID ")
        )
        + _item(_explicit(0x00100020, "LO", b"SENTINEL ID ")),
    )
    _, result = _edits(data_set)
    codecs = {value.source: value.codecs for value in result.source_values}

    own = codecs[_path(("(0010,1002)", 0), "(0010,0020)")]
    assert own != ("latin_1",)
    assert codecs[_path(("(0010,1002)", 1), "(0010,0020)")] == ("latin_1",)


@pytest.mark.parametrize("action", ["K", "X"])
def test_an_unsupported_character_set_in_an_item_sequesters_the_instance(action):
    # D-010, whether the item is kept, with nothing in it read, or removed.
    # Beam Sequence is Type 1, so the engine's rule removes it, as a plain X
    # from Table E.1-1 would sequester the instance (D-020).
    data_set = _explicit(
        0x300A00B0,
        "SQ",
        _item(
            _explicit(0x00080005, "CS", b"ISO_IR 999")
            + _explicit(0x300A00C0, "IS", b"1 ")
        ),
    )
    _, result = _edits(
        data_set, _Overridden({"(300A,00B0)": action}, RuleSource.ENGINE)
    )

    (sequestration,) = result.sequestrations
    assert sequestration.path == _path(("(300A,00B0)", 0), "(0008,0005)")
    assert sequestration.reason is walker.SequesterReason.UNSUPPORTED_CHARACTER_SET
    assert sequestration.action == ("K" if action == "K" else "X")
    assert not result.edits


def test_an_undecodable_patient_id_that_is_removed_is_not_collected(monkeypatch):
    _refusing(monkeypatch, _path("(0010,0020)"))
    # The engine's rule removes it alone; a plain X from Table E.1-1 would
    # sequester the instance, as Patient ID is Type 2 (D-020).
    _, result = _edits(
        _explicit(0x00100020, "LO", b"SENTINEL ID "),
        _Overridden({"(0010,0020)": "X"}, RuleSource.ENGINE),
    )

    (patient_id,) = result.edits
    assert patient_id.kind is EditKind.REMOVE
    assert not result.sequestrations
    assert [missing.path for missing in result.not_collected] == [_path("(0010,0020)")]


CODES = _path(("(0044,0110)", 0), ("(0044,0103)", 0), "(0040,1101)")
CODE_ITEM = (*CODES.items, (CODES.tag, 0))
CODE_VALUE = walker.ElementPath(CODE_ITEM, "(0008,0100)")


def _person_identification_codes(value, meaning=b"SENTINEL^NAME "):
    """Person Identification Code Sequence (0040,1101) in RT Assertions.

    RT Assertions Sequence (0044,0110) and Asserter Identification Sequence
    (0044,0103) are kept, so D applies to the codes (D-021).
    """
    code = _explicit(0x00080100, "SH", value)
    code += _explicit(0x00080102, "SH", b"99LOCAL ")
    code += _explicit(0x00080104, "LO", meaning)
    return _explicit(
        0x00440110,
        "SQ",
        _item(
            _explicit(0x00440103, "SQ", _item(_explicit(0x00401101, "SQ", _item(code))))
        ),
    )


def _dummy_item(code_value, code_meaning):
    return (
        (
            DummyElement("(0008,0100)", "SH", code_value),
            DummyElement("(0008,0102)", "SH", "99PYMEDPHYS"),
            DummyElement("(0008,0104)", "LO", code_meaning),
        ),
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_d_replaces_person_identification_code_sequence_with_its_dummy_item():
    # D-021: one item of constants, the second ones where a source item's
    # Code Value or Code Meaning equals the first.
    for value, meaning, expected in [
        (b"SENTINEL", b"SENTINEL^NAME ", ("DEIDENTIFIED", "DEIDENTIFIED^DEIDENTIFIED")),
        (
            b"deidentified",
            b"SENTINEL^NAME ",
            ("DE-IDENTIFIED", "DE-IDENTIFIED^DE-IDENTIFIED"),
        ),
        (
            b"SENTINEL",
            b"DEIDENTIFIED^DEIDENTIFIED^",
            ("DE-IDENTIFIED", "DE-IDENTIFIED^DE-IDENTIFIED"),
        ),
    ]:
        _, result = _edits(_person_identification_codes(value, meaning))
        found = {edit.path: edit for edit in result.edits}

        assert not result.sequestrations
        codes = found[CODES]
        assert (codes.action, codes.kind) == ("D", EditKind.REPLACE)
        assert codes.items == _dummy_item(*expected)
        assert (codes.values, codes.removed_with) == ((), None)
        # The source items are removed with the sequence that the edit
        # replaces, and their values are collected.
        for tag in ("(0008,0100)", "(0008,0102)", "(0008,0104)"):
            edit = found[walker.ElementPath(CODE_ITEM, tag)]
            assert (edit.kind, edit.removed_with) == (EditKind.REMOVE, CODES)
        assert _collected(result)[CODE_VALUE] == ("SH", value.decode().strip())


def test_an_undecodable_person_identification_code_sequesters(monkeypatch):
    # D compares each source Code Value with its constant, so it needs it.
    _refusing(monkeypatch, CODE_VALUE)
    _, result = _edits(_person_identification_codes(b"SENTINEL"))

    assert result.sequestrations == (
        walker.Sequestration(CODE_VALUE, "D", "SH", walker.SequesterReason.UNDECODABLE),
    )
    assert not result.edits


def test_a_person_identification_code_outside_iso_646_is_compared_as_latin_1():
    _, result = _edits(_person_identification_codes(b"SENTINEL \xe9"))
    found = {edit.path: edit for edit in result.edits}

    assert not result.sequestrations
    assert found[CODES].items == _dummy_item(
        "DEIDENTIFIED", "DEIDENTIFIED^DEIDENTIFIED"
    )
    assert result.read_as_latin_1 == (CODE_VALUE,)


def test_each_extent_of_a_plain_x_gives_its_edits():
    # D-020: an enclosing Type 3 sequence is removed with the attribute,
    # every attribute of an overlay group with Overlay Data, and otherwise,
    # where the IOD requires the attribute, the instance is sequestered.
    _, result = _edits(_patient_setup_photo())
    found = {edit.path: edit for edit in result.edits}
    description = walker.ElementPath(PHOTO_ITEM, "(300A,0794)")

    assert not result.sequestrations
    assert (found[PHOTOS].kind, found[PHOTOS].removed_with) == (EditKind.REMOVE, None)
    assert (found[description].kind, found[description].removed_with) == (
        EditKind.REMOVE,
        PHOTOS,
    )
    assert found[_path(("(300A,0180)", 0), "(300A,079F)")].kind is EditKind.KEEP
    assert _collected(result)[description] == ("LT", "SENTINEL PLAN")

    overlay = _explicit(0x60000010, "US", b"\x00\x02") + _explicit(
        0x60003000, "OW", bytes(4)
    )
    evidence = source.read_source(_file(EXPLICIT, overlay))
    ct = load_iod_tables().iods["CT Image"]
    plan = walker.plan_instance(evidence, _rules(), ct)
    overlay_edits = edits.edit_instance(evidence, plan, KEY).edits
    assert [edit.kind for edit in overlay_edits] == [EditKind.REMOVE] * 2

    _, sequestered = _edits(_explicit(0x00102297, "PN", b"SENTINEL^NAME "))
    (reason,) = sequestered.sequestrations
    assert reason.reason is walker.SequesterReason.REQUIRED_BY_IOD
    assert not sequestered.edits
