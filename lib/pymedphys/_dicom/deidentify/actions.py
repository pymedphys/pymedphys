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

"""Give each attribute of Table E.1-1 its action under a profile and its options.

Table E.1-1 of DICOM PS3.15 gives each attribute an action under the Basic
Application Level Confidentiality Profile, and an action under each Option
that changes it. "A requirement for an Option, when implemented, overrides any
requirement for the underlying Profile" (PS3.15 E.1.1), so an attribute takes
the action of the selected options that give one, and otherwise the Profile's.

PS3.15 E.3.6 specifies Retain Longitudinal Temporal Information with Full
Dates and with Modified Dates as mutually exclusive, so selecting both is
rejected. Otherwise PS3.15 defines no precedence between options. Where two
selected options give an attribute different actions, as Retain Device
Identity (K) and Modified Dates (C) do for eleven calibration, manufacture,
installation, and beam hold dates, no output can satisfy both while the
attribute has a value. Such an attribute is reported as a conflict and given
no action; what a policy does about it is decided when the policy is
validated.

These are the actions of Table E.1-1 alone. Compound actions such as X/Z/D
are resolved later, from the attribute's Type in its IOD, and reviewed
supplementary rules add attributes the table omits.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Iterable, Mapping

from .standard import OPTIONS, ProfileTable, load_table_e1_1

# Options that PS3.15 specifies as mutually exclusive: E.3.6 for the two Retain
# Longitudinal Temporal Information Options.
MUTUALLY_EXCLUSIVE = (
    frozenset({"retain_longitudinal_full_dates", "retain_longitudinal_modified_dates"}),
)


@dataclasses.dataclass(frozen=True)
class OptionConflict:
    """An attribute to which the selected options give different actions.

    Attributes
    ----------
    name : str
        The attribute's name, as Table E.1-1 gives it.
    tag : str
        The attribute's tag, as Table E.1-1 gives it, such as
        ``"(0018,1200)"``.
    actions : Mapping of str to str
        The action of each selected option that gives the attribute one, in
        the table's order of options, such as ``{"retain_device_identity":
        "K", "retain_longitudinal_modified_dates": "C"}``. Read-only.
    """

    name: str
    tag: str
    # A mapping is not hashable, so it is left out of the hash.
    actions: Mapping[str, str] = dataclasses.field(hash=False)


@dataclasses.dataclass(frozen=True)
class EffectiveActions:
    """The actions of Table E.1-1 under the Basic Profile and selected options.

    Attributes
    ----------
    edition : str
        The edition of the table, such as ``"2026d"``.
    options : tuple of str
        The selected options, once each, in the table's order, such as
        ``("retain_uids", "clean_descriptors")``.
    actions : Mapping of str to str
        Each attribute's action code, such as ``"X/Z/D"`` or ``"K"``, keyed
        by its tag as Table E.1-1 gives it, including
        ``"(gggg,eeee) where gggg is odd"`` for private attributes. An
        attribute in :attr:`conflicts` has none. Read-only.
    conflicts : tuple of OptionConflict
        The attributes to which the selected options give different actions,
        in the table's order.
    """

    edition: str
    options: tuple[str, ...]
    # Mappings are not hashable, so they are left out of the hash.
    actions: Mapping[str, str] = dataclasses.field(hash=False)
    conflicts: tuple[OptionConflict, ...]


def _selected(options: Iterable[str]) -> tuple[str, ...]:
    if isinstance(options, str):
        raise TypeError(
            "options must be a collection of option names, not a single string"
        )
    chosen = set(options)
    unknown = sorted(chosen.difference(OPTIONS))
    if unknown:
        raise ValueError(
            f"unknown options {unknown}; the options of Table E.1-1 are "
            + ", ".join(OPTIONS)
        )
    for exclusive in MUTUALLY_EXCLUSIVE:
        if exclusive <= chosen:
            raise ValueError(
                f"the options {sorted(exclusive)} are mutually exclusive (PS3.15 E.3.6)"
            )
    return tuple(option for option in OPTIONS if option in chosen)


def effective_actions(
    options: Iterable[str] = (), table: ProfileTable | None = None
) -> EffectiveActions:
    """Return each attribute's action under the Basic Profile and ``options``.

    Parameters
    ----------
    options : iterable of str, optional
        The selected options, by the names of
        :data:`~pymedphys._dicom.deidentify.standard.OPTIONS`, such as
        ``"retain_patient_characteristics"``. Defaults to none: the Basic
        Profile alone.
    table : ProfileTable, optional
        Table E.1-1. Defaults to
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1`.

    Returns
    -------
    EffectiveActions
        An attribute to which no selected option gives an action takes the
        Profile's action. One to which the selected options give one action
        takes it. One to which they give different actions is a conflict,
        with no action.

    Raises
    ------
    TypeError
        If ``options`` is a single string rather than a collection of names.
    ValueError
        If an option is not one of Table E.1-1's options, or if the options
        include both Retain Longitudinal Temporal Information with Full Dates
        and with Modified Dates, which PS3.15 E.3.6 makes mutually exclusive.
    """
    selected = _selected(options)
    if table is None:
        table = load_table_e1_1()

    resolved: dict[str, str] = {}
    conflicts: list[OptionConflict] = []
    for attribute in table.attributes:
        given = {
            option: attribute.options[option]
            for option in selected
            if option in attribute.options
        }
        if len(set(given.values())) > 1:
            conflicts.append(
                OptionConflict(
                    attribute.name, attribute.tag, types.MappingProxyType(given)
                )
            )
        elif given:
            resolved[attribute.tag] = next(iter(given.values()))
        else:
            resolved[attribute.tag] = attribute.basic_profile

    return EffectiveActions(
        edition=table.edition,
        options=selected,
        actions=types.MappingProxyType(resolved),
        conflicts=tuple(conflicts),
    )
