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
"""

from __future__ import annotations

import re

from pymedphys._imports import pydicom

from .midi_answer_key import AttributePath, Element


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
