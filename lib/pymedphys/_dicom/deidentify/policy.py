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

"""Compose the presets, and validate a policy's options before processing.

A preset names a set of DICOM PS3.15 Options on top of the Basic Application
Level Confidentiality Profile, chosen from the Options that the design
document's Scope targets:

- ``basic``, the default: the Basic Profile alone;
- ``tps-import``: Retain Device Identity, Retain Patient Characteristics,
  Retain Longitudinal Temporal Information with Modified Dates, and Clean
  Descriptors, for copies in non-clinical treatment planning systems;
- ``public-release``: Retain Safe Private, Modified Dates, and Clean
  Descriptors, for collections being assessed for public sharing.

Composing a policy gives each attribute of Table E.1-1 its action under the
preset's options (:func:`~pymedphys._dicom.deidentify.actions.effective_actions`),
and each reviewed supplementary rule, for an attribute that the table omits,
its action under the same options
(:func:`~pymedphys._dicom.deidentify.actions.effective_supplementary_actions`),
such as C for Beam Name under Clean Descriptors. It first checks that the
options are within the supported scope and that the table is of the same
edition as the data dictionary, against which the supplementary rules were
reviewed.

PS3.15 defines no precedence between options, so an attribute to which two
selected options give different actions makes the policy invalid. The one
exception belongs to the ``tps-import`` preset, which deliberately selects
both Retain Device Identity (K) and Modified Dates (C). No output can satisfy
both while one of the eleven attributes they conflict on has a value, so the
preset modifies each of them as Modified Dates requires, by the attribute's
temporal role, and makes no PS3.15 conformance claim. The same options chosen
without the preset, and any other conflict, such as one a new edition of the
table adds, are rejected.

A preset is enabled only once its behaviour is implemented and validated. No
preset is enabled yet; the first supported release is to enable ``basic``, the
Basic Profile alone, and a preset that adds the Clean Descriptors Option to
it. The engine takes its policy from :func:`select_policy`, which refuses a
preset that is not enabled. A policy composed from a given table is never
enabled, and a custom option set is validated but not enabled.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Iterable, Mapping

from .actions import OptionConflict, effective_actions, effective_supplementary_actions
from .attribute_roles import AttributeRoles
from .standard import OPTIONS, ProfileTable, load_data_dictionary, load_table_e1_1
from .temporal_roles import TemporalRole, load_temporal_roles

DEVICE_IDENTITY = "retain_device_identity"
MODIFIED_DATES = "retain_longitudinal_modified_dates"

# The Options that the design document's Scope targets, in Table E.1-1's order.
TARGET_OPTIONS = (
    "retain_safe_private",
    DEVICE_IDENTITY,
    "retain_patient_characteristics",
    MODIFIED_DATES,
    "clean_descriptors",
)

# Each preset's options, in Table E.1-1's order.
PRESETS: Mapping[str, tuple[str, ...]] = types.MappingProxyType(
    {
        "basic": (),
        "tps-import": (
            DEVICE_IDENTITY,
            "retain_patient_characteristics",
            MODIFIED_DATES,
            "clean_descriptors",
        ),
        "public-release": (
            "retain_safe_private",
            MODIFIED_DATES,
            "clean_descriptors",
        ),
    }
)
DEFAULT_PRESET = "basic"
# The presets whose behaviour is implemented and validated. None is yet; the
# first supported release is to enable ``basic`` and a preset that adds the
# Clean Descriptors Option to it.
ENABLED_PRESETS: frozenset[str] = frozenset()

# The preset that resolves the conflicts below, and the actions it resolves.
_TPS_IMPORT = "tps-import"
_RESOLVABLE = types.MappingProxyType({DEVICE_IDENTITY: "K", MODIFIED_DATES: "C"})


class PolicyError(ValueError):
    """A preset or option set that cannot be used as a policy."""


@dataclasses.dataclass(frozen=True)
class ResolvedConflict:
    """A conflict between options that the ``tps-import`` preset resolves.

    Attributes
    ----------
    conflict : OptionConflict
        The attribute and the actions its selected options give it.
    action : str
        The action applied: Modified Dates' action, ``"C"``, since the value
        is modified rather than kept.
    role : TemporalRole
        The attribute's temporal role, by which Modified Dates applies the
        action, such as :attr:`TemporalRole.DEVICE` for a calibration date.
    unmet : tuple of str
        The options whose action is not applied, such as
        ``("retain_device_identity",)``.
    """

    conflict: OptionConflict
    action: str
    role: TemporalRole
    unmet: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Policy:
    """A validated policy: the action of each attribute of Table E.1-1.

    Attributes
    ----------
    preset : str or None
        The preset, such as ``"basic"``, or None for a custom option set.
    edition : str
        The edition of Table E.1-1, such as ``"2026d"``.
    options : tuple of str
        The selected options, in the table's order.
    actions : Mapping of str to str
        Each attribute's action code, keyed by its tag as Table E.1-1 gives
        it, in the table's order, including the attributes in
        :attr:`resolved`. Read-only.
    resolved : tuple of ResolvedConflict
        The conflicts between selected options that the preset resolves, in
        the table's order. Only ``tps-import`` has any.
    supplementary_actions : Mapping of str to str
        The action of each reviewed supplementary rule under the selected
        options, keyed by its tag as the data dictionary gives it, such as
        ``"(300A,00C2)"`` for Beam Name: the actions of attributes that
        Table E.1-1 omits. A text attribute that the table omits and no rule
        covers has no entry; the engine (M3) will apply
        :data:`~pymedphys._dicom.deidentify.supplementary_actions.UNCOVERED_TEXT_ACTION`
        to it. Read-only.
    enabled : bool
        Whether the engine may use the policy: only for an enabled preset,
        composed from the pinned tables. Only :func:`compose_policy` sets it,
        so a policy constructed directly, or copied with
        :func:`dataclasses.replace`, is not enabled.
    """

    preset: str | None
    edition: str
    options: tuple[str, ...]
    # Mappings are not hashable, so they are left out of the hash.
    actions: Mapping[str, str] = dataclasses.field(hash=False)
    resolved: tuple[ResolvedConflict, ...]
    supplementary_actions: Mapping[str, str] = dataclasses.field(hash=False)
    # Not an argument, so that neither the constructor nor dataclasses.replace
    # can enable a policy; _compose sets it.
    enabled: bool = dataclasses.field(default=False, init=False)

    @property
    def claims_conformance(self) -> bool:
        """Whether the policy can claim PS3.15 conformance.

        A policy that leaves a selected option's action unapplied cannot.
        This is a claim about the policy only: each instance's claim still
        comes from its own validated result.
        """
        return not self.resolved


def _join(values: Iterable[str]) -> str:
    """Join ``values`` as prose: ``"a"``, ``"a and b"``, or ``"a, b, and c"``."""
    values = list(values)
    if len(values) <= 2:
        return " and ".join(values)
    return ", ".join(values[:-1]) + ", and " + values[-1]


def _checked_options(options: Iterable[str]) -> tuple[str, ...]:
    """Return ``options`` in the table's order, once each, after checking them."""
    if isinstance(options, str):
        raise TypeError(
            "options must be a collection of option names, not a single string"
        )
    chosen = set(options)
    unknown = sorted(chosen.difference(OPTIONS))
    if unknown:
        raise PolicyError(
            f"unknown options {unknown}; the options of Table E.1-1 are "
            + ", ".join(OPTIONS)
        )
    unsupported = [o for o in OPTIONS if o in chosen and o not in TARGET_OPTIONS]
    if unsupported:
        named = (
            f"the option {unsupported[0]} is"
            if len(unsupported) == 1
            else f"the options {_join(unsupported)} are"
        )
        raise PolicyError(
            f"{named} outside the supported scope; "
            f"the supported options are {_join(TARGET_OPTIONS)}"
        )
    return tuple(option for option in OPTIONS if option in chosen)


def _resolution(
    conflict: OptionConflict, roles: AttributeRoles[TemporalRole]
) -> ResolvedConflict | None:
    """Return how ``tps-import`` resolves ``conflict``, or None if it cannot."""
    if dict(conflict.actions) != dict(_RESOLVABLE) or conflict.tag not in roles.rules:
        return None
    action = conflict.actions[MODIFIED_DATES]
    return ResolvedConflict(
        conflict=conflict,
        action=action,
        role=roles.role(conflict.tag),
        unmet=tuple(o for o, given in conflict.actions.items() if given != action),
    )


def _conflict_message(conflicts: list[OptionConflict], hint: bool) -> str:
    """Describe unresolved conflicts by their options and tags, never values."""
    by_options: dict[tuple[str, ...], list[str]] = {}
    for conflict in conflicts:
        by_options.setdefault(tuple(conflict.actions), []).append(conflict.tag)
    parts = []
    for options, tags in by_options.items():
        count = f"{len(tags)} attribute{'s' if len(tags) > 1 else ''}"
        parts.append(
            f"the options {_join(options)} give different actions to {count}: "
            + ", ".join(tags)
        )
    message = "PS3.15 defines no precedence between options, and " + "; ".join(parts)
    if hint:
        message += (
            f"; only the {_TPS_IMPORT} preset, which claims no PS3.15 "
            "conformance, selects both"
        )
    return message


def _compose(
    preset: str | None, options: Iterable[str], table: ProfileTable | None
) -> Policy:
    """Validate ``options`` for ``preset``, or for a custom set if it is None."""
    selected = _checked_options(options)
    pinned = table is None
    if table is None:
        table = load_table_e1_1()
    dictionary = load_data_dictionary()
    if table.edition != dictionary.edition:
        raise PolicyError(
            f"Table E.1-1 is of edition {table.edition}, but the data dictionary "
            f"and the rules reviewed against it are of edition {dictionary.edition}"
        )

    effective = effective_actions(selected, table=table)
    supplementary = effective_supplementary_actions(selected)
    conflicts = effective.conflicts + supplementary.conflicts
    resolved: dict[str, ResolvedConflict] = {}
    unresolved: list[OptionConflict] = []
    resolvable: list[ResolvedConflict | None] = []
    if conflicts:
        roles = load_temporal_roles()
        resolvable = [_resolution(c, roles) for c in conflicts]
    for conflict, resolution in zip(conflicts, resolvable):
        if preset == _TPS_IMPORT and resolution is not None:
            resolved[conflict.tag] = resolution
        else:
            unresolved.append(conflict)
    if unresolved:
        raise PolicyError(
            _conflict_message(unresolved, preset is None and all(resolvable))
        )

    composed = Policy(
        preset=preset,
        edition=table.edition,
        options=selected,
        actions=types.MappingProxyType(
            {
                row.tag: resolved[row.tag].action
                if row.tag in resolved
                else effective.actions[row.tag]
                for row in table.attributes
            }
        ),
        resolved=tuple(resolved.values()),
        supplementary_actions=supplementary.actions,
    )
    if preset in ENABLED_PRESETS and pinned:
        # The way a frozen dataclass sets a field that is not an argument.
        object.__setattr__(composed, "enabled", True)
    return composed


def compose_policy(
    preset: str = DEFAULT_PRESET, *, table: ProfileTable | None = None
) -> Policy:
    """Compose and validate the policy of a preset, whether enabled or not.

    Parameters
    ----------
    preset : str, optional
        One of :data:`PRESETS`. Defaults to ``"basic"``.
    table : ProfileTable, optional
        Table E.1-1. Defaults to
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1`. A
        policy composed from a given table is never enabled, since the table
        may have been altered.

    Returns
    -------
    Policy
        Enabled only for a preset in :data:`ENABLED_PRESETS` composed from the
        pinned table.

    Raises
    ------
    TypeError
        If ``preset`` is not a string.
    PolicyError
        If ``preset`` is not one of :data:`PRESETS`; if the table is of
        another edition than the data dictionary; or if two of the preset's
        options give an attribute of the table, or a supplementary rule,
        different actions, other than the conflicts the ``tps-import``
        preset resolves.
    """
    if not isinstance(preset, str):
        raise TypeError("preset must be the name of a preset")
    if preset not in PRESETS:
        raise PolicyError(
            f"unknown preset {preset!r}; the presets are {_join(PRESETS)}"
        )
    return _compose(preset, PRESETS[preset], table)


def compose_custom_policy(
    options: Iterable[str], *, table: ProfileTable | None = None
) -> Policy:
    """Validate a custom set of options as a policy, which is not enabled.

    A custom policy must be able to conform, so every conflict between its
    options is rejected, including those the ``tps-import`` preset resolves.

    Parameters
    ----------
    options : iterable of str
        The selected options, from :data:`TARGET_OPTIONS`.
    table : ProfileTable, optional
        Table E.1-1. Defaults to
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1`.

    Returns
    -------
    Policy
        With no preset, and not enabled.

    Raises
    ------
    TypeError
        If ``options`` is a single string rather than a collection of names.
    PolicyError
        If an option is not one of Table E.1-1's options, or is outside
        :data:`TARGET_OPTIONS`; if the table is of another edition than the
        data dictionary; or if two of the options give an attribute
        different actions.
    """
    return _compose(None, options, table)


def select_policy(preset: str = DEFAULT_PRESET) -> Policy:
    """Return the policy of an enabled preset, for the engine to apply.

    Parameters
    ----------
    preset : str, optional
        One of :data:`ENABLED_PRESETS`. Defaults to ``"basic"``.

    Returns
    -------
    Policy
        The preset's policy, composed from the pinned tables.

    Raises
    ------
    TypeError
        If ``preset`` is not a string.
    PolicyError
        For any reason :func:`compose_policy` gives, or if the preset is not
        enabled because its behaviour is not yet implemented and validated.
        No preset is enabled yet, so every preset is refused.
    """
    policy = compose_policy(preset)
    if not policy.enabled:
        enabled = [name for name in PRESETS if name in ENABLED_PRESETS]
        if not enabled:
            status = "no preset is enabled yet"
        elif len(enabled) == 1:
            status = f"only {enabled[0]} is enabled"
        else:
            status = f"only {_join(enabled)} are enabled"
        raise PolicyError(
            f"the {preset} preset is not enabled: its behaviour is not yet "
            f"implemented and validated; {status}"
        )
    return policy
