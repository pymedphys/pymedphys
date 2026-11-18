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

"""Find what a MIDI benchmark check scores in a data set (D-018).

The checks of a MIDI answer key name a place as a path of attributes and
sequence items. :func:`find_element` finds the attribute at that place, and
:func:`element_text` gives its value as the text that the checks compare,
and :func:`compare_text` compares it with the answer key's.
:func:`is_engine_replacement` says whether a value is one that the engine
writes in place of the source's, which holds nothing of the source.
"""

from __future__ import annotations

import base64
import functools
import re

from pymedphys._imports import pydicom

from .ae_titles import TOKEN_CHARACTERS, TOKEN_PREFIX
from .midi_answer_key import AttributePath, Element
from .pseudonyms import CODE_BYTES, FAMILY_NAME, PATIENT_ID_PREFIX
from .residuals import written_constants


def unbracketed(text: str) -> str:
    """Return ``text`` without any ``<`` or ``>``, as the script compares it."""
    return text.replace("<", "").replace(">", "")


def is_bulk_data(element: pydicom.DataElement) -> bool:
    """Whether an element is Pixel Data or Overlay Data."""
    return element.tag == 0x7FE00010 or (
        element.tag.group & 0xFF01 == 0x6000 and element.tag.element == 0x3000
    )


def find_element(
    dataset: pydicom.Dataset, path: AttributePath
) -> pydicom.DataElement | None:
    """Return the element at ``path``, or ``None`` if there is none."""
    current = dataset
    for depth, wanted in enumerate(path.elements):
        element = _element(current, wanted)
        if element is None or depth == len(path.elements) - 1:
            return element
        if element.VR != "SQ":
            return None
        index = path.items[depth]
        if index >= len(element.value):
            return None
        current = element.value[index]
    return None  # pragma: no cover - the loop returns at the last element


def _element(dataset: pydicom.Dataset, wanted: Element) -> pydicom.DataElement | None:
    if not wanted.is_private:
        return dataset.get((wanted.group << 16) | wanted.element)
    for element in dataset:
        tag = element.tag
        if tag.group != wanted.group or tag.element < 0x1000:
            continue
        if tag.element & 0xFF != wanted.element:
            continue
        creator = dataset.get((tag.group << 16) | (tag.element >> 8))
        if (
            creator is not None
            and str(creator.value).strip().upper()
            == (wanted.creator or "").strip().upper()
        ):
            return element
    return None


def element_text(element: pydicom.DataElement) -> str:
    """Return an element's value as text, as the checks compare it.

    A multi-valued value is joined by ``\\``, as it is encoded; bytes are
    read as ISO 8859-1, so that text in them is found; and a sequence is the
    text of every element of its items, joined by spaces.
    """
    value = element.value
    if element.VR == "SQ":
        return " ".join(
            text
            for item in value
            for inner in item
            for text in [element_text(inner)]
            if text
        )
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("latin-1").strip(" \t\r\n\x00")
    if isinstance(value, pydicom.multival.MultiValue):
        return "\\".join(str(each) for each in value).strip(" \t\r\n\x00")
    return str(value).strip(" \t\r\n\x00")


_NUMBER = re.compile(r"[0-9]*\.?[0-9]+|[0-9]+\.")
_WORD = re.compile(r"\w+")


def compare_text(text: str, answer: str, *, keep: bool) -> bool | None:
    """Compare an attribute's text with the answer key's, ignoring case.

    Two numbers compare as numbers. Otherwise the answer is kept if it is
    within the text, and removed if none of its words is; a text that keeps
    some of its words, but not all, fails both. ``None`` means the answer
    has no word to compare.
    """
    text = unbracketed(text).lower()
    answer = unbracketed(answer).lower()
    if _NUMBER.fullmatch(text) and _NUMBER.fullmatch(answer):
        return (float(text) == float(answer)) == keep
    if answer in text:
        return keep
    words = _WORD.findall(answer)
    if not words:
        return None
    found = sum(word in text for word in words)
    return found == len(words) if keep else found == 0


def held_words(text: str, answer: str) -> list[str]:
    """Return the words of the answer key's text that a text holds.

    Each is in capitals, and held as :func:`compare_text` finds it: within
    the text, ignoring case.

    >>> held_words("AX T1 GRAY", "<gray 2>")
    ['GRAY']
    """
    text = unbracketed(text).lower()
    words = _WORD.findall(unbracketed(answer).lower())
    return [word.upper() for word in words if word in text]


# A character of the engine's keyed codes and tokens: the base32 alphabet of
# RFC 4648, in which they are written.
_CODE_CHARACTER = "[A-Z2-7]"
# The characters of a patient's code: CODE_BYTES bytes in base32, unpadded.
_CODE_LENGTH = len(base64.b32encode(bytes(CODE_BYTES)).rstrip(b"="))

# The values that the engine derives from a source value under the run's key
# alone, by the VR they are written in: a patient's pseudonym, as Patient ID
# and as Patient's Name, and an application entity's token under Retain
# Device Identity.
_KEYED_VALUES: dict[str, re.Pattern[str]] = {
    "LO": re.compile(
        f"{re.escape(PATIENT_ID_PREFIX)}{_CODE_CHARACTER}{{{_CODE_LENGTH}}}"
    ),
    "PN": re.compile(f"{re.escape(FAMILY_NAME)}\\^{_CODE_CHARACTER}{{{_CODE_LENGTH}}}"),
    "AE": re.compile(
        f"{re.escape(TOKEN_PREFIX)}{_CODE_CHARACTER}{{{TOKEN_CHARACTERS}}}"
    ),
}

# Padding that a value may carry: spaces, and NUL from some writers.
_PADDING = " \x00"


@functools.cache
def _constants() -> frozenset[tuple[str, str]]:
    return frozenset(written_constants())


def is_engine_replacement(element: pydicom.DataElement) -> bool:
    """Whether each value of an element is one the engine writes in a source's place.

    That is a constant of the element's VR that the engine writes whatever
    the source held, as
    :func:`~pymedphys._dicom.deidentify.residuals.written_constants` lists
    them, such as ``DEIDENTIFIED``; or a value derived under the run's key
    alone: a patient's pseudonym, ``DEID-`` as Patient ID (LO) or
    ``DEIDENTIFIED^`` as Patient's Name (PN) followed by the patient's code
    of 16 characters, or an application entity's token (AE), ``AE``
    followed by 14 characters, each character an upper-case letter or a
    digit from 2 to 7. Such a value holds nothing of the source, so a word
    of the answer key's text that it holds, as :func:`compare_text` finds
    words within a text, is there by chance. An element is not such a value
    where it has no value but padding, or holds a sequence or bytes; an
    empty value among several is left out.

    Examples
    --------
    >>> from pymedphys._imports import pydicom
    >>> name = "DEIDENTIFIED^ABCDEFGHIJKLMNOP"
    >>> is_engine_replacement(pydicom.DataElement(0x00100010, "PN", name))
    True
    >>> is_engine_replacement(pydicom.DataElement(0x00100010, "PN", name + "^JO"))
    False
    """
    value = element.value
    if element.VR == "SQ" or value is None or isinstance(value, (bytes, bytearray)):
        return False
    values = [
        str(each).strip(_PADDING)
        for each in (
            value if isinstance(value, pydicom.multival.MultiValue) else [value]
        )
    ]
    values = [each for each in values if each]
    keyed = _KEYED_VALUES.get(element.VR)
    return bool(values) and all(
        (element.VR, each) in _constants()
        or (keyed is not None and keyed.fullmatch(each) is not None)
        for each in values
    )
