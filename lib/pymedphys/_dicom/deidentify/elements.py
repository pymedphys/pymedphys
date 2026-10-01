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

"""Read each element with the pinned data dictionary, and build those written.

:func:`read_element` decodes an element with the VR that the pinned PS3.6
data dictionary gives its attribute, and raises :class:`UndecodableElement`
for anything it cannot decode exactly. UN is decoded as Implicit VR Little
Endian (PS3.5 Section 6.2.2), including a sequence that pydicom does not
know, such as RT Assertions Sequence (0044,0110), once
:func:`.file_layout.reads_as_items` finds that items fill it: pydicom reads
malformed items silently. A VR in the file must be one the dictionary gives,
and not contradict the one that the standard decides of alternatives. US or
SS follows Pixel Representation (0028,0103) in the nearest data set that has
it (PS3.3 Sections C.7.5.1, C.7.6.3, and C.11.1.1.1), but for LUT Descriptor
(0028,3002) in VOI LUT Sequence (0028,3010), the input to the VOI LUT
decides it (PS3.3 Section C.11.2.1.1): Pixel Representation without a
Modality LUT or rescale, US after a Modality LUT, and after rescale SS where
the rescaled range can be negative, as Hounsfield Units always can, and US
otherwise. There, in explicit VR, either applies, since the standard has the
VR follow what the second value needs. Real World Value First Value Mapped
(0040,9216) and Last Value Mapped (0040,9211) are SS for floating point
pixel data (PS3.3 Section C.7.6.16.2.11.1.1), which the first supported
release's IODs do not have, so without a VR in the file they are refused
where Pixel Representation is absent. Without a VR in the file, OB or OW,
and US or OW, are OW, as PS3.5 Section A.1 gives Pixel, Overlay, and
Waveform Data, whose bytes are the same either way; in explicit VR, Pixel
Data is OB if encapsulated (Section A.4) and OW where Bits Allocated
(0028,0100) is more than 8 (Section A.2). Text is decoded in the Specific
Character Set (0008,0005) of the data set, or of the item that has its own
(PS3.5 Section 7.5.3). Where that is the Default Character Repertoire alone,
which pydicom reads as ISO 8859-1, text must be in ISO 646 (PS3.5 Section
6.1.2.1). ``ISO_IR 6`` names that repertoire as the absence of a value does:
PS3.3 Section C.12.1.1.2 does not list it among the Defined Terms, but real
data commonly holds it.

:func:`new_element` builds an element to write with pydicom's checks off,
once :func:`written_value_problem` has checked its values.

pydicom's warnings and log records are redacted by
:func:`pymedphys._dicom.anonymise.diagnostics.redacted_pydicom_diagnostics`,
which ignores its warnings for the rest of the process, and its exceptions,
whose messages can quote values, are replaced, not chained. This module
neither walks a data set nor applies an action.
"""

from __future__ import annotations

import dataclasses
import decimal
import functools
from collections.abc import Sequence
from typing import cast

from pymedphys._imports import pydicom

from pymedphys._dicom.anonymise.diagnostics import redacted_pydicom_diagnostics

from .file_layout import ElementPath, reads_as_items
from .sop_classes import load_storage_sop_classes
from .standard import VRS, DictionaryAttribute, load_data_dictionary
from .uids import normalise_uid
from .values import values_problem

# The codecs of the Default Character Repertoire, as pydicom names them.
DEFAULT_CODECS = ("iso8859",)
# Not a Defined Term, but it names the Default Character Repertoire.
_DEFAULT_TERM = "ISO_IR 6"
_UNDEFINED = 0xFFFFFFFF
_CHARACTER_SET = "(0008,0005)"
# The Defined Terms of PS3.3 Tables C.12-2 to C.12-5 that pydicom 3.0 can
# decode, which leaves out ISO_IR 203 and ISO 2022 IR 203.
_SINGLE_BYTE = tuple("13 100 101 109 110 126 127 138 144 148 166".split())
_WITHOUT_EXTENSIONS = {"ISO_IR 192": "UTF8", "GB18030": "GB18030", "GBK": "GBK"}
_TERMS = frozenset(
    {*(f"ISO_IR {n}" for n in _SINGLE_BYTE), *_WITHOUT_EXTENSIONS}
    | {f"ISO 2022 IR {n}" for n in ("6", *_SINGLE_BYTE, "87", "149", "159", "58")}
)
# The codecs that can take more than one byte for a character.
_MULTI_BYTE = frozenset(
    {*_WITHOUT_EXTENSIONS.values(), "iso2022_jp", "iso2022_jp_2", "euc_kr", "iso_ir_58"}
)
# The code points of a person name's first component group where Value 1 of
# Specific Character Set is UTF-8, GB18030, or GBK (PS3.5 Section 6.2.1.2).
_FIRST_GROUP = (
    (0x20, 0x1FFF), (0x3001, 0x3002), (0x300C, 0x300D), (0x3099, 0x309C),
    (0x30A0, 0x30FF),
)  # fmt: skip
_CHARACTER_SET_VRS = frozenset({"LO", "LT", "PN", "SH", "ST", "UC", "UT"})
_SOP_CLASS_UID = "(0008,0016)"
_BITS_STORED = "(0028,0101)"
_PIXEL_REPRESENTATION = "(0028,0103)"
_SIGNEDNESS = {0: "US", 1: "SS"}
_LUT_DESCRIPTOR = "(0028,3002)"
_VOI_LUT_SEQUENCE = "(0028,3010)"
_MODALITY_LUT_SEQUENCE = "(0028,3000)"
_RESCALE_INTERCEPT = "(0028,1052)"
_RESCALE_SLOPE = "(0028,1053)"
_RESCALE_TYPE = "(0028,1054)"
# What a VOI LUT's input comes from, if not the stored values.
_VOI_LUT_INPUT = (_MODALITY_LUT_SEQUENCE, _RESCALE_INTERCEPT, _RESCALE_SLOPE)
# Shared and Per-Frame Functional Groups Sequence.
_FUNCTIONAL_GROUPS = ("(5200,9229)", "(5200,9230)")
# The type that pydicom decodes each value of a binary VR as.
_BINARY_TYPES: dict[str, type] = {
    **dict.fromkeys(("OB", "OD", "OF", "OL", "OV", "OW", "UN"), bytes),
    **dict.fromkeys(("AT", "SL", "SS", "SV", "UL", "US", "UV"), int),
    **dict.fromkeys(("FD", "FL"), float),
}


class UndecodableElement(Exception):
    """An element that cannot be decoded exactly, or whose VR is in doubt.

    Not a :class:`ValueError`, which code that rejects invalid input could
    catch by accident. ``reason`` says what is wrong without quoting a value.
    """

    def __init__(self, path: ElementPath, reason: str) -> None:
        super().__init__(path, reason)
        self.path = path
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.path} {self.reason}"


@dataclasses.dataclass(frozen=True, repr=False)
class ElementValue:
    """An element as the rules act on it. Its ``repr`` shows only path and VR.

    Attributes
    ----------
    path : ElementPath
    vr : str
        The one VR that applies to the element in its data set.
    values : tuple of str, int, float, or bytes
        As :func:`.values.values_problem` takes them, or ``()`` if empty or a
        sequence: PN, DS, IS, DA, DT, and TM as text, and bytes as one value.
    items : tuple of pydicom.Dataset
        A sequence's items, whose elements are decoded only when read.
    codecs : tuple of str
        The codecs, as pydicom names them, of the data set's character set.
    """

    path: ElementPath
    vr: str
    values: tuple[str | int | float | bytes, ...] = ()
    items: tuple[pydicom.Dataset, ...] = ()
    codecs: tuple[str, ...] = DEFAULT_CODECS

    def __repr__(self) -> str:
        return f"ElementValue(path={str(self.path)!r}, vr={self.vr!r})"


@functools.cache
def _dictionary() -> tuple[dict, list[DictionaryAttribute]]:
    attributes = load_data_dictionary().attributes
    masked = [each for each in attributes if "x" in each.tag]
    return {each.tag: each for each in attributes if "x" not in each.tag}, masked


def dictionary_attribute(tag: str) -> DictionaryAttribute | None:
    """Return the pinned dictionary's attribute for a tag such as ``"(6002,3000)"``.

    An "x" in the dictionary's tags stands for any digit, but in (50xx,eeee)
    and (60xx,eeee) only for the groups that repeat, 5000 to 501E and 6000 to
    601E (PS3.5 Section 7.6). An odd group is private, so it has none.

    >>> dictionary_attribute("(6002,3000)").keyword
    'OverlayData'
    >>> dictionary_attribute("(6020,3000)") is None
    True
    """
    exact, masked = _dictionary()
    if tag in exact or int(tag[4], 16) % 2:
        return exact.get(tag)
    return next(
        (
            each
            for each in masked
            if all(digit in ("x", found) for digit, found in zip(each.tag, tag))
            and (each.tag[1:3] not in ("50", "60") or tag[3] in "01")
        ),
        None,
    )


def dataset_codecs(
    dataset: pydicom.Dataset,
    inherited: tuple[str, ...] = DEFAULT_CODECS,
    items: tuple[tuple[str, int], ...] = (),
) -> tuple[str, ...]:
    """Return the codecs, as pydicom names them, of a data set's text.

    ``inherited`` are those of the data set that holds it, which apply unless
    it has its own Specific Character Set (0008,0005) (PS3.5 Section 7.5.3),
    and ``items`` the items that hold it, as in :class:`ElementPath`. It
    raises :class:`UndecodableElement` unless each value is a Defined Term of
    PS3.3 Section C.12.1.1.2 that pydicom can decode, or the only value is
    ``ISO_IR 6``, which gives the Default Character Repertoire as an absent
    value does; only the first is empty; and several all use ISO 2022 code
    extensions.

    >>> item = pydicom.Dataset()
    >>> item.SpecificCharacterSet = ["", "ISO 2022 IR 87"]
    >>> dataset_codecs(item)
    ('iso8859', 'iso2022_jp')
    """
    if _number(_CHARACTER_SET) not in dataset:
        return tuple(inherited)
    path = ElementPath(items, _CHARACTER_SET)
    values = read_element(dataset, path, DEFAULT_CODECS).values
    terms = [str(value).strip(" ") for value in values] or [""]
    single = len(terms) == 1
    if not all(
        (term == "" and index == 0)
        or (term == _DEFAULT_TERM and single)
        or (term in _TERMS and (single or term.startswith("ISO 2022")))
        for index, term in enumerate(terms)
    ):
        raise UndecodableElement(path, "is not a supported Specific Character Set")
    return tuple(pydicom.charset.python_encoding[term] for term in terms)


def read_element(
    dataset: pydicom.Dataset,
    path: ElementPath,
    codecs: Sequence[str],
    ancestors: Sequence[pydicom.Dataset] = (),
) -> ElementValue:
    """Decode the element at ``path`` in ``dataset``, which is not changed.

    ``codecs`` are the data set's, from :func:`dataset_codecs`, and
    ``ancestors`` the data sets that hold it, nearest first, up to the
    instance's. It raises :class:`UndecodableElement` if the value is
    deferred or shorter than its length, its VR is not one the pinned
    dictionary gives, contradicts the one the standard decides, or is in
    doubt, or it does not decode exactly as its VR and character set; the
    Default Character Repertoire alone holds only ISO 646.

    The data sets must hold each element read from a file as
    :func:`pydicom.dcmread` returned it, or as built in memory with its VR.
    Accessing an element read from a file through pydicom, by indexing,
    attribute, ``get``, or iteration, decodes it in place: pydicom then
    holds no encoded value to check, and has chosen any VR in doubt itself,
    reading a sequence of VR UN without checking its items. Such an element
    raises :class:`UndecodableElement`, except Specific Character Set
    (0008,0005), which dcmread decodes itself, and a sequence of undefined
    length, which it reads as items.
    """
    with redacted_pydicom_diagnostics():
        element = dataset.get_item(_number(path.tag), keep_deferred=True)
        if element is None:
            raise KeyError(str(path))
        if _decoded_by_pydicom(element, path.tag):
            raise UndecodableElement(
                path,
                "was decoded by pydicom before it was read here, so its encoded "
                "value cannot be checked",
            )
        if isinstance(element, pydicom.dataelem.RawDataElement):
            undefined = element.length == _UNDEFINED
        else:
            undefined = element.is_undefined_length
        stated = str(element.VR) if element.VR in VRS - {"UN"} else None
        vr = _applicable_vr(path, stated, undefined, (dataset, *ancestors))
        value = _decoded(element, vr, list(codecs), path)
        if vr == "SQ":
            items = tuple(cast(Sequence[pydicom.Dataset], value))
            return ElementValue(path, vr, (), items, tuple(codecs))
        values: Sequence[object] = [value]
        if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
            values = value
        elif value is None or value in ("", b""):
            values = []
        plain = tuple(_plain(path, vr, each) for each in values)
        # pydicom reads the Default Character Repertoire as ISO 8859-1, but it
        # is ISO 646 (PS3.5 Section 6.1.2.1).
        if (
            vr in _CHARACTER_SET_VRS
            and tuple(codecs) == DEFAULT_CODECS
            and not all(str(each).isascii() for each in plain)
        ):
            raise UndecodableElement(
                path,
                f"could not be decoded as VR {vr} in the Default Character "
                "Repertoire, ISO 646",
            )
    return ElementValue(path, vr, plain, (), tuple(codecs))


def _number(tag: str) -> int:
    return int(tag[1:5] + tag[6:10], 16)


def _decoded_by_pydicom(element: object, tag: str) -> bool:
    """Return whether pydicom has decoded an element read from a file."""
    # pydicom records where in the file it read the value of each element it
    # decodes from one, and of no element built in memory.
    return (
        isinstance(element, pydicom.DataElement)
        and element.file_tell is not None
        and tag != _CHARACTER_SET
        and not (element.VR == "SQ" and element.is_undefined_length)
    )


def _applicable_vr(
    path: ElementPath, stated: str | None, undefined: bool, chain: tuple
) -> str:
    """Return the one VR that applies, from the file's VR and the dictionary's."""
    attribute = dictionary_attribute(path.tag)
    if attribute is None or not attribute.vrs:
        return stated or "UN"
    alternatives = attribute.vrs
    if stated is not None and stated not in alternatives:
        raise UndecodableElement(
            path, f"has VR {stated}, which the pinned data dictionary does not give it"
        )
    if len(alternatives) == 1:
        return alternatives[0]
    decided, rule = _decided_vr(path, alternatives, stated, undefined, chain)
    if stated is not None and decided not in (None, stated):
        raise UndecodableElement(
            path, f"has VR {stated}, but {rule} decides VR {decided}"
        )
    applicable = stated or decided
    if applicable is None:
        raise UndecodableElement(
            path,
            f"has VR {attribute.vr}, and nothing in the data sets that hold it "
            f"decides which, as {rule} would",
        )
    return applicable


def _decided_vr(
    path: ElementPath,
    alternatives: tuple[str, ...],
    stated: str | None,
    undefined: bool,
    chain: tuple,
) -> tuple[str | None, str]:
    """Return the VR the standard decides of alternatives, if any, and what decides."""
    if alternatives == ("US", "SS"):
        enclosing = path.items[-1][0] if path.items else None
        if path.tag == _LUT_DESCRIPTOR and enclosing == _VOI_LUT_SEQUENCE:
            # In explicit VR, "the explicit VR actually used is dictated by
            # the VR needed to represent the second Value" (PS3.3 Section
            # C.11.2.1.1), so the file's VR applies, whichever it is.
            decided = None if stated else _voi_lut_input_vr(chain)
            return decided, "PS3.3 Section C.11.2.1.1"
        representation = _deciding(chain, _PIXEL_REPRESENTATION)
        return _SIGNEDNESS.get(representation), "Pixel Representation (0028,0103)"
    if stated is None and "OW" in alternatives:
        return "OW", "PS3.5 Section A.1"
    if path.tag == "(7FE0,0010)":
        if undefined:
            return "OB", "encapsulation (PS3.5 Section A.4)"
        bits = _deciding(chain, "(0028,0100)")
        return ("OW" if bits > 8 else None), "Bits Allocated (0028,0100)"
    return None, "the standard"


def _voi_lut_input_vr(chain: tuple) -> str | None:
    """Return the VR of a VOI LUT Descriptor's second value, or None if in doubt.

    PS3.3 Section C.11.2.1.1 gives it as "the same as specified by Pixel
    Representation (0028,0103), if there is no Modality LUT or Rescale Slope
    and Intercept specified; SS if the possible output range after
    application of the Rescale Slope and Intercept may be signed; [and] US
    otherwise". Its Note adds that HU "are always signed", and a CT Image
    leaves Rescale Type (0028,1054) out only where it is HU (PS3.3 Table
    C.8-3). Section C.11.1.1.1 gives the output range of rescale "from
    (minimum pixel value*Rescale Slope+Rescale Intercept) to (maximum pixel
    value*Rescale Slope+Rescale Intercept), where the minimum and maximum
    pixel values are determined by Bits Stored and Pixel Representation",
    and that of a Modality LUT Sequence (0028,3000) as "always unsigned".

    The nearest data set of ``chain`` that has a Modality LUT Sequence,
    Rescale Intercept (0028,1052), or Rescale Slope (0028,1053) gives them.
    A data set with both a Modality LUT and rescale, which PS3.3 Table C.11-1b
    does not allow, or functional groups, where the rescale of each frame is
    in a Functional Group Macro, decides nothing.
    """
    if any(_number(tag) in each for each in chain for tag in _FUNCTIONAL_GROUPS):
        return None
    source = next(
        (each for each in chain if any(_number(tag) in each for tag in _VOI_LUT_INPUT)),
        None,
    )
    if source is None:
        return _SIGNEDNESS.get(_deciding(chain, _PIXEL_REPRESENTATION))
    if _number(_MODALITY_LUT_SEQUENCE) in source:
        rescaled = any(_number(tag) in source for tag in _VOI_LUT_INPUT[1:])
        lut = _single_value(source, _MODALITY_LUT_SEQUENCE)
        return None if rescaled or lut is None else "US"
    return _rescaled_vr(source, chain)


def _rescaled_vr(source: pydicom.Dataset, chain: tuple) -> str | None:
    """Return SS if the output of rescale can be negative, US if not, or None."""
    if _number(_RESCALE_TYPE) in source:
        rescale_type = _single_value(source, _RESCALE_TYPE)
        if rescale_type is None:
            return None
        hounsfield = rescale_type == "HU"
    else:
        hounsfield = _is_ct_image(chain)
    if hounsfield:
        return "SS"
    slope = _decimal(_single_value(source, _RESCALE_SLOPE))
    intercept = _decimal(_single_value(source, _RESCALE_INTERCEPT))
    bits = _deciding(chain, _BITS_STORED)
    representation = _deciding(chain, _PIXEL_REPRESENTATION)
    if slope is None or intercept is None or bits < 1 or representation not in (0, 1):
        return None
    lowest, highest = (
        (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1)
        if representation
        else (0, 2**bits - 1)
    )
    signed = min(lowest * slope, highest * slope) + intercept < 0
    return "SS" if signed else "US"


def _is_ct_image(chain: tuple) -> bool:
    """Return whether the SOP Class of the instance is one of the CT Image IOD."""
    sop_class = next(
        (
            _single_value(each, _SOP_CLASS_UID)
            for each in chain
            if _number(_SOP_CLASS_UID) in each
        ),
        None,
    )
    return isinstance(sop_class, str) and normalise_uid(sop_class) in _ct_image_uids()


@functools.cache
def _ct_image_uids() -> frozenset[str]:
    rows = load_storage_sop_classes().rows
    return frozenset(row.uid for row in rows if row.iod_name == "CT Image")


def _decimal(value: object) -> decimal.Decimal | None:
    """Return a DS value as a finite decimal, or None if it is not one."""
    if not isinstance(value, str):
        return None
    try:
        number = decimal.Decimal(value)
    except decimal.InvalidOperation:
        return None
    return number if number.is_finite() else None


def _single_value(dataset: pydicom.Dataset, tag: str) -> object:
    """Return the one value of ``tag`` in ``dataset``, or None.

    A sequence's one value is its item. The element is decoded in the
    Default Character Repertoire, so text outside it gives None, as does an
    element that is absent, cannot be decoded, or has another number of
    values.
    """
    if _number(tag) not in dataset:
        return None
    try:
        found = read_element(dataset, ElementPath((), tag), DEFAULT_CODECS)
    except UndecodableElement:
        return None
    values = found.items if found.vr == "SQ" else found.values
    if len(values) != 1:
        return None
    return values[0].strip(" ") if isinstance(values[0], str) else values[0]


def _deciding(chain: tuple, tag: str) -> int:
    """Return the one value of ``tag`` in the nearest data set that has it, or -1."""
    for dataset in chain:
        if _number(tag) in dataset:
            value = _single_value(dataset, tag)
            return value if isinstance(value, int) else -1
    return -1


def _decoded(element, vr: str, codecs: list[str], path: ElementPath) -> object:
    """Return pydicom's decoded value, having it decode any bytes as ``vr``."""
    if isinstance(element, pydicom.dataelem.RawDataElement):
        if element.value is None and element.length:
            raise UndecodableElement(path, "has a deferred value; read it in full")
        if element.value is not None and element.length not in (
            len(element.value),
            _UNDEFINED,
        ):
            raise UndecodableElement(path, "has a value shorter than its length")
        raw = element
    elif element.VR == "UN" and isinstance(element.value, bytes):
        raw = pydicom.dataelem.RawDataElement(
            element.tag, "UN", len(element.value), element.value, 0, True, True
        )
    else:
        return element.value
    if raw.VR == "UN":  # in Implicit VR Little Endian (PS3.5 Section 6.2.2)
        raw = raw._replace(is_implicit_VR=True, is_little_endian=True)
    raw = raw._replace(VR=vr)
    explicit = not raw.is_implicit_VR
    if vr == "SQ" and raw.value and not reads_as_items(raw.value, explicit=explicit):
        raise UndecodableElement(path, "has items that cannot be read")
    try:
        return pydicom.values.convert_value(vr, raw, codecs)
    # pydicom raises many types for a malformed value; any means that the
    # value does not decode, and its message can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise UndecodableElement(path, f"could not be decoded as VR {vr}") from None


def _plain(path: ElementPath, vr: str, value: object) -> str | int | float | bytes:
    """Return a decoded value as values_problem takes it, if it is of ``vr``."""
    valuerep = pydicom.valuerep
    kind = _BINARY_TYPES.get(vr)
    if kind is not None:
        if isinstance(value, kind):
            return cast(str | int | float | bytes, kind(value))
    elif (
        isinstance(
            value,
            {
                "DS": (valuerep.DSfloat, valuerep.DSdecimal),
                "IS": (valuerep.IS,),
                "PN": (valuerep.PersonName, str),
            }.get(vr, (str, valuerep.DA, valuerep.DT, valuerep.TM)),
        )
        or value == ""
    ):
        text = str(value)
        # pydicom leaves an escape sequence it does not know, and writes
        # U+FFFD where bytes do not decode in the character set.
        if "\x1b" not in text and "\ufffd" not in text:
            return text
    raise UndecodableElement(path, f"could not be decoded as VR {vr}")


def written_value_problem(
    vr: str, vm: str, values: Sequence[object], codecs: Sequence[str]
) -> str | None:
    """Return what is wrong with values to be written, or None if nothing is.

    That is what :func:`.values.values_problem` finds; else that a text value
    cannot be encoded in the data set's character set, whose ``codecs`` come
    from :func:`dataset_codecs`, where the Default Character Repertoire is ISO
    646 and a single-byte set takes one byte for each character; else that a
    person name's first component group is not in the set of Value 1 alone,
    or, where that is UTF-8, GB18030, or GBK, has a character outside the
    code points PS3.5 Section 6.2.1.2 allows there. It never quotes a value.

    >>> written_value_problem("PN", "1", ["ΩΜΕΓΑ^ΑΛΦΑ"], ("latin_1",))
    "value 1 cannot be encoded in the data set's Specific Character Set"
    >>> written_value_problem("PN", "1", ["ΩΜΕΓΑ^ΑΛΦΑ"], ("UTF8",)) is None
    True
    """
    problem = values_problem(vr, vm, values)
    if problem or vr not in _CHARACTER_SET_VRS:
        return problem
    for number, value in enumerate(values, start=1):
        if not _encodable(str(value), codecs):
            return (
                f"value {number} cannot be encoded in the data set's "
                "Specific Character Set"
            )
        first = str(value).split("=")[0] if vr == "PN" else ""
        if not _encodable(first, codecs[:1]) or (
            codecs[0] in _WITHOUT_EXTENSIONS.values()
            and not all(
                any(low <= ord(char) <= high for low, high in _FIRST_GROUP)
                for char in first
            )
        ):
            return (
                f"value {number} has a character that PS3.5 Section 6.2.1.2 "
                "does not allow in a person name's first component group"
            )
    return None


def _encodable(text: str, codecs: Sequence[str]) -> bool:
    """Return whether each character has a codec that encodes it."""
    # pydicom decodes the Default Character Repertoire as ISO 8859-1, but it
    # is ISO 646 (PS3.5 Section 6.1.2.1).
    names = ["ascii" if codec == "iso8859" else codec for codec in codecs]
    return all(any(_encodes(char, name) for name in names) for char in text)


@functools.lru_cache(maxsize=65536)
def _encodes(char: str, codec: str) -> bool:
    try:
        encoded = char.encode(codec)
    except UnicodeError:
        return False
    return codec in _MULTI_BYTE or len(encoded) == 1


def new_element(
    path: ElementPath, vr: str, values: Sequence[object], codecs: Sequence[str]
) -> pydicom.DataElement:
    """Build an element to write, with pydicom's own checks of its value off.

    ``vr`` is one the pinned dictionary gives the attribute, of alternatives
    the one :func:`read_element` gives; ``values`` are as in
    :class:`ElementValue`, or a sequence's items; and ``codecs`` are those of
    the data set it is written in. It raises :class:`ValueError` without the
    value for any other VR, an item that is not a data set, or a problem that
    :func:`written_value_problem` finds.
    """
    attribute = dictionary_attribute(path.tag)
    if attribute is None or vr not in attribute.vrs:
        raise ValueError(f"{path} does not have VR {vr} in the pinned data dictionary")
    value: object
    if vr == "SQ":
        if not all(isinstance(item, pydicom.Dataset) for item in values):
            raise ValueError(f"{path} needs data sets as its items")
        value = pydicom.Sequence(cast(Sequence[pydicom.Dataset], values))
    elif problem := written_value_problem(vr, attribute.vm, values, codecs):
        raise ValueError(f"{path} {problem}")
    else:
        empty = pydicom.dataelem.empty_value_for_VR(vr)
        value = list(values) if len(values) > 1 else values[0] if values else empty
    with redacted_pydicom_diagnostics():
        return pydicom.DataElement(
            _number(path.tag), vr, value, validation_mode=pydicom.config.IGNORE
        )
