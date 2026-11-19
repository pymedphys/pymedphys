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

"""Describe the items that D writes or keeps where a reviewed rule covers them.

:func:`~pymedphys._dicom.deidentify.conformance_values.values_written`
takes from here its descriptions of the sequences whose items a reviewed
rule gives D (D-021): the items that D writes, from
:mod:`~pymedphys._dicom.deidentify.dummy_values`, among them the cleaned
ICC Profile; the items that D keeps, each attribute under its own action;
and the written values that name PyMedPhys. Each names tags, VRs, actions,
and the engine's constants, never a value from an instance or a key.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from . import dummy_values
from .conformance import ConformanceStatement
from .conformance_prose import code, join
from .element_rules import IOD_DEFINED_VRS, KEPT_VRS
from .standard import dictionary_attribute
from .walker import REVIEWED_DUMMY_SEQUENCES


def reviewed_items(named: Callable[[str], str]) -> list[str]:
    """Describe what D writes where a reviewed rule gives the value (D-021)."""
    lines = []
    for tag, compared in REVIEWED_DUMMY_SEQUENCES.items():
        if tag == dummy_values.REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE:
            lines.append(_procedure_step_items(named, tag, compared))
            continue
        within = _reviewed_place(tag)
        (first,) = dummy_values.items_for_d(tag, [], within=within)
        source = {e.tag: e.value for e in first if e.tag in compared}
        (second,) = dummy_values.items_for_d(tag, [source], within=within)
        changed = [
            f"{named(element.tag)} `{element.value}`"
            for element, before in zip(second, first)
            if element.value != before.value
        ]
        place = "".join(f" in an item of {named(each)}" for each in within)
        elsewhere = (
            " Elsewhere, D on it has no reviewed rule, so the instance is sequestered."
            if within
            else ""
        )
        lines.append(
            f"D on {named(tag)}{place} writes one item, with "
            + join(f"{named(element.tag)} `{element.value}`" for element in first)
            + ". Where a source item's "
            + join((named(t) for t in sorted(compared)), "or")
            + " equals the item's, as D compares values, the item has "
            + join(changed)
            + " instead."
            + elsewhere
        )
    lines.append(_icc_profile(named))
    return lines


def _reviewed_place(tag: str) -> tuple[str, ...]:
    """Return the sequence whose items alone hold a sequence's reviewed rule.

    It is empty for a sequence whose rule holds everywhere.
    """
    return tuple(sorted(dummy_values.REVIEWED_WITHIN.get(tag, frozenset())))


def _procedure_step_items(
    named: Callable[[str], str], tag: str, compared: frozenset[str]
) -> str:
    """Describe the items that D writes in Referenced Performed Procedure Step Sequence."""
    (uid,) = compared
    return (
        f"D on {named(tag)} writes, for each source item, one item, with "
        f"{named('(0008,1150)')} "
        f"`{dummy_values.MODALITY_PERFORMED_PROCEDURE_STEP}`, the Modality "
        f"Performed Procedure Step SOP Class, and {named(uid)} the keyed "
        "replacement of the source item's, as D writes for a UI attribute. "
        f"Where the sequence has no item, or an item has no {named(uid)}, "
        "the instance is sequestered."
    )


def _icc_profile(named: Callable[[str], str]) -> str:
    """Describe the profile that D writes in place of ICC Profile."""
    first, second = dummy_values.CONSTANTS["LO"]
    return (
        f"D on {named(dummy_values.ICC_PROFILE)} writes the source profile "
        "cleaned of everything but its colorimetry: it keeps the tags that "
        "map device values to the profile connection space and back, the "
        "media white and black points, luminance, chromatic adaptation, "
        "coding-independent code points, chromaticity, measurement and "
        "viewing conditions, the colorimetric intent image state, and the "
        "rendering intent gamuts, each parsed and written again, and removes "
        "every text tag, private tag, and other tag. Its header keeps the "
        "source's version, profile connection space, illuminant, rendering "
        "intent, and embedded-profile flags, names no CMM, platform, device, "
        "or creator, gives 1 January 1900 as its date, and makes it an input "
        "device profile; a version 4 profile's profile ID is computed again. "
        f"Its description and copyright are `{first}`, or `{second}` where "
        "the source has the same bytes. Where the source is not of ICC version "
        "2 or 4, not an input, display, or colour space profile, has another "
        "illuminant than D50, holds a colorimetric tag that does not parse "
        "as its version defines it, or is a version 2 display profile whose "
        "media white point is not D50, which colour management modules read "
        "by class, D writes instead a fixed ICC version 2.4 "
        "input profile of the sRGB colour space of IEC 61966-2.1, described "
        f"`{first} sRGB`; pixel values are preserved, but the source "
        "profile's colorants and tone curves are not, so colour rendering can "
        "then change substantially. PS3.3 Section C.11.15.1.1 requires the "
        "profile's data colour space to be RGB, so where the source is not "
        "an RGB profile, the instance is sequestered."
    )


def kept_items(
    statement: ConformanceStatement, named: Callable[[str], str]
) -> list[str]:
    """Describe the items that D keeps where a reviewed rule keeps them (D-021).

    An attribute that no rule covers, such as Observer Type (0040,A084), of
    VR CS, takes the action that the statement gives its VR.
    """
    actions = {entry.tag: entry.action for entry in statement.attributes}
    lines = []
    for tag, kept in dummy_values.KEPT_ITEM_ATTRIBUTES.items():
        place = _reviewed_place(tag)
        where = (
            " directly in an item of " + join((named(t) for t in place), "or")
            if place
            else ""
        )
        lines.append(
            f"D on {named(tag)}{where} keeps each source item, and in it only "
            "these attributes, each under the action that the policy gives it "
            "there: "
            + "; ".join(_kept_action(each, actions, named) for each in sorted(kept))
            + ". The item's other attributes are removed, and none of these is "
            "added to an item that lacks it."
        )
    return lines


def _kept_action(
    tag: str, actions: Mapping[str, str], named: Callable[[str], str]
) -> str:
    """Describe the action of one attribute of a kept item."""
    if tag in actions:
        return f"{named(tag)}, {code(actions[tag])}"
    attribute = dictionary_attribute(tag)
    (vr,) = attribute.vrs if attribute is not None else ("",)
    if vr not in KEPT_VRS | IOD_DEFINED_VRS:
        raise ValueError(f"no rule covers the kept item attribute {tag}")
    return f"{named(tag)}, {code('K')}, as an attribute of VR {vr} that no rule covers"


def naming_pymedphys(named: Callable[[str], str]) -> dict[str, list[str]]:
    """Name each value that a reviewed rule writes and that names PyMedPhys.

    Each is listed by the sequence whose item holds it.
    """
    found = {
        tag: [
            f"{named(element.tag)} `{element.value}`"
            for item in dummy_values.items_for_d(tag, [], within=_reviewed_place(tag))
            for element in item
            if "PYMEDPHYS" in element.value.upper()
        ]
        for tag in REVIEWED_DUMMY_SEQUENCES
        # The procedure step's items hold only UIDs, written for the source.
        if tag != dummy_values.REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE
    }
    return {tag: values for tag, values in found.items() if values}
