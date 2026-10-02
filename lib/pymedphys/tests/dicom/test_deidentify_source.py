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

"""The immutable evidence of a source file, and elements read against it.

Every file is synthetic and encoded by hand here, so that malformed
structures do not depend on pydicom's writer. Values that must never appear
in a message carry the text ``SENTINEL``.
"""

import logging

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import elements, file_layout, source
from pymedphys._dicom.deidentify.file_layout import ElementPath

from .test_deidentify_file_layout import (
    EXPLICIT,
    IMPLICIT,
    ITEM_END,
    MALFORMED,
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
ROI_NAME = b"SENTINEL ROI"
BEAM_SEQUENCE = 0x300A00B0
BEAM_NAME = 0x300A00C2
BEAM_NUMBER = 0x300A00C0
RT_ASSERTIONS = 0x00440110
ASSERTION_UID = 0x00440102
PADDING = 0xFFFCFFFC


def _path(*steps):
    return ElementPath(tuple(steps[:-1]), steps[-1])


def _explicit_data_set():
    """Elements, sequences of both length forms, UN items, and padding."""
    return (
        _explicit(0x00080016, "UI", b"1.2.840.10008.5.1.4.1.1.481.5\x00")
        + _explicit(0x00100010, "PN", NAME)
        # RT Assertions Sequence as UN, whose items are implicit VR (PS3.5
        # Section 6.2.2).
        + _explicit(
            RT_ASSERTIONS, "UN", _item(_implicit(ASSERTION_UID, b"2.25.4401\x00"))
        )
        + _explicit(BEAM_SEQUENCE, "SQ", length=UNDEFINED)
        + _item(length=UNDEFINED)
        + _explicit(BEAM_NUMBER, "IS", b"1 ")
        + _explicit(BEAM_NAME, "LO", DESCRIPTION)
        + ITEM_END
        + _item(_explicit(BEAM_NUMBER, "IS", b"2 "))
        + SEQUENCE_END
        + _explicit(PADDING, "OB", bytes(4))
    )


def _implicit_data_set():
    return (
        _implicit(0x00080016, b"1.2.840.10008.5.1.4.1.1.481.5\x00")
        + _implicit(0x00100010, NAME)
        + _implicit(RT_ASSERTIONS, _item(_implicit(ASSERTION_UID, b"2.25.4401\x00")))
        + _implicit(
            BEAM_SEQUENCE,
            _item(_implicit(BEAM_NUMBER, b"1 ") + _implicit(BEAM_NAME, DESCRIPTION))
            + _item(_implicit(BEAM_NUMBER, b"2 ")),
        )
    )


EXPECTED_PATHS = [
    _path("(0008,0016)"),
    _path("(0010,0010)"),
    _path("(0044,0110)"),
    _path(("(0044,0110)", 0), "(0044,0102)"),
    _path("(300A,00B0)"),
    _path(("(300A,00B0)", 0), "(300A,00C0)"),
    _path(("(300A,00B0)", 0), "(300A,00C2)"),
    _path(("(300A,00B0)", 1), "(300A,00C0)"),
]
NAME_PATH = _path("(0010,0010)")
BEAM_NAME_PATH = _path(("(300A,00B0)", 0), "(300A,00C2)")
ASSERTION_UID_PATH = _path(("(0044,0110)", 0), "(0044,0102)")


def test_evidence_indexes_every_data_set_element_by_its_path():
    data = _file(EXPLICIT, _explicit_data_set())

    evidence = source.read_source(data)

    assert list(evidence.paths()) == [*EXPECTED_PATHS, _path("(FFFC,FFFC)")]
    assert evidence.size == len(data)
    assert evidence.transfer_syntax == EXPLICIT
    assert evidence.value_field(NAME_PATH) == NAME
    assert evidence.value_field(BEAM_NAME_PATH) == DESCRIPTION
    assert evidence.value_field(ASSERTION_UID_PATH) == b"2.25.4401\x00"
    name = evidence.element(NAME_PATH)
    assert (name.vr, name.undefined_length) == ("PN", False)
    assert data[name.value_start : name.end] == NAME
    assert data[name.start : name.value_start] == _explicit(0x00100010, "PN", NAME)[:8]
    assert evidence.element(_path("(300A,00B0)")).undefined_length
    assert evidence.element(_path("(0044,0110)")).vr == "UN"
    # File Meta Information is not part of the data set.
    with pytest.raises(KeyError):
        evidence.element(_path("(0002,0010)"))


def test_implicit_vr_evidence_records_no_vr():
    data = _file(IMPLICIT, _implicit_data_set())

    evidence = source.read_source(data)

    assert list(evidence.paths()) == EXPECTED_PATHS
    assert evidence.element(NAME_PATH).vr is None
    assert evidence.value_field(BEAM_NAME_PATH) == DESCRIPTION


@pytest.mark.parametrize(
    "transfer_syntax, data_set",
    [(EXPLICIT, _explicit_data_set()), (IMPLICIT, _implicit_data_set())],
    ids=["explicit-vr", "implicit-vr"],
)
def test_evidence_counts_the_items_of_each_value_that_holds_them(
    transfer_syntax, data_set
):
    evidence = source.read_source(_file(transfer_syntax, data_set))

    counts = {path: evidence.element(path).items for path in evidence.paths()}

    assert counts[_path("(300A,00B0)")] == 2
    assert counts[_path("(0044,0110)")] == 1
    assert counts[NAME_PATH] is None


def test_a_sequence_of_undefined_length_has_no_single_value_field():
    evidence = source.read_source(_file(EXPLICIT, _explicit_data_set()))

    with pytest.raises(ValueError, match="undefined length"):
        evidence.value_field(_path("(300A,00B0)"))


@pytest.mark.parametrize("data_set, stop", MALFORMED.values(), ids=MALFORMED)
def test_a_malformed_structure_is_refused(data_set, stop):
    with pytest.raises(source.SourceRefused) as raised:
        source.read_source(_file(EXPLICIT, data_set))

    assert raised.value.reason is source.SourceReason.STRUCTURE
    assert raised.value.offset == stop


def test_a_file_that_ends_inside_a_sequence_is_refused_at_its_end():
    # Without its sequence delimiter, the file ends inside Beam Sequence.
    data = _file(EXPLICIT, _explicit_data_set()[:-24])

    with pytest.raises(source.SourceRefused) as raised:
        source.read_source(data)

    assert raised.value.reason is source.SourceReason.STRUCTURE
    assert raised.value.offset == len(data)


@pytest.mark.parametrize(
    "appended",
    [b"\x00\x00", b"\xfe\xff\x00\xe0\x00\x00\x00\x00", NAME],
    ids=["zeros", "an-item", "text"],
)
def test_bytes_after_the_last_element_are_refused(appended):
    data = _file(EXPLICIT, _explicit_data_set()[:-16] + appended)

    with pytest.raises(source.SourceRefused) as raised:
        source.read_source(data)

    assert raised.value.reason is source.SourceReason.STRUCTURE


def test_nesting_deeper_than_the_limit_is_refused():
    nested = _explicit(BEAM_NAME, "LO", DESCRIPTION)
    for _ in range(file_layout.MAX_NESTING + 1):
        nested = _explicit(BEAM_SEQUENCE, "SQ", _item(nested))

    with pytest.raises(source.SourceRefused) as raised:
        source.read_source(_file(EXPLICIT, nested))

    assert raised.value.reason is source.SourceReason.STRUCTURE


@pytest.mark.parametrize(
    "data, reason",
    [
        (bytes(132), source.SourceReason.NOT_PS3_10),
        (
            _file("1.2.840.10008.1.2.2", _explicit(0x00100010, "PN", NAME)),
            source.SourceReason.TRANSFER_SYNTAX,
        ),
        (
            _file("1.2.840.10008.1.2.5", _explicit(0x00100010, "PN", NAME)),
            source.SourceReason.TRANSFER_SYNTAX,
        ),
        (
            _file("1.2.840.10008.1.2.1.99", _explicit(0x00100010, "PN", NAME)),
            source.SourceReason.TRANSFER_SYNTAX,
        ),
    ],
    ids=["no-dicm", "big-endian", "rle", "deflated"],
)
def test_a_file_outside_the_supported_encodings_is_refused(data, reason):
    with pytest.raises(source.SourceRefused) as raised:
        source.read_source(data)

    assert raised.value.reason is reason


def test_evidence_does_not_change_with_its_input_or_its_data_sets():
    data = bytearray(_file(EXPLICIT, _explicit_data_set()))
    evidence = source.read_source(data)
    data[:] = bytes(len(data))

    first = evidence.dataset()
    first.PatientName = "CHANGED^NAME"
    del first[BEAM_SEQUENCE]
    second = evidence.dataset()

    assert evidence.value_field(NAME_PATH) == NAME
    assert second is not first
    assert isinstance(second.get_item(0x00100010), pydicom.dataelem.RawDataElement)
    assert BEAM_SEQUENCE in second
    assert isinstance(evidence.value_field(NAME_PATH), bytes)


def test_messages_and_reprs_hold_no_value():
    evidence = source.read_source(_file(EXPLICIT, _explicit_data_set()))
    with pytest.raises(source.SourceRefused) as raised:
        source.read_source(_file(EXPLICIT, _explicit(0x00100010, "PN", NAME) * 2))

    shown = [
        repr(evidence),
        str(evidence),
        repr(evidence.element(NAME_PATH)),
        str(raised.value),
        repr(raised.value),
    ]

    assert not any("SENTINEL" in each for each in shown)
    assert "elements=9" in repr(evidence)


def _read(dataset, path, evidence, codecs=elements.DEFAULT_CODECS):
    """Read through each sequence on ``path`` with the source evidence."""
    ancestors = ()
    for depth, (tag, index) in enumerate(path.items):
        sequence = elements.read_element(
            dataset,
            ElementPath(path.items[:depth], tag),
            codecs,
            ancestors,
            source=evidence,
        )
        ancestors = (dataset, *ancestors)
        dataset = sequence.items[index]
    return elements.read_element(dataset, path, codecs, ancestors, source=evidence)


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "transfer_syntax, data_set",
    [(EXPLICIT, _explicit_data_set()), (IMPLICIT, _implicit_data_set())],
    ids=["explicit-vr", "implicit-vr"],
)
def test_elements_read_against_their_source(transfer_syntax, data_set):
    evidence = source.read_source(_file(transfer_syntax, data_set))
    dataset = evidence.dataset()

    assert _read(dataset, NAME_PATH, evidence).values == ("SENTINEL^NAME",)
    assert _read(dataset, BEAM_NAME_PATH, evidence).values == ("SENTINEL BEAM",)
    assert _read(dataset, ASSERTION_UID_PATH, evidence).values == ("2.25.4401",)


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "access",
    [
        lambda dataset: dataset.PatientName,
        lambda dataset: dataset.get(0x00100010),
        list,
        lambda dataset: dataset == dataset.copy(),
    ],
    ids=["attribute", "get", "iteration", "equality"],
)
def test_an_element_that_pydicom_decoded_is_read_from_its_source_bytes(access):
    # Without its source, an element that pydicom has decoded in place is
    # refused; with it, the value is decoded from the source's bytes.
    evidence = source.read_source(_file(EXPLICIT, _explicit_data_set()))
    dataset = evidence.dataset()
    access(dataset)

    with pytest.raises(elements.UndecodableElement, match="decoded by pydicom"):
        elements.read_element(dataset, NAME_PATH, elements.DEFAULT_CODECS)
    read = elements.read_element(
        dataset, NAME_PATH, elements.DEFAULT_CODECS, source=evidence
    )

    assert (read.vr, read.values) == ("PN", ("SENTINEL^NAME",))


@pytest.mark.parametrize(
    "replacement",
    [
        # Other bytes, as from another file.
        lambda: pydicom.dataelem.RawDataElement(
            pydicom.tag.Tag(0x00100010), "PN", 14, b"SENTINEL^OTHER", 0, False, True
        ),
        # The same bytes with another VR.
        lambda: pydicom.dataelem.RawDataElement(
            pydicom.tag.Tag(0x00100010), "LO", len(NAME), NAME, 0, False, True
        ),
        # A value set in memory.
        lambda: pydicom.DataElement(0x00100010, "PN", "SENTINEL^MEMORY"),
    ],
    ids=["other-bytes", "other-vr", "in-memory"],
)
def test_an_element_that_does_not_match_its_source_is_refused(replacement):
    evidence = source.read_source(_file(EXPLICIT, _explicit_data_set()))
    dataset = evidence.dataset()
    dataset[0x00100010] = replacement()

    with pytest.raises(elements.UndecodableElement) as raised:
        elements.read_element(
            dataset, NAME_PATH, elements.DEFAULT_CODECS, source=evidence
        )

    assert raised.value.reason == "does not match its source"
    assert "SENTINEL" not in str(raised.value)


@pytest.mark.parametrize(
    "tag, replacement",
    [
        # A sequence of defined length where the source's is undefined.
        (
            0x300A00B0,
            lambda: pydicom.dataelem.RawDataElement(
                pydicom.tag.Tag(0x300A00B0), "SQ", 0, b"", 0, False, True
            ),
        ),
        # A Specific Character Set set in memory, which dcmread would have
        # decoded from the file.
        (0x00080005, lambda: pydicom.DataElement(0x00080005, "CS", "ISO_IR 100")),
    ],
    ids=["sequence-length", "character-set"],
)
def test_a_structure_that_does_not_match_its_source_is_refused(tag, replacement):
    data_set = _explicit(0x00080005, "CS", b"ISO_IR 6") + _explicit_data_set()
    evidence = source.read_source(_file(EXPLICIT, data_set))
    dataset = evidence.dataset()
    dataset[tag] = replacement()
    path = _path(f"({tag >> 16:04X},{tag & 0xFFFF:04X})")

    with pytest.raises(elements.UndecodableElement, match="does not match"):
        elements.read_element(dataset, path, elements.DEFAULT_CODECS, source=evidence)


def _without_the_first_item(dataset):
    del dataset[BEAM_SEQUENCE].value[0]


def _with_another_item(dataset):
    dataset[BEAM_SEQUENCE].value.append(pydicom.Dataset())


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "transfer_syntax, data_set",
    [(EXPLICIT, _explicit_data_set()), (IMPLICIT, _implicit_data_set())],
    ids=["undefined-length", "defined-length"],
)
@pytest.mark.parametrize(
    "change", [_without_the_first_item, _with_another_item], ids=["fewer", "more"]
)
def test_a_sequence_with_other_items_than_its_source_is_refused(
    transfer_syntax, data_set, change
):
    evidence = source.read_source(_file(transfer_syntax, data_set))
    dataset = evidence.dataset()
    change(dataset)

    with pytest.raises(elements.UndecodableElement, match="does not match"):
        elements.read_element(
            dataset, _path("(300A,00B0)"), elements.DEFAULT_CODECS, source=evidence
        )


def _with_character_set(term):
    return _explicit(0x00080005, "CS", term) + _explicit_data_set()


def _set_latin_1(dataset):
    dataset.SpecificCharacterSet = "ISO_IR 100"


def _delete_character_set(dataset):
    del dataset.SpecificCharacterSet


@pytest.mark.parametrize(
    "data_set, change, reason",
    [
        (_explicit_data_set(), _set_latin_1, "does not match"),
        (_with_character_set(b"ISO_IR 144"), _set_latin_1, None),
        (_with_character_set(b"ISO_IR 144"), _delete_character_set, "does not match"),
    ],
    ids=["added", "changed", "deleted"],
)
def test_the_character_set_of_source_text_is_the_sources(data_set, change, reason):
    # Text is decoded from the source's bytes, so in the character set the
    # source declares, whatever the data set now holds.
    evidence = source.read_source(_file(EXPLICIT, data_set))
    dataset = evidence.dataset()
    elements.dataset_codecs(dataset, source=evidence)
    change(dataset)

    if reason is None:
        codecs = elements.dataset_codecs(dataset, source=evidence)
        assert codecs == (pydicom.charset.python_encoding["ISO_IR 144"],)
    else:
        with pytest.raises(elements.UndecodableElement, match=reason):
            elements.dataset_codecs(dataset, source=evidence)


def test_an_element_absent_from_its_source_is_refused():
    evidence = source.read_source(_file(EXPLICIT, _explicit_data_set()))
    dataset = evidence.dataset()
    dataset.add_new(0x00100020, "LO", "SENTINEL")

    with pytest.raises(elements.UndecodableElement, match="is not in its source"):
        elements.read_element(
            dataset, _path("(0010,0020)"), elements.DEFAULT_CODECS, source=evidence
        )


def test_reading_the_source_logs_no_value(caplog):
    pydicom.config.debug(True)
    try:
        with caplog.at_level(logging.DEBUG):
            evidence = source.read_source(_file(EXPLICIT, _explicit_data_set()))
            evidence.dataset()
    finally:
        pydicom.config.debug(False)

    assert "SENTINEL" not in caplog.text


def test_value_fields_are_the_bytes_the_layout_gives():
    data = _file(EXPLICIT, _explicit_data_set())
    layout = file_layout.read_file_layout(data)
    evidence = source.read_source(data)

    for span in layout.spans:
        location = span.location
        if (
            span.value_start is not None
            and location.region is file_layout.Region.DATA_SET
            and location.item is None
        ):
            assert evidence.value_field(location.element) == bytes(
                data[span.value_start : span.end]
            )


def test_a_value_that_only_starts_like_items_is_one_element():
    # A private UN value whose first bytes look like an item, but which does
    # not read as items to its end, is one value with no elements inside.
    looks_like_items = _item(_implicit(0x00091010, b"AB")) + b"\x01\x02"
    data = _file(
        EXPLICIT,
        _explicit(0x00090010, "LO", b"SYNTHETIC ")
        + _explicit(0x00091001, "UN", looks_like_items),
    )

    evidence = source.read_source(data)

    assert list(evidence.paths()) == [_path("(0009,0010)"), _path("(0009,1001)")]
    assert evidence.value_field(_path("(0009,1001)")) == looks_like_items
