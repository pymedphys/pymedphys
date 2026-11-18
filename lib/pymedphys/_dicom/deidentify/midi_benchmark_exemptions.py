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

"""Measure what candidate exemptions from the text search would release (D-018).

The residual search sends a file to QC review where it finds the text of a
removed value inside a kept one (D-027). On MIDI-B, most such files are held
because a removed value equals a coded term or an equipment name that the
profile keeps elsewhere. :func:`would_release` names the candidate
exemptions under which every reason that withheld an instance is exempt, so
that the benchmark can count, without applying them, how many instances
each would release. The engine applies none of them.

- **Coded values**: the text was found in a value of VR CS, or in the Code
  Value, Coding Scheme Designator, Coding Scheme Version, or Code Meaning of
  a code item. A Coding Scheme Designator is exempt whatever it names; the
  other values of a code item only where the item's designator is one of
  the external coding schemes of PS3.16 Section 8 listed here.
- **Equipment**: the text was found in Manufacturer, Manufacturer's Model
  Name, or Software Versions, which the Basic Profile keeps.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from pymedphys._imports import pydicom

from .midi_benchmark_sources import read_source, reason_code

CODED = "coded values"
EQUIPMENT = "equipment"
BOTH = "coded values and equipment"
EXEMPTIONS = (CODED, EQUIPMENT, BOTH)

_RESIDUAL_TEXT = "residual-text"
_DESIGNATOR = "(0008,0102)"
# Code Value, Coding Scheme Version, Code Meaning, Long Code Value, and URN
# Code Value, which a code item's designator qualifies.
_CODE_ITEM = frozenset(
    {"(0008,0100)", "(0008,0103)", "(0008,0104)", "(0008,0119)", "(0008,0120)"}
)
# External coding schemes that PS3.16 Section 8 gives designators to.
_STANDARD_SCHEMES = frozenset(
    {
        "DCM",
        "SCT",
        "SRT",
        "SNM3",
        "LN",
        "UCUM",
        "NCIt",
        "RADLEX",
        "FMA",
        "UMLS",
        "MDC",
        "I10",
        "I9C",
    }
)
# Manufacturer, Manufacturer's Model Name, and Software Versions.
_EQUIPMENT = frozenset({"(0008,0070)", "(0008,1090)", "(0018,1020)"})


def would_release(reasons: Iterable[object], source: Path | None) -> tuple[str, ...]:
    """Return the candidate exemptions that would release a withheld instance.

    Parameters
    ----------
    reasons : iterable
        The release gate's reasons for withholding the instance.
    source : Path, optional
        The instance's source file, read only where a code item's designator
        decides; without it, no such finding is exempt.

    Returns
    -------
    tuple of str
        Those of :data:`EXEMPTIONS` under which every reason is a residual
        text finding that the exemption covers. Empty where any reason is of
        another kind or has no place in the written file.
    """
    reasons = tuple(reasons)
    if not reasons:
        return ()
    read: list[pydicom.Dataset | None] = []

    def dataset() -> pydicom.Dataset | None:
        if not read:
            read.append(None if source is None else read_source(source))
        return read[0]

    covered = {CODED: True, EQUIPMENT: True, BOTH: True}
    for reason in reasons:
        element = _found_in(reason)
        if element is None:
            return ()
        coded = _coded(element, getattr(reason.location, "vr", None), dataset)  # type: ignore[attr-defined]
        equipment = element.tag in _EQUIPMENT
        covered[CODED] &= coded
        covered[EQUIPMENT] &= equipment
        covered[BOTH] &= coded or equipment
    return tuple(name for name in EXEMPTIONS if covered[name])


def _found_in(reason: object) -> object | None:
    """Return the element of the written file that a residual text was found
    in, or ``None`` for any other reason."""
    if reason_code(reason) != _RESIDUAL_TEXT:
        return None
    location = getattr(reason, "location", None)
    return None if location is None else getattr(location, "element", None)


def _coded(
    element: object,
    vr: str | None,
    dataset: Callable[[], pydicom.Dataset | None],
) -> bool:
    tag = getattr(element, "tag", "")
    if vr == "CS" or tag == _DESIGNATOR:
        return True
    if tag not in _CODE_ITEM:
        return False
    item = _item(dataset(), getattr(element, "items", ()))
    if item is None:
        return False
    designator = item.get((0x0008, 0x0102))
    value = None if designator is None else designator.value
    return isinstance(value, str) and value.strip() in _STANDARD_SCHEMES


def _item(
    dataset: pydicom.Dataset | None, items: tuple[tuple[str, int], ...]
) -> pydicom.Dataset | None:
    """Return the source's item at a written file's path, or ``None``.

    The profile keeps a code item's sequences whole, so its place in the
    written file is its place in the source.
    """
    if dataset is None or not items:
        return None
    current = dataset
    for tag, index in items:
        element = current.get(pydicom.tag.Tag(int(tag[1:5], 16), int(tag[6:10], 16)))
        if element is None or element.VR != "SQ" or index >= len(element.value):
            return None
        current = element.value[index]
    return current


def exemption_rows(counted: dict[tuple[str, str], int]) -> list[dict[str, object]]:
    """Return counts by exemption and modality as rows, in exemption order."""
    return [
        {"exemption": exemption, "modality": modality, "instances": n}
        for (exemption, modality), n in sorted(
            counted.items(), key=lambda pair: (EXEMPTIONS.index(pair[0][0]), pair[0][1])
        )
    ]
