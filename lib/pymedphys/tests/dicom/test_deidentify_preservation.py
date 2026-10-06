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

"""Verify that a written file preserves what its source kept, byte for byte.

Every file is synthetic and encoded by hand, so that each output differs
from its source in exactly one way. Values that must never appear in a
message carry the text ``SENTINEL``.
"""

import struct

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.preservation import (
    Expectations,
    PreservationFailed,
    PreservationReason,
    verify_preservation,
)
from pymedphys._dicom.deidentify.source import read_source

from .test_deidentify_file_layout import (
    EXPLICIT,
    IMPLICIT,
    ITEM_END,
    SEQUENCE_END,
    UNDEFINED,
    _explicit,
    _file,
    _implicit,
    _item,
)

pytestmark = pytest.mark.pydicom

NAME = b"SENTINEL^NAME "
DESCRIPTION = b"SENTINEL BEAM "
DOCUMENT = b"SENTINEL DOCUMENT "
# A LUT Descriptor of 4096 entries, from 0, of 16 bits (PS3.3 C.11.2.1.1).
LUT_DESCRIPTOR = struct.pack("<3H", 4096, 0, 16)
SOP_CLASS = b"1.2.840.10008.5.1.4.1.1.481.5\x00"


def _path(*steps):
    return ElementPath(tuple(steps[:-1]), steps[-1])


CHARACTER_SET = _path("(0008,0005)")
NAME_PATH = _path("(0010,0010)")
DOCUMENT_PATH = _path("(0042,0011)")
VOI_LUT = _path("(0028,3010)")
DESCRIPTOR = _path(("(0028,3010)", 0), "(0028,3002)")
BEAMS = _path("(300A,00B0)")
BEAM_CHARACTER_SET = _path(("(300A,00B0)", 0), "(0008,0005)")
BEAM_NUMBER = _path(("(300A,00B0)", 0), "(300A,00C0)")
BEAM_NAME = _path(("(300A,00B0)", 0), "(300A,00C2)")


def _explicit_data_set(  # pylint: disable = too-many-arguments
    *,
    character_set=b"ISO_IR 100",
    name=NAME,
    document=_explicit(0x00420011, "OB", DOCUMENT),
    lut_vr="US",
    voi_lut=True,
    beam_character_set=b"ISO_IR 192",
    beam_number=b"1 ",
    sequence=None,
    extra=b"",
):
    """An RT Plan-like data set; each argument changes one thing about it."""
    beam = (
        (_explicit(0x00080005, "CS", beam_character_set) if beam_character_set else b"")
        + _explicit(0x300A00C0, "IS", beam_number)
        + _explicit(0x300A00C2, "LO", DESCRIPTION)
    )
    if sequence is None:  # undefined lengths, as the source has them
        sequence = (
            _explicit(0x300A00B0, "SQ", length=UNDEFINED)
            + _item(length=UNDEFINED)
            + beam
            + ITEM_END
            + SEQUENCE_END
        )
    elif sequence == "defined":
        sequence = _explicit(0x300A00B0, "SQ", _item(beam))
    elif sequence == "another-item":
        sequence = _explicit(0x300A00B0, "SQ", _item(beam) + _item())
    elif sequence == "UN":  # whose items are in implicit VR (PS3.5 6.2.2)
        beam = (
            _implicit(0x00080005, beam_character_set)
            + _implicit(0x300A00C0, beam_number)
            + _implicit(0x300A00C2, DESCRIPTION)
        )
        sequence = _explicit(0x300A00B0, "UN", _item(beam))
    return (
        (_explicit(0x00080005, "CS", character_set) if character_set else b"")
        + _explicit(0x00080016, "UI", SOP_CLASS)
        + (_explicit(0x00100010, "PN", name) if name else b"")
        + extra
        + (
            _explicit(
                0x00283010, "SQ", _item(_explicit(0x00283002, lut_vr, LUT_DESCRIPTOR))
            )
            if voi_lut
            else b""
        )
        + document
        + sequence
    )


def _implicit_data_set():
    return (
        _implicit(0x00080005, b"ISO_IR 100")
        + _implicit(0x00080016, SOP_CLASS)
        + _implicit(0x00100010, NAME)
        + _implicit(0x00283010, _item(_implicit(0x00283002, LUT_DESCRIPTOR)))
        + _implicit(
            0x300A00B0,
            _item(_implicit(0x300A00C0, b"1 ") + _implicit(0x300A00C2, DESCRIPTION)),
        )
    )


# Encapsulated Document's bytes as one fragment of an undefined length.
FRAGMENTS = (
    _explicit(0x00420011, "OB", length=UNDEFINED) + _item(DOCUMENT) + SEQUENCE_END
)
SOURCE = read_source(_file(EXPLICIT, _explicit_data_set()))
ALL = frozenset(SOURCE.paths())


def _output(**changes):
    return read_source(_file(EXPLICIT, _explicit_data_set(**changes)))


def _refused(output, expected=Expectations(kept=ALL), source=SOURCE):
    with pytest.raises(PreservationFailed) as raised:
        verify_preservation(source, output, expected)
    assert "SENTINEL" not in str(raised.value)
    assert "SENTINEL" not in repr(raised.value)
    return raised.value.reason, raised.value.path


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
@pytest.mark.parametrize(
    "data",
    [_file(EXPLICIT, _explicit_data_set()), _file(IMPLICIT, _implicit_data_set())],
    ids=["explicit-vr", "implicit-vr"],
)
def test_a_copy_that_keeps_every_element_is_preserved(data):
    evidence = read_source(data)

    verify_preservation(
        evidence, read_source(data), Expectations(kept=frozenset(evidence.paths()))
    )


def test_changed_and_removed_elements_need_not_be_preserved():
    output = _output(
        name=b"PSEUDONYM ", document=b"", extra=_explicit(0x00120062, "CS", b"YES ")
    )
    expected = Expectations(
        kept=ALL - {NAME_PATH, DOCUMENT_PATH},
        changed=frozenset({NAME_PATH, _path("(0012,0062)")}),
        removed=frozenset({DOCUMENT_PATH}),
    )

    verify_preservation(SOURCE, output, expected)


def test_a_removed_sequence_takes_its_descendants_with_it():
    output = _output(voi_lut=False, document=b"", sequence=b"")
    removed = frozenset(
        path for path in ALL if path in (VOI_LUT, DOCUMENT_PATH) or path.items
    ) | {BEAMS}

    verify_preservation(
        SOURCE, output, Expectations(kept=ALL - removed, removed=removed)
    )


def test_a_kept_sequence_may_be_written_with_defined_lengths():
    verify_preservation(SOURCE, _output(sequence="defined"), Expectations(kept=ALL))


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_another_transfer_syntax_is_refused():
    output = read_source(_file(IMPLICIT, _implicit_data_set()))

    assert _refused(output) == (PreservationReason.TRANSFER_SYNTAX, None)


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
@pytest.mark.parametrize(
    "expected, output, failure",
    [
        (
            Expectations(kept=ALL - {NAME_PATH}),
            _output(),
            (PreservationReason.UNPLANNED, NAME_PATH),
        ),
        (
            Expectations(kept=ALL),
            _output(extra=_explicit(0x00120062, "CS", b"YES ")),
            (PreservationReason.UNEXPECTED, _path("(0012,0062)")),
        ),
        (
            Expectations(kept=ALL - {NAME_PATH}, removed=frozenset({NAME_PATH})),
            _output(),
            (PreservationReason.NOT_REMOVED, NAME_PATH),
        ),
        (
            Expectations(kept=ALL),
            _output(name=b""),
            (PreservationReason.MISSING, NAME_PATH),
        ),
        (
            Expectations(kept=ALL | {_path("(0012,0062)")}),
            _output(),
            (PreservationReason.MISSING, _path("(0012,0062)")),
        ),
        (
            Expectations(kept=ALL - {NAME_PATH}, changed=frozenset({NAME_PATH})),
            _output(name=b""),
            (PreservationReason.MISSING, NAME_PATH),
        ),
    ],
    ids=[
        "unplanned",
        "unexpected",
        "not-removed",
        "kept-missing-from-output",
        "kept-missing-from-source",
        "changed-missing-from-output",
    ],
)
def test_each_element_must_correspond_to_its_plan(expected, output, failure):
    assert _refused(output, expected) == failure


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_a_kept_value_that_decodes_the_same_from_other_bytes_is_refused():
    # "01" and "1 " are both the integer 1.
    assert _refused(_output(beam_number=b"01")) == (
        PreservationReason.VALUE,
        BEAM_NUMBER,
    )


def test_a_kept_name_with_other_bytes_is_refused():
    assert _refused(_output(name=b"SENTINEL^NAMF ")) == (
        PreservationReason.VALUE,
        NAME_PATH,
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_an_ambiguous_vr_resolved_again_with_the_same_bytes_is_refused():
    # A writer that resolves US or SS again, as pydicom's can, changes only
    # the VR of the LUT Descriptor.
    assert _refused(_output(lut_vr="SS")) == (PreservationReason.VR, DESCRIPTOR)


def test_a_kept_sequence_written_with_another_vr_is_refused():
    assert _refused(_output(sequence="UN")) == (PreservationReason.VR, BEAMS)


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_a_kept_sequence_with_another_number_of_items_is_refused():
    assert _refused(_output(sequence="another-item")) == (
        PreservationReason.STRUCTURE,
        BEAMS,
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_a_kept_value_written_with_another_length_encoding_is_refused():
    assert _refused(_output(document=FRAGMENTS)) == (
        PreservationReason.LENGTH,
        DOCUMENT_PATH,
    )


def test_a_kept_value_of_undefined_length_cannot_be_verified():
    source = _output(document=FRAGMENTS)

    assert _refused(_output(document=FRAGMENTS), source=source) == (
        PreservationReason.UNVERIFIABLE,
        DOCUMENT_PATH,
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
@pytest.mark.parametrize(
    "changes, path",
    [
        ({"character_set": b"ISO_IR 192"}, NAME_PATH),
        ({"character_set": b""}, NAME_PATH),
        ({"beam_character_set": b"ISO_IR 100"}, BEAM_NAME),
        # The item now inherits ISO_IR 100 from the top level.
        ({"beam_character_set": b""}, BEAM_NAME),
    ],
    ids=["replaced", "removed", "item-replaced", "item-removed"],
)
def test_kept_text_in_another_character_set_is_refused(changes, path):
    holders = {CHARACTER_SET, BEAM_CHARACTER_SET}
    output = _output(**changes)
    written = frozenset(holders & set(output.paths()))
    expected = Expectations(
        kept=ALL - holders, changed=written, removed=frozenset(holders - written)
    )

    assert _refused(output, expected) == (
        PreservationReason.CHARACTER_SET,
        path,
    )


def test_a_kept_value_that_is_not_text_ignores_the_character_set():
    holders = {CHARACTER_SET, BEAM_CHARACTER_SET}
    output = _output(character_set=b"ISO_IR 192", beam_character_set=b"ISO_IR 100")
    # Only the text elements are changed, so that the rest must be preserved.
    changed = frozenset(holders | {NAME_PATH, BEAM_NAME})

    verify_preservation(
        SOURCE, output, Expectations(kept=ALL - changed, changed=changed)
    )


def test_an_element_planned_twice_is_rejected():
    with pytest.raises(ValueError, match=r"\(0010,0010\)"):
        Expectations(kept=ALL, removed=frozenset({NAME_PATH}))


def test_a_failure_names_its_reason_and_path_only():
    failure = PreservationFailed(PreservationReason.VALUE, BEAM_NAME)

    assert str(failure) == (
        "preservation cannot be shown (value) at (300A,00B0)[0] > (300A,00C2)"
    )
    assert str(PreservationFailed(PreservationReason.TRANSFER_SYNTAX)) == (
        "preservation cannot be shown (transfer-syntax)"
    )


def _in_items(depth, content, tag=0x300A00B0):
    """``content`` in the first item of ``depth`` nested sequences."""
    for _ in range(depth):
        content = _explicit(tag, "SQ", _item(content))
    return content


def _character_sets(character_set, inner=b""):
    return _explicit(0x00080005, "CS", character_set) + inner


def _private(element, character_set, creator=b"SENTINEL CREATOR"):
    """A Specific Character Set, a Private Creator, and private text."""
    return (
        element(0x00080005, "CS", character_set)
        + (element(0x00090010, "LO", creator) if creator else b"")
        + element(0x00091001, "UN", b"SENTINEL")
    )


def _private_container(vr, creator=b"SENTINEL CREATOR"):
    """A Private Creator and a private element that holds one item.

    The item of a UN is in implicit VR (PS3.5 Section 6.2.2).
    """
    item = _implicit(0x300A00C2, DESCRIPTION) if vr == "UN" else TEXT
    return (
        _explicit(0x00080005, "CS", b"ISO_IR 100")
        + (_explicit(0x00090010, "LO", creator) if creator else b"")
        + _explicit(0x00091002, vr, _item(item))
    )


def _implicit_element(tag, _vr, value):
    return _implicit(tag, value)


BEAM = ("(300A,00B0)", 0)
TEXT = _explicit(0x300A00C2, "LO", DESCRIPTION)
PRIVATE_TEXT = _path("(0009,1001)")
PRIVATE_CONTAINER = _path("(0009,1002)")
CREATOR = _path("(0009,0010)")
CHARACTER_SET_FRAGMENTS = (
    _explicit(0x00080005, "OB", length=UNDEFINED) + _item(b"ISO_IR 100") + SEQUENCE_END
)
CONTEXT_CASES = {
    # The item has no Specific Character Set, so the top level's applies.
    "inherited-by-an-item": (
        _file(EXPLICIT, _character_sets(b"ISO_IR 100", _in_items(1, TEXT))),
        _file(EXPLICIT, _character_sets(b"ISO_IR 192", _in_items(1, TEXT))),
        {CHARACTER_SET},
        set(),
        (PreservationReason.CHARACTER_SET, _path(BEAM, "(300A,00C2)")),
    ),
    "inherited-by-a-nested-item": (
        _file(EXPLICIT, _character_sets(b"ISO_IR 100", _in_items(2, TEXT))),
        _file(EXPLICIT, _character_sets(b"ISO_IR 192", _in_items(2, TEXT))),
        {CHARACTER_SET},
        set(),
        (PreservationReason.CHARACTER_SET, _path(BEAM, BEAM, "(300A,00C2)")),
    ),
    # The outer item's applies two levels below it, the top level's nowhere.
    "held-two-levels-up": (
        _file(
            EXPLICIT,
            _character_sets(
                b"ISO_IR 100",
                _in_items(1, _character_sets(b"ISO_IR 100", _in_items(2, TEXT))),
            ),
        ),
        _file(
            EXPLICIT,
            _character_sets(
                b"ISO_IR 100",
                _in_items(1, _character_sets(b"ISO_IR 192", _in_items(2, TEXT))),
            ),
        ),
        {_path(BEAM, "(0008,0005)")},
        set(),
        (PreservationReason.CHARACTER_SET, _path(BEAM, BEAM, BEAM, "(300A,00C2)")),
    ),
    # Private text has no VR in implicit VR, and UN in explicit VR.
    "private-implicit-vr": (
        _file(IMPLICIT, _private(_implicit_element, b"ISO_IR 100")),
        _file(IMPLICIT, _private(_implicit_element, b"ISO_IR 192")),
        {CHARACTER_SET, CREATOR},
        set(),
        (PreservationReason.CHARACTER_SET, PRIVATE_TEXT),
    ),
    "private-un": (
        _file(EXPLICIT, _private(_explicit, b"ISO_IR 100")),
        _file(EXPLICIT, _private(_explicit, b"ISO_IR 192")),
        {CHARACTER_SET, CREATOR},
        set(),
        (PreservationReason.CHARACTER_SET, PRIVATE_TEXT),
    ),
    # A Specific Character Set that holds fragments, not one value.
    "character-set-of-fragments": (
        _file(EXPLICIT, CHARACTER_SET_FRAGMENTS + _explicit(0x00100010, "PN", NAME)),
        _file(EXPLICIT, CHARACTER_SET_FRAGMENTS + _explicit(0x00100010, "PN", NAME)),
        {CHARACTER_SET},
        set(),
        (PreservationReason.CHARACTER_SET, NAME_PATH),
    ),
    "another-private-creator": (
        _file(EXPLICIT, _private(_explicit, b"ISO_IR 100")),
        _file(EXPLICIT, _private(_explicit, b"ISO_IR 100", b"ANOTHER CREATOR ")),
        {CREATOR},
        set(),
        (PreservationReason.PRIVATE_CREATOR, PRIVATE_TEXT),
    ),
    "no-private-creator": (
        _file(EXPLICIT, _private(_explicit, b"ISO_IR 100")),
        _file(EXPLICIT, _private(_explicit, b"ISO_IR 100", b"")),
        set(),
        {CREATOR},
        (PreservationReason.PRIVATE_CREATOR, PRIVATE_TEXT),
    ),
    # A kept private container needs its creator too (PS3.5 Section 7.8.1).
    **{
        f"{change}-private-creator-of-{vr}-items": (
            _file(EXPLICIT, _private_container(vr)),
            _file(EXPLICIT, _private_container(vr, creator)),
            changed,
            removed,
            (PreservationReason.PRIVATE_CREATOR, PRIVATE_CONTAINER),
        )
        for vr in ("SQ", "UN")
        for change, creator, changed, removed in (
            ("another", b"ANOTHER CREATOR ", {CREATOR}, set()),
            ("no", b"", set(), {CREATOR}),
        )
    },
}


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
@pytest.mark.parametrize(
    "source, output, changed, removed, failure",
    CONTEXT_CASES.values(),
    ids=CONTEXT_CASES,
)
def test_a_kept_element_in_another_context_is_refused(
    source, output, changed, removed, failure
):
    source = read_source(source)
    expected = Expectations(
        kept=frozenset(source.paths()) - changed - removed,
        changed=frozenset(changed),
        removed=frozenset(removed),
    )

    assert _refused(read_source(output), expected, source) == failure


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_an_empty_specific_character_set_is_the_default_as_an_absent_one_is():
    # Both give the Default Character Repertoire (PS3.3 C.12.1.1.2).
    source = read_source(
        _file(EXPLICIT, _in_items(1, _explicit(0x00080005, "CS", b"  ") + TEXT))
    )
    output = read_source(_file(EXPLICIT, _in_items(1, TEXT)))
    holder = _path(BEAM, "(0008,0005)")

    verify_preservation(
        source,
        output,
        Expectations(
            kept=frozenset(source.paths()) - {holder}, removed=frozenset({holder})
        ),
    )
