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

"""The role of every UI attribute, a supplementary (L2) rule.

``uid_roles.toml`` gives each UI attribute of the pinned PS3.6 data dictionary
one role, curated by hand. An ``instance`` attribute identifies an instance,
event, entity, device, or organisation; a ``definition`` attribute identifies
something a standard or vendor publishes, such as a SOP Class or transfer
syntax. :func:`~pymedphys._dicom.deidentify.uids.transform_uid` applies the
role to a value. A UI attribute without a role is rejected, never replaced
merely because of its VR.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import pathlib
import types
from collections.abc import Mapping

from pymedphys._imports import tomlkit

from .standard import load_data_dictionary

SCHEMA = "pymedphys-deid-uid-roles/1"
UID_ROLES_PATH = pathlib.Path(__file__).resolve().parent / "uid_roles.toml"
_FIELDS = frozenset({"tag", "keyword", "role"})


class UIDRoleError(ValueError):
    """A roles file, or a lookup, that cannot be used."""


class UIDRole(enum.Enum):
    """What a UI attribute identifies."""

    INSTANCE = "instance"
    DEFINITION = "definition"


@dataclasses.dataclass(frozen=True)
class UIDRule:
    """One UI attribute's role.

    Attributes
    ----------
    tag, keyword : str
        As the pinned data dictionary gives them.
    role : UIDRole
    note : str
        Why the attribute has its role, or ``""`` for an instance UID that
        Table E.1-1 replaces.
    """

    tag: str
    keyword: str
    role: UIDRole
    note: str


@dataclasses.dataclass(frozen=True)
class UIDRoles:
    """The roles of every UI attribute, keyed by tag.

    Attributes
    ----------
    edition : str
        The edition of the data dictionary the roles cover.
    acknowledgement : str
        ``"DICOM PS3.6 <edition>, © NEMA"``.
    rules : mapping of str to UIDRule
    """

    edition: str
    acknowledgement: str
    rules: Mapping[str, UIDRule]

    def role(self, tag: str) -> UIDRole:
        """Return the role of the UI attribute with ``tag``, such as ``"(0008,0018)"``.

        Raises
        ------
        UIDRoleError
            If the attribute has no role.
        """
        try:
            return self.rules[tag].role
        except KeyError:
            raise UIDRoleError("the attribute has no role") from None


def _rule_problem(entry: object, ui: Mapping[str, str]) -> str | None:
    if not isinstance(entry, dict) or not (
        _FIELDS <= entry.keys() <= _FIELDS | {"note"}
    ):
        return "does not have exactly the fields tag, keyword, role, and note"
    if not isinstance(entry["tag"], str) or entry["tag"] not in ui:
        return "is not a UI attribute of the data dictionary"
    if entry["keyword"] != ui[entry["tag"]]:
        return "names its attribute differently from the data dictionary"
    if not isinstance(entry["role"], str) or entry["role"] not in {
        role.value for role in UIDRole
    }:
        return "has a role that is not instance or definition"
    note = entry.get("note")
    if note is not None and not (isinstance(note, str) and note.strip()):
        return "has a note that is not non-empty text"
    return None


def load_uid_roles(path: pathlib.Path | None = None) -> UIDRoles:
    """Load the role of every UI attribute.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The roles file. Defaults to the one shipped with PyMedPhys.

    Raises
    ------
    UIDRoleError
        If the file cannot be read; has another schema; covers another
        edition than the data dictionary or lacks its acknowledgement; does
        not give its rules as an array of tables; has a rule without exactly
        the fields tag, keyword, role, and an optional non-empty note; has a
        rule for an attribute that is not a UI attribute of the data
        dictionary, or with another keyword; has a role other than
        ``instance`` or ``definition``; repeats a tag; or has no role for a
        UI attribute of the data dictionary.
    """
    return _load_uid_roles((path or UID_ROLES_PATH).resolve())


@functools.lru_cache(maxsize=None)
def _load_uid_roles(path: pathlib.Path) -> UIDRoles:
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except (OSError, ValueError, tomlkit.exceptions.TOMLKitError) as error:
        raise UIDRoleError(f"{path.name} could not be read") from error
    if document.get("schema") != SCHEMA:
        raise UIDRoleError(f"{path.name} is not a {SCHEMA} file (schema)")
    dictionary = load_data_dictionary()
    if document.get("edition") != dictionary.edition:
        raise UIDRoleError(
            f"{path.name} does not cover the data dictionary's edition, "
            f"{dictionary.edition}"
        )
    acknowledgement = f"DICOM PS3.6 {dictionary.edition}, © NEMA"
    if document.get("acknowledgement") != acknowledgement:
        raise UIDRoleError(f"{path.name} lacks the acknowledgement {acknowledgement}")

    ui = {a.tag: a.keyword for a in dictionary.attributes if a.vr == "UI"}
    attributes = document.get("attribute", [])
    if not isinstance(attributes, list):
        raise UIDRoleError(f"{path.name} rules are not an array of tables")
    rules: dict[str, UIDRule] = {}
    for number, entry in enumerate(attributes, start=1):
        problem = _rule_problem(entry, ui)
        if problem:
            raise UIDRoleError(f"{path.name} rule {number} {problem}")
        if entry["tag"] in rules:
            raise UIDRoleError(f"{path.name} rule {number} repeats {entry['tag']}")
        rules[entry["tag"]] = UIDRule(
            tag=entry["tag"],
            keyword=entry["keyword"],
            role=UIDRole(entry["role"]),
            note=entry.get("note", ""),
        )
    missing = sorted(set(ui) - set(rules))
    if missing:
        raise UIDRoleError(f"{path.name} has no role for " + ", ".join(missing))
    return UIDRoles(
        edition=dictionary.edition,
        acknowledgement=acknowledgement,
        rules=types.MappingProxyType(rules),
    )
