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

The file gives actions only to attributes that the table omits, so it never
changes an action the table gives. UI, DA, DT, and TM attributes are left to
the roles files (:mod:`~pymedphys._dicom.deidentify.uid_roles` and
:mod:`~pymedphys._dicom.deidentify.temporal_roles`), which give each of them a
role. The temporal roles act only under Modified Dates; the Basic Profile
action of a date or time that Table E.1-1 omits, X/Z/D, is to be added here.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import types
from collections.abc import Mapping

from pymedphys._imports import tomlkit

from .standard import (
    ACTION_CODES,
    ProfileTable,
    load_data_dictionary,
    load_table_e1_1,
)

SCHEMA = "pymedphys-deid-supplementary-actions/1"
SUPPLEMENTARY_ACTIONS_PATH = (
    pathlib.Path(__file__).resolve().parent / "supplementary_actions.toml"
)

# Every attribute of these VRs that Table E.1-1 omits needs an action.
COVERED_VRS = frozenset({"PN"})
# The VRs whose attributes the roles files give roles.
_ROLE_VRS = frozenset({"UI", "DA", "DT", "TM"})
_FIELDS = frozenset({"tag", "keyword", "action", "note"})


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
        An action code of Table E.1-1a, such as ``"X/Z/D"`` or ``"K"``.
    note : str
        Why the attribute has its action.
    """

    tag: str
    keyword: str
    action: str
    note: str


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
    if _ROLE_VRS.intersection(dictionary[tag].vrs):
        return "is of a VR that a roles file covers"
    return None


def _rule_problem(entry: object, dictionary, listed: frozenset[str]) -> str | None:
    if not isinstance(entry, dict) or entry.keys() != _FIELDS:
        return "does not have exactly the fields tag, keyword, action, and note"
    problem = _attribute_problem(entry["tag"], entry["keyword"], dictionary, listed)
    if problem:
        return problem
    if not isinstance(entry["action"], str) or entry["action"] not in ACTION_CODES:
        return "has an action not defined in Table E.1-1a"
    note = entry["note"]
    if not (isinstance(note, str) and note.strip()):
        return "has a note that is not non-empty text"
    return None


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
        edition than the data dictionary and Table E.1-1, or lacks its
        acknowledgement; does not give its rules as an array of tables; has a
        rule without exactly the fields tag, keyword, action, and note; has a
        rule for an attribute that is not in the data dictionary, with
        another keyword, that Table E.1-1 lists (exactly or by a masked
        tag, as it lists the Curve group), or of a VR that a roles file
        covers; has an action not defined in Table E.1-1a, or an empty note;
        repeats a tag; or has no action for a person name that Table E.1-1
        omits.
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
    if document.get("edition") != dictionary.edition or table.edition != (
        dictionary.edition
    ):
        raise SupplementaryActionError(
            f"{path.name} does not cover the edition of the data dictionary "
            f"and Table E.1-1, {dictionary.edition}"
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
        rules[entry["tag"]] = SupplementaryAction(**entry)

    missing = sorted(
        tag
        for tag, attribute in attributes.items()
        if COVERED_VRS.intersection(attribute.vrs)
        and tag not in listed
        and tag not in rules
    )
    if missing:
        raise SupplementaryActionError(
            f"{path.name} has no action for " + ", ".join(missing)
        )
    return SupplementaryActions(
        edition=dictionary.edition,
        acknowledgement=acknowledgement,
        rules=types.MappingProxyType(rules),
    )
