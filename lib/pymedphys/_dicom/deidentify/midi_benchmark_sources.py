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

"""Describe what a MIDI check found in its source instance, without a value (D-018).

A failed check of a released instance can be explained by its source
instance: an attribute that a check asks to be kept cannot be, where the
source never held it. :func:`source_state` says whether the source holds the
attribute at the check's place, and with a value. A text that a check asks
to be removed, and the release keeps, is described by :func:`removed_shape`
in coarse, value-free terms, such as the number of digits of an Integer
String, so that a reviewer can judge whether it could carry an identifier.
:func:`reason_places` says where the reasons that withheld an instance were
found, by tag, so that the holds that cost the most can be traced.
"""

from __future__ import annotations

import collections
import enum
import re
from collections.abc import Mapping
from pathlib import Path

from pymedphys._imports import pydicom

from .midi_answer_key import Action, Check
from .midi_benchmark_values import element_text, find_element, unbracketed

ABSENT = "absent"
EMPTY = "empty"
VALUE = "value"

_IS = re.compile(r"[+-]?([0-9]{1,12})")


def read_source(path: Path) -> pydicom.Dataset | None:
    """Read a source instance, deferring large values, or return ``None``."""
    try:
        return pydicom.dcmread(path, defer_size=1024)
    except Exception:  # pylint: disable = broad-exception-caught
        return None


def source_state(source: pydicom.Dataset, check: Check) -> str | None:
    """Whether the source holds the check's attribute: absent, empty, or value."""
    if check.path is None:
        return None
    element = find_element(source, check.path)
    if element is None:
        return ABSENT
    return VALUE if element_text(element) else EMPTY


def removed_shape(source: pydicom.Dataset, check: Check) -> tuple[str, str, bool]:
    """Describe the source value of a text that a check asks to be removed.

    Returns the value's VR; its shape, given for an Integer String as its
    number of digits, and otherwise as ``not IS``; and whether the answer
    key's text is the whole value, ignoring surrounding spaces.

    >>> dataset = pydicom.Dataset()
    >>> dataset.SeriesNumber = "20240131"
    >>> from .midi_answer_key import parse_check
    >>> check = parse_check({"action": "<text_removed>", "tag_ds": "<(0020,0011)>",
    ...                      "action_text": "<20240131>"})
    >>> removed_shape(dataset, check)
    ('IS', '8 digits, a date', True)
    """
    element = None if check.path is None else find_element(source, check.path)
    if element is None:
        return "none", ABSENT, False
    text = element_text(element)
    answer = unbracketed(check.action_text or "").strip()
    whole = bool(text) and text.strip() == answer
    if element.VR != "IS":
        return str(element.VR), "not IS" if text else EMPTY, whole
    return "IS", integer_shape(text), whole


def integer_shape(text: str) -> str:
    """Describe an Integer String by its number of digits, without its value.

    >>> [integer_shape(t) for t in ("7", "12345", "19991232", "123456789", "1.5", "")]
    ['1 to 4 digits', '5 to 7 digits', '8 digits', '9 or more digits', 'not a valid IS', 'empty']
    """
    if not text.strip():
        return EMPTY
    match = _IS.fullmatch(text.strip())
    if match is None:
        return "not a valid IS"
    digits = match.group(1)
    if len(digits) <= 4:
        return "1 to 4 digits"
    if len(digits) <= 7:
        return "5 to 7 digits"
    if len(digits) == 8:
        return "8 digits, a date" if _is_date(digits) else "8 digits"
    return "9 or more digits"


def _is_date(digits: str) -> bool:
    """Whether eight digits read as a plausible YYYYMMDD date."""
    year, month, day = int(digits[:4]), int(digits[4:6]), int(digits[6:])
    return 1900 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31


def counted_order(pair: tuple[tuple[object, ...], int]) -> tuple[str, ...]:
    """Order counted descriptions by their text, a missing attribute first."""
    return tuple("" if part is None else str(part) for part in pair[0])


def described_rows(counted: collections.Counter) -> list[dict[str, object]]:
    """Return counted (category, action, attribute) descriptions as rows."""
    return [
        {"category": category, "action": action, "attribute": attribute, "checks": n}
        for (category, action, attribute), n in sorted(
            counted.items(), key=counted_order
        )
    ]


# What each kind of failed check records of its source instance: one that
# asked for an attribute or a value to be present, and one that asked for a
# text to be removed.
EXPLAINED = {
    "present": ("category", "action", "attribute", "source"),
    "removed": ("category", "action", "attribute", "vr", "shape", "whole_value"),
}


def describe_source(
    check: Check,
    source: pydicom.Dataset | None,
    described: tuple[str, ...],
    explained: Mapping[str, collections.Counter],
) -> None:
    """Count a failed check by what its source instance holds, without a value."""
    if source is None:
        return
    if check.action in (Action.TAG_RETAINED, Action.TEXT_NOTNULL):
        explained["present"][(*described, source_state(source, check))] += 1
    elif check.action is Action.TEXT_REMOVED:
        explained["removed"][(*described, *removed_shape(source, check))] += 1


def explained_rows(
    explained: Mapping[str, collections.Counter],
) -> dict[str, list[dict[str, object]]]:
    """Return the counts of :func:`describe_source` as rows, by kind."""
    return {
        kind: [
            {**dict(zip(fields, key)), "checks": n}
            for key, n in sorted(explained[kind].items(), key=counted_order)
        ]
        for kind, fields in EXPLAINED.items()
    }


def reason_places(reasons: tuple[object, ...]) -> set[tuple[str, str, str, str]]:
    """Return where each reason with a place was found, by tag, without a value.

    Each place is the reason's code; the source attribute, as its sequences'
    and its own tags, without item numbers or private creators; the
    attribute of the written file that the reason was found in, or the
    region of the file; and the VR it was found as.
    """
    places = set()
    for reason in reasons:
        path = getattr(reason, "path", None)
        if path is None or not hasattr(path, "tag"):
            continue
        location = getattr(reason, "location", None)
        found = ""
        if location is not None:
            element = getattr(location, "element", None)
            found = (
                _tags(element)
                if element is not None
                else str(getattr(location.region, "value", location.region))
            )
        vr = "" if location is None else str(getattr(location, "vr", None) or "")
        places.add((reason_code(reason), _tags(path), found, vr))
    return places


def place_rows(places: collections.Counter) -> list[dict[str, object]]:
    """Return counted places as rows, the most instances first."""
    fields = ("code", "source", "found_in", "vr")
    return [
        {**dict(zip(fields, place)), "instances": n}
        for place, n in sorted(places.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _tags(path: object) -> str:
    items = getattr(path, "items", ())
    return "/".join([*(tag for tag, _ in items), str(getattr(path, "tag", ""))])


def reason_code(reason: object) -> str:
    """Return a withheld input's reason as a code, without a value."""
    code = getattr(reason, "code", None)
    if isinstance(code, enum.Enum):
        return str(code.value)
    if isinstance(reason, enum.Enum):
        return str(reason.value)
    return type(reason).__name__
