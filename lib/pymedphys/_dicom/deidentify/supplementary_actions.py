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

"""Supplementary (L2) actions for attributes that Table E.1-1 omits.

The de-identifier remains responsible for attributes that Table E.1-1 of DICOM
PS3.15 does not list (E.1.1). ``supplementary_actions.toml``, curated by hand
for one edition of the pinned PS3.6 data dictionary, gives some of them an
action from Table E.1-1a, each with a note that says why. It gives one to
every person name (PN) attribute that the table omits, and keeps Burned In
Annotation (0028,0301) and Recognizable Visual Features (0028,0302) as
received, since the engine does not change pixel data.

It also gives one to every text attribute (VR LO, SH, LT, ST, UC, or UT) that
the table omits and an IOD of the supported scope uses, at any depth. Like a
row of the table, such a rule can give an action under an option, which
overrides its Basic Profile action when the option is selected:

- operator-typed labels and text, such as Beam Name, are removed by Type
  (X/Z/D), and cleaned (C) under Clean Descriptors;
- accessory and equipment identifiers, such as Wedge ID, are device identity:
  removed by Type, and kept (K) under Retain Device Identity;
- coded and technical values, such as Code Value and Convolution Kernel, are
  kept;
- names and identifiers of people, organisations, records, and networks, such
  as Universal Entity ID, identifiers that a device reads, such as Accessory
  Code, and the text of overlays, are removed by Type under every option, as
  are the two dates in an alternative calendar, Patient's Birth Date in
  Alternative Calendar and Patient's Death Date in Alternative Calendar (X);
- De-identification Method (0012,0063) is kept, and the engine adds its own
  values to it.

Every date, time, and datetime attribute (VR DA, DT, or TM) that the table
omits has a rule too: removal by Type (X/Z/D), as the Basic Profile removes or
replaces every date and time that the table lists, with K under Retain
Longitudinal Temporal Information with Full Dates and C under Modified Dates,
as the table gives nearly every date it lists. Each also has a temporal role
(:mod:`~pymedphys._dicom.deidentify.temporal_roles`), which decides how
Modified Dates cleans it: a subject event moves with the subject's other
dates, and any other date takes a fixed dummy value.

A rule may give only C under Clean Descriptors and K under Retain Device
Identity to a text attribute, and only K under Full Dates and C under Modified
Dates to a date, time, or datetime, in each case only over a Basic Profile
action that removes or replaces the value.
:func:`~pymedphys._dicom.deidentify.actions.effective_supplementary_actions`
gives each rule's action under the selected options, as
:func:`~pymedphys._dicom.deidentify.actions.effective_actions` does for Table
E.1-1. :data:`UNCOVERED_TEXT_ACTION` declares the action for a text attribute
that the table omits and no rule covers, such as one that no supported IOD
uses: removal by Type. Nothing applies it yet; the engine (M3) will apply it to
such attributes.

The file gives actions only to attributes that the table omits, so it never
changes an action the table gives. UI attributes are left to the UID roles
file (:mod:`~pymedphys._dicom.deidentify.uid_roles`), which gives each of them
a role.
"""

from __future__ import annotations

import dataclasses
import functools
import itertools
import pathlib
import types
from collections.abc import Mapping

from pymedphys._imports import tomlkit

from .iods import load_iod_tables
from .scope import SUPPORTED_IODS
from .standard import (
    ACTION_CODES,
    MUTUALLY_EXCLUSIVE,
    OPTIONS,
    ProfileTable,
    load_data_dictionary,
    load_table_e1_1,
)

SCHEMA = "pymedphys-deid-supplementary-actions/1"
SUPPLEMENTARY_ACTIONS_PATH = (
    pathlib.Path(__file__).resolve().parent / "supplementary_actions.toml"
)

# The date, time, and datetime VRs, whose attributes also have temporal roles.
TEMPORAL_VRS = frozenset({"DA", "DT", "TM"})
# Every attribute of these VRs that Table E.1-1 omits needs an action.
COVERED_VRS = frozenset({"PN"}) | TEMPORAL_VRS
# The text VRs. Every attribute of these VRs that Table E.1-1 omits and a
# supported IOD uses needs an action.
TEXT_VRS = frozenset({"LO", "SH", "LT", "ST", "UC", "UT"})
# The action for a text attribute that Table E.1-1 omits and no rule covers,
# under every option: removed, emptied, or replaced by its Type. The engine
# (M3) will apply it; nothing applies it yet.
UNCOVERED_TEXT_ACTION = "X/Z/D"
# The options under which a rule may give an action, and the action each may
# give, as Table E.1-1 gives them: Retain Device Identity keeps (K) a device
# identifier, and Clean Descriptors cleans (C) a descriptor; Retain
# Longitudinal Temporal Information with Full Dates keeps (K) a date, and with
# Modified Dates cleans it (C) by its temporal role. Each overrides a Basic
# Profile action that removes or replaces the value.
OPTION_ACTIONS: Mapping[str, str] = types.MappingProxyType(
    {
        "retain_device_identity": "K",
        "retain_longitudinal_full_dates": "K",
        "retain_longitudinal_modified_dates": "C",
        "clean_descriptors": "C",
    }
)
# The attributes, by VR, to which each option may give its action, and what
# they are called in messages.
_TEXT = (TEXT_VRS, "a text attribute")
_TEMPORAL = (TEMPORAL_VRS, "a date, time, or datetime attribute")
_OPTION_ATTRIBUTES: Mapping[str, tuple[frozenset[str], str]] = types.MappingProxyType(
    {
        "retain_device_identity": _TEXT,
        "retain_longitudinal_full_dates": _TEMPORAL,
        "retain_longitudinal_modified_dates": _TEMPORAL,
        "clean_descriptors": _TEXT,
    }
)
# The actions of Table E.1-1a that never keep the value as received.
_REMOVING = frozenset({"X", "Z", "D", "X/Z", "X/D", "Z/D", "X/Z/D"})
# The VRs whose attributes only a roles file covers.
_ROLES_ONLY_VRS = frozenset({"UI"})
_FIELDS = frozenset({"tag", "keyword", "action", "note"})
_OPTIONAL_FIELDS = frozenset({"options"})


def _covers(table_tag: str, tag: str) -> bool:
    """Whether a Table E.1-1 tag covers a dictionary tag.

    An "x" in the table's tag stands for any hexadecimal digit, so
    "(50xx,xxxx)" covers every attribute of the retired Curve group, such as
    "(50xx,2500)". Only tags of the form "(gggg,eeee)" are compared, so the
    private attributes row, "(gggg,eeee) where gggg is odd", covers none.
    """
    return len(table_tag) == len(tag) == len("(gggg,eeee)") and all(
        expected in ("x", found) for expected, found in zip(table_tag, tag)
    )


def _listed(table: ProfileTable, tags) -> frozenset[str]:
    """Return the dictionary tags that Table E.1-1 lists, exactly or masked."""
    exact = {row.tag for row in table.attributes}
    masked = [tag for tag in exact if "x" in tag]
    return frozenset(
        tag
        for tag in tags
        if tag in exact or any(_covers(pattern, tag) for pattern in masked)
    )


class SupplementaryActionError(ValueError):
    """A supplementary actions file that cannot be used."""


@dataclasses.dataclass(frozen=True)
class SupplementaryAction:
    """One attribute's supplementary action.

    Attributes
    ----------
    tag, keyword : str
        As the pinned data dictionary gives them.
    action : str
        The Basic Profile action, an action code of Table E.1-1a, such as
        ``"X/Z/D"`` or ``"K"``.
    note : str
        Why the attribute has its action.
    options : Mapping of str to str
        The action under each option that gives one, which overrides
        :attr:`action` when the option is selected, such as
        ``{"clean_descriptors": "C"}``, as in Table E.1-1. Usually empty.
        Read-only.
    """

    tag: str
    keyword: str
    action: str
    note: str
    # A mapping is not hashable, so it is left out of the hash.
    options: Mapping[str, str] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({}), hash=False
    )


@dataclasses.dataclass(frozen=True)
class SupplementaryActions:
    """The supplementary actions, keyed by tag.

    Attributes
    ----------
    edition : str
        The edition of the data dictionary and Table E.1-1 that the actions
        cover.
    acknowledgement : str
        ``"DICOM PS3.6 <edition>, © NEMA"``.
    rules : mapping of str to SupplementaryAction
        Read-only.
    """

    edition: str
    acknowledgement: str
    # A mapping is not hashable, so it is left out of the hash.
    rules: Mapping[str, SupplementaryAction] = dataclasses.field(hash=False)


def _attribute_problem(
    tag: object, keyword: object, dictionary, listed: frozenset[str]
) -> str | None:
    if not isinstance(tag, str) or tag not in dictionary:
        return "is not an attribute of the data dictionary"
    if keyword != dictionary[tag].keyword:
        return "names its attribute differently from the data dictionary"
    if tag in listed:
        return "is listed in Table E.1-1, whose action it must not change"
    if _ROLES_ONLY_VRS.intersection(dictionary[tag].vrs):
        return "is a UI attribute, which the UID roles file covers"
    return None


def _option_problem(option: str, given: object) -> str | None:
    """Return what is wrong with a rule's action under one option, or None."""
    if option not in OPTIONS:
        return f"has an option that Table E.1-1 does not define: {option}"
    if not isinstance(given, str) or given not in ACTION_CODES:
        return "has an option action not defined in Table E.1-1a"
    if option not in OPTION_ACTIONS:
        *others, last = OPTION_ACTIONS
        return (
            f"gives an action under {option}; a rule may give one only under "
            f"{', '.join(others)}, or {last}"
        )
    if given != OPTION_ACTIONS[option]:
        return f"gives {option} an action other than {OPTION_ACTIONS[option]}"
    return None


def _exclusive(first: str, second: str) -> bool:
    """Whether PS3.15 makes two options mutually exclusive."""
    return any({first, second} <= options for options in MUTUALLY_EXCLUSIVE)


def _options_problem(options: object, action: str, vrs: tuple[str, ...]) -> str | None:
    """Return what is wrong with a rule's option actions, or None."""
    if not isinstance(options, dict) or not options:
        return "has options that are not a table of option actions"
    problem = next(
        filter(None, (_option_problem(o, given) for o, given in options.items())),
        None,
    )
    if problem:
        return problem
    if any(
        options[first] != options[second] and not _exclusive(first, second)
        for first, second in itertools.combinations(options, 2)
    ):
        return (
            "gives different actions under two or more options that can be "
            "selected together, between which PS3.15 defines no precedence"
        )
    if action not in _REMOVING:
        return "has an option action, but its Basic Profile action keeps the value"
    for option in options:
        allowed, kind = _OPTION_ATTRIBUTES[option]
        if not allowed.intersection(vrs):
            return f"has an option action under {option}, but is not {kind}"
    return None


def _rule_problem(entry: object, dictionary, listed: frozenset[str]) -> str | None:
    if not isinstance(entry, dict) or not (
        _FIELDS <= entry.keys() <= _FIELDS | _OPTIONAL_FIELDS
    ):
        return (
            "does not have exactly the fields tag, keyword, action, and note, "
            "and optionally options"
        )
    problem = _attribute_problem(entry["tag"], entry["keyword"], dictionary, listed)
    if problem:
        return problem
    if not isinstance(entry["action"], str) or entry["action"] not in ACTION_CODES:
        return "has an action not defined in Table E.1-1a"
    note = entry["note"]
    if not (isinstance(note, str) and note.strip()):
        return "has a note that is not non-empty text"
    if "options" in entry:
        return _options_problem(
            entry["options"], entry["action"], dictionary[entry["tag"]].vrs
        )
    return None


def _supported_text(dictionary, listed: frozenset[str]) -> set[str]:
    """Return the text attributes that a supported IOD uses and the table omits."""
    tables = load_iod_tables()
    return {
        definition.tag
        for name in SUPPORTED_IODS
        for definition in tables.iods[name].definitions
        if definition.tag in dictionary
        and TEXT_VRS.intersection(dictionary[definition.tag].vrs)
        and definition.tag not in listed
    }


def load_supplementary_actions(
    path: pathlib.Path | None = None,
) -> SupplementaryActions:
    """Load the supplementary actions.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The actions file. Defaults to the one shipped with PyMedPhys.

    Raises
    ------
    SupplementaryActionError
        If the file cannot be read; has another schema; covers another
        edition than the data dictionary, Table E.1-1, and the IOD tables, or
        lacks its acknowledgement; does not give its rules as an array of
        tables; has a rule without exactly the fields tag, keyword, action,
        and note, and optionally options; has a rule for an attribute that is
        not in the data dictionary, with another keyword, that Table E.1-1
        lists (exactly or by a masked tag, as it lists the Curve group), or
        that is a UI attribute; has an action not defined in Table E.1-1a, or
        an empty note; has options that are not a non-empty table, or that
        name an option Table E.1-1 does not define, give an action not
        defined in Table E.1-1a, give an action other than those in
        :data:`OPTION_ACTIONS`, or give different actions under two options
        that are not mutually exclusive; has options on a rule whose Basic
        Profile action keeps the value, or an option action for an attribute
        that the option does not apply to (text for Clean Descriptors and
        Retain Device Identity, a date, time, or datetime for the Retain
        Longitudinal Temporal Information Options); repeats a tag; or has no
        action for a person name, date, time, or datetime that Table E.1-1
        omits, or for a text attribute that it omits and a supported IOD uses.
    """
    return _load((path or SUPPLEMENTARY_ACTIONS_PATH).resolve())


@functools.lru_cache(maxsize=None)
def _load(path: pathlib.Path) -> SupplementaryActions:
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except (OSError, ValueError, tomlkit.exceptions.TOMLKitError) as error:
        raise SupplementaryActionError(f"{path.name} could not be read") from error
    if document.get("schema") != SCHEMA:
        raise SupplementaryActionError(f"{path.name} is not a {SCHEMA} file (schema)")
    dictionary = load_data_dictionary()
    table = load_table_e1_1()
    editions = (table.edition, load_iod_tables().edition, document.get("edition"))
    if any(edition != dictionary.edition for edition in editions):
        raise SupplementaryActionError(
            f"{path.name} does not cover the edition of the data dictionary, "
            f"Table E.1-1, and the IOD tables, {dictionary.edition}"
        )
    acknowledgement = f"DICOM PS3.6 {dictionary.edition}, © NEMA"
    if document.get("acknowledgement") != acknowledgement:
        raise SupplementaryActionError(
            f"{path.name} lacks the acknowledgement {acknowledgement}"
        )

    attributes = {attribute.tag: attribute for attribute in dictionary.attributes}
    listed = _listed(table, attributes)
    entries = document.get("attribute", [])
    if not isinstance(entries, list):
        raise SupplementaryActionError(f"{path.name} rules are not an array of tables")
    rules: dict[str, SupplementaryAction] = {}
    for number, entry in enumerate(entries, start=1):
        problem = _rule_problem(entry, attributes, listed)
        if problem:
            raise SupplementaryActionError(f"{path.name} rule {number} {problem}")
        if entry["tag"] in rules:
            raise SupplementaryActionError(
                f"{path.name} rule {number} repeats {entry['tag']}"
            )
        options = types.MappingProxyType(dict(entry.get("options", {})))
        fields = {name: entry[name] for name in _FIELDS}
        rules[entry["tag"]] = SupplementaryAction(**fields, options=options)

    covered = _supported_text(attributes, listed) | {
        tag
        for tag, attribute in attributes.items()
        if COVERED_VRS.intersection(attribute.vrs) and tag not in listed
    }
    missing = sorted(covered.difference(rules))
    if missing:
        raise SupplementaryActionError(
            f"{path.name} has no action for " + ", ".join(missing)
        )
    return SupplementaryActions(
        edition=dictionary.edition,
        acknowledgement=acknowledgement,
        rules=types.MappingProxyType(rules),
    )
