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

"""A sequence's items, decoded only once they are shown to fill its value.

Every value is encoded here by hand, little endian (PS3.5 Sections 7.1 and
7.5). Values that must never appear in a message carry the text
``SENTINEL``.
"""

import ast
import logging
import pathlib
import struct
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import sequences

pytestmark = pytest.mark.pydicom

UNDEFINED = 0xFFFFFFFF
ITEM, ITEM_END, SEQUENCE_END = 0xFFFEE000, 0xFFFEE00D, 0xFFFEE0DD
REFERENCED_STUDY = 0x00081110  # Referenced Study Sequence, VR SQ
REFERENCED_INSTANCE = 0x00081155  # Referenced SOP Instance UID, VR UI
UID = b"2.25.1"


def _implicit(tag, value=b"", length=None):
    """An implicit VR element, or an item or delimiter (PS3.5 Table 7.1-3)."""
    length = len(value) if length is None else length
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, length) + value


def _explicit(tag, vr, value):
    """An explicit VR element with a 16-bit length (PS3.5 Table 7.1-2)."""
    group, element = divmod(tag, 0x10000)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _undefined_item(content):
    """An item of undefined length, ended by its delimiter (PS3.5 Section 7.5)."""
    return _implicit(ITEM, content, UNDEFINED) + _implicit(ITEM_END)


@pytest.mark.parametrize(
    "value, explicit",
    [
        (_implicit(ITEM, _implicit(REFERENCED_INSTANCE, UID)), False),
        (_implicit(ITEM, _explicit(REFERENCED_INSTANCE, "UI", UID)), True),
        (_undefined_item(_implicit(REFERENCED_INSTANCE, UID)), False),
    ],
    ids=["implicit-vr", "explicit-vr", "undefined-length"],
)
def test_items_are_decoded(value, explicit):
    decoded = sequences.decode_items(value, explicit=explicit)

    assert isinstance(decoded, pydicom.Sequence)
    assert [item[REFERENCED_INSTANCE].value for item in decoded] == ["2.25.1"]


@pytest.mark.parametrize("undefined", [False, True], ids=["defined", "undefined"])
def test_a_sequence_nested_in_an_item_is_decoded(undefined):
    inner = _implicit(ITEM, _implicit(REFERENCED_INSTANCE, UID))
    if undefined:
        nested = _implicit(REFERENCED_STUDY, inner + _implicit(SEQUENCE_END), UNDEFINED)
    else:
        nested = _implicit(REFERENCED_STUDY, inner)
    value = _implicit(ITEM, nested) + _undefined_item(b"")

    decoded = sequences.decode_items(value, explicit=False)

    assert len(decoded) == 2
    (study,) = decoded[0][REFERENCED_STUDY].value
    assert study[REFERENCED_INSTANCE].value == "2.25.1"


def test_an_empty_value_has_no_items():
    decoded = sequences.decode_items(b"", explicit=False)

    assert isinstance(decoded, pydicom.Sequence)
    assert not decoded


@pytest.mark.parametrize("own", [False, True], ids=["inherited", "its-own"])
def test_an_item_is_decoded_in_its_own_character_set_or_the_one_it_inherits(own):
    # PS3.5 Section 7.5.3: the Specific Character Set of the data set that
    # holds a sequence applies to its items, unless an item has its own.
    name = _implicit(0x00100010, "Žák^Ō".encode())
    if own:
        item = _implicit(0x00080005, b"ISO_IR 192") + name
        codecs = ()
    else:
        item, codecs = name, ("UTF8",)

    (decoded,) = sequences.decode_items(
        _implicit(ITEM, item), explicit=False, codecs=codecs
    )

    assert str(decoded.PatientName) == "Žák^Ō"


MALFORMED = {
    "element-where-an-item-belongs": _implicit(REFERENCED_INSTANCE, b"SENTINEL"),
    "item-past-value": _implicit(ITEM, _implicit(REFERENCED_INSTANCE, b"SENTINEL"), 64),
    "element-past-item": _implicit(
        ITEM, _implicit(REFERENCED_INSTANCE, b"SENTINEL", 16)
    ),
    "tags-out-of-order": _implicit(
        ITEM,
        _implicit(REFERENCED_INSTANCE, b"SENTINEL")
        + _implicit(0x00080016, b"SENTINEL"),
    ),
    "bytes-after-the-last-item": _implicit(ITEM, b"") + b"SENTINEL",
    "item-without-its-delimiter": _implicit(
        ITEM, _implicit(REFERENCED_INSTANCE, b"SENTINEL"), UNDEFINED
    ),
    "nested-item-past-its-sequence": _implicit(
        ITEM,
        _implicit(
            REFERENCED_STUDY,
            _implicit(ITEM, _implicit(REFERENCED_INSTANCE, b"SENTINEL"), 64),
        ),
    ),
}


@pytest.mark.parametrize("value", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_value_that_is_not_only_items_is_refused(value):
    with pytest.raises(sequences.UnreadableItems) as raised:
        sequences.decode_items(value, explicit=False)

    assert str(raised.value) == "the value is not a sequence's items"
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert "SENTINEL" not in repr(raised.value)


def test_a_value_that_pydicom_cannot_decode_is_refused_without_its_error(
    monkeypatch,
):
    def refuse(*_):
        raise ValueError("SENTINEL")

    monkeypatch.setattr(pydicom.values, "convert_SQ", refuse)

    with pytest.raises(sequences.UnreadableItems) as raised:
        sequences.decode_items(_implicit(ITEM, b""), explicit=False)

    assert str(raised.value) == "the value is not a sequence's items"
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_a_nested_sequence_of_defined_length_can_be_left_for_its_own_decoding():
    # The nested sequence's item runs past it; pydicom decodes the nested
    # sequence only when it is accessed.
    value = MALFORMED["nested-item-past-its-sequence"]

    (item,) = sequences.decode_items(value, explicit=False, nested=False)

    assert isinstance(item.get_item(REFERENCED_STUDY).value, bytes)
    with pytest.raises(sequences.UnreadableItems):
        sequences.decode_items(item.get_item(REFERENCED_STUDY).value, explicit=False)


def test_a_nested_sequence_of_undefined_length_is_read_either_way():
    # pydicom decodes it with the value that holds it.
    inner = _implicit(ITEM, _implicit(REFERENCED_INSTANCE, b"SENTINEL"), 64)
    nested = _implicit(REFERENCED_STUDY, inner + _implicit(SEQUENCE_END), UNDEFINED)

    with pytest.raises(sequences.UnreadableItems):
        sequences.decode_items(_implicit(ITEM, nested), explicit=False, nested=False)


def test_big_endian_items_are_refused():
    # PS3.5 Section A.3; the structure of the value is read little endian.
    value = struct.pack(">HHI", 0xFFFE, 0xE000, 8) + struct.pack(
        ">HH2sH", 8, 0x18, b"UI", 0
    )

    with pytest.raises(sequences.UnreadableItems):
        sequences.decode_items(value, explicit=True, little_endian=False)


def test_pydicom_diagnostics_while_decoding_are_redacted(monkeypatch, caplog):
    # A caller that has no redaction of its own, such as the first pass's
    # reference records, still gets none of pydicom's text.
    sentinel = "ZZSENTINELZZ"
    convert = pydicom.values.convert_SQ

    def convert_and_warn(*args, **kwargs):
        pydicom.misc.warn_and_log(f"bad value {sentinel}")
        return convert(*args, **kwargs)

    monkeypatch.setattr(pydicom.values, "convert_SQ", convert_and_warn)
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        decoded = sequences.decode_items(
            _implicit(ITEM, _implicit(REFERENCED_INSTANCE, UID)), explicit=False
        )
    assert len(decoded) == 1
    assert caught and caplog.records
    assert sentinel not in " ".join(str(each.message) for each in caught)
    assert sentinel not in caplog.text


def _sequence_decoders(source: str) -> list[tuple[str, str]]:
    """Return each call in a module's source that may have pydicom decode items.

    Each is given by the function it is in and the call, with the VR it
    passes to ``convert_value``: a VR that is not a constant may be SQ.
    """
    found = []

    def visit(node: ast.AST, function: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = node.name
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", None))
            if name in ("convert_SQ", "read_sequence", "read_sequence_item"):
                found.append((function, name))
            elif name == "convert_value" and (
                not node.args
                or not isinstance(node.args[0], ast.Constant)
                or node.args[0].value == "SQ"
            ):
                vr = ast.unparse(node.args[0]) if node.args else ""
                found.append((function, f"convert_value({vr})"))
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(ast.parse(source), "")
    return found


# The calls outside this module that may be given VR SQ. Each decodes SQ by
# decode_items first, so the VR it is given is another.
_REVIEWED_DECODERS = {
    "sequences.py": [("decode_items", "convert_SQ")],
    "elements.py": [
        ("_decoded", "convert_value(vr)"),
        ("_written_back", "convert_value(vr)"),
    ],
}


def _engine_sources() -> dict[str, str]:
    package = pathlib.Path(sequences.__file__).parent
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    }


def test_only_this_module_has_pydicom_decode_items():
    # A caller that decoded items itself would skip the check that they fill
    # the value, which pydicom does not make.
    decoders = {
        name: calls
        for name, source in _engine_sources().items()
        if (calls := _sequence_decoders(source))
    }
    assert decoders == _REVIEWED_DECODERS


@pytest.mark.parametrize("module", ["elements.py", "references.py"])
@pytest.mark.parametrize(
    "call",
    [
        "pydicom.values.convert_value('SQ', value)",
        "pydicom.values.convert_value(vr, value)",
        "pydicom.values.convert_SQ(value, True, True)",
    ],
)
def test_a_new_decoder_of_items_is_found(module, call):
    source = (
        _engine_sources()[module] + f"\n\ndef _added(value, vr):\n    return {call}\n"
    )
    assert _sequence_decoders(source) != _REVIEWED_DECODERS.get(module, [])
