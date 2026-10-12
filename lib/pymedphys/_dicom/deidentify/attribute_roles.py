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

"""Supplementary (L2) rules that give attributes of some VRs a role.

A roles file is TOML, curated by hand, for one edition of the pinned PS3.6
data dictionary. It gives every attribute of the VRs it covers, and of any
other attribute that Table E.1-1 cleans under a given option, exactly one role,
with a note where the reason is not obvious. The UI roles
(:mod:`~pymedphys._dicom.deidentify.uid_roles`) and the date, time, and
datetime roles (:mod:`~pymedphys._dicom.deidentify.temporal_roles`) share this
format and loader. An attribute without a role is rejected, never handled
merely because of its VR.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import pathlib
import types
from collections.abc import Mapping
from typing import Generic, TypeVar

from pymedphys._imports import tomlkit

from .standard import load_data_dictionary, load_table_e1_1

RoleT = TypeVar("RoleT", bound=enum.Enum)

_FIELDS = frozenset({"tag", "keyword", "role"})


class RoleError(ValueError):
    """A roles file, or a lookup, that cannot be used."""


@dataclasses.dataclass(frozen=True)
class RoleFormat(Generic[RoleT]):
    """What one kind of roles file covers.

    Attributes
    ----------
    schema : str
        The file's schema, such as ``"pymedphys-deid-uid-roles/1"``.
    vrs : frozenset of str
        The VRs whose dictionary attributes each need a role.
    role : type
        The enumeration of roles, whose values the file uses.
    cleaned_under : str, optional
        A Table E.1-1 option, such as ``"retain_longitudinal_modified_dates"``.
        Every attribute that the table cleans (C) under it also needs a role,
        whatever its VR.
    """

    schema: str
    vrs: frozenset[str]
    role: type[RoleT]
    cleaned_under: str | None = None

    def covers(self) -> str:
        """Describe the attributes that need a role, for messages."""
        vrs = f"a {_either(sorted(self.vrs))} attribute of the data dictionary"
        if self.cleaned_under is None:
            return vrs
        return f"{vrs}, or one that Table E.1-1 cleans under {self.cleaned_under}"


@dataclasses.dataclass(frozen=True)
class AttributeRule(Generic[RoleT]):
    """One attribute's role.

    Attributes
    ----------
    tag, keyword : str
        As the pinned data dictionary gives them.
    role : enum.Enum
    note : str
        Why the attribute has its role, or ``""`` where the file's header
        says no note is needed.
    """

    tag: str
    keyword: str
    role: RoleT
    note: str


@dataclasses.dataclass(frozen=True)
class AttributeRoles(Generic[RoleT]):
    """The roles of every attribute a roles file covers, keyed by tag.

    Attributes
    ----------
    edition : str
        The edition of the data dictionary the roles cover.
    acknowledgement : str
        ``"DICOM PS3.6 <edition>, © NEMA"``.
    rules : mapping of str to AttributeRule
    """

    edition: str
    acknowledgement: str
    rules: Mapping[str, AttributeRule[RoleT]]

    def role(self, tag: str) -> RoleT:
        """Return the role of the attribute with ``tag``, such as ``"(0008,0018)"``.

        Raises
        ------
        RoleError
            If the attribute has no role.
        """
        try:
            return self.rules[tag].role
        except KeyError:
            raise RoleError("the attribute has no role") from None


def _either(values: list[str]) -> str:
    """Join ``values`` as prose: ``"a"``, ``"a or b"``, or ``"a, b, or c"``."""
    if len(values) <= 2:
        return " or ".join(values)
    return ", ".join(values[:-1]) + ", or " + values[-1]


def _rule_problem(
    entry: object, attributes: Mapping[str, str], role_format: RoleFormat
) -> str | None:
    if not isinstance(entry, dict) or not (
        _FIELDS <= entry.keys() <= _FIELDS | {"note"}
    ):
        return "does not have exactly the fields tag, keyword, role, and note"
    if not isinstance(entry["tag"], str) or entry["tag"] not in attributes:
        return f"is not {role_format.covers()}"
    if entry["keyword"] != attributes[entry["tag"]]:
        return "names its attribute differently from the data dictionary"
    values = [role.value for role in role_format.role]
    if not isinstance(entry["role"], str) or entry["role"] not in values:
        return f"has a role that is not {_either(values)}"
    note = entry.get("note")
    if note is not None and not (isinstance(note, str) and note.strip()):
        return "has a note that is not non-empty text"
    return None


def _covered(role_format: RoleFormat, attributes) -> dict[str, str]:
    """Return the keyword of every attribute that needs a role, by tag."""
    cleaned: set[str] = set()
    if role_format.cleaned_under is not None:
        cleaned = {
            row.tag
            for row in load_table_e1_1().attributes
            if row.options.get(role_format.cleaned_under) == "C"
        }
    return {
        a.tag: a.keyword
        for a in attributes
        if a.vr in role_format.vrs or a.tag in cleaned
    }


def load_attribute_roles(
    role_format: RoleFormat[RoleT], path: pathlib.Path
) -> AttributeRoles[RoleT]:
    """Load a roles file of the given format.

    Each file is read once and cached, keyed by its format and resolved path.

    Raises
    ------
    RoleError
        If the file cannot be read; has another schema; covers another
        edition than the data dictionary or lacks its acknowledgement; does
        not give its rules as an array of tables; has a rule without exactly
        the fields tag, keyword, role, and an optional non-empty note; has a
        rule for an attribute that the format does not cover, or with
        another keyword than the data dictionary gives; has a role the
        format does not define; repeats a tag; or has no role for an
        attribute that the format covers.
    """
    return _load_attribute_roles(role_format, path.resolve())


@functools.lru_cache(maxsize=None)
def _load_attribute_roles(
    role_format: RoleFormat[RoleT], path: pathlib.Path
) -> AttributeRoles[RoleT]:
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except (OSError, ValueError, tomlkit.exceptions.TOMLKitError) as error:
        raise RoleError(f"{path.name} could not be read") from error
    if document.get("schema") != role_format.schema:
        raise RoleError(f"{path.name} is not a {role_format.schema} file (schema)")
    dictionary = load_data_dictionary()
    if document.get("edition") != dictionary.edition:
        raise RoleError(
            f"{path.name} does not cover the data dictionary's edition, "
            f"{dictionary.edition}"
        )
    acknowledgement = f"DICOM PS3.6 {dictionary.edition}, © NEMA"
    if document.get("acknowledgement") != acknowledgement:
        raise RoleError(f"{path.name} lacks the acknowledgement {acknowledgement}")

    covered = _covered(role_format, dictionary.attributes)
    entries = document.get("attribute", [])
    if not isinstance(entries, list):
        raise RoleError(f"{path.name} rules are not an array of tables")
    rules: dict[str, AttributeRule[RoleT]] = {}
    for number, entry in enumerate(entries, start=1):
        problem = _rule_problem(entry, covered, role_format)
        if problem:
            raise RoleError(f"{path.name} rule {number} {problem}")
        if entry["tag"] in rules:
            raise RoleError(f"{path.name} rule {number} repeats {entry['tag']}")
        rules[entry["tag"]] = AttributeRule(
            tag=entry["tag"],
            keyword=entry["keyword"],
            role=role_format.role(entry["role"]),
            note=entry.get("note", ""),
        )
    missing = sorted(set(covered) - set(rules))
    if missing:
        raise RoleError(f"{path.name} has no role for " + ", ".join(missing))
    return AttributeRoles(
        edition=dictionary.edition,
        acknowledgement=acknowledgement,
        rules=types.MappingProxyType(rules),
    )
