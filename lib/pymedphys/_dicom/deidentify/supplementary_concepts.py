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

"""Supplementary rows for content items whose concepts Table E.3.4-1 omits.

The Clean Structured Content Option removes the information in content items
"corresponding to the Attribute information specified to be removed by the
Profile and any other Options specified" (PS3.15 E.3.4), and Table E.3.4-1
names the concepts that carry it (:mod:`.structured_content`). A content item
whose concept the table does not list keeps its codes and numbers
(:mod:`.content_items`), so where PS3.16's templates code a characteristic
that Table E.1-1 removes under a concept that the table omits, the item would
keep it. ``supplementary_concepts.toml``, curated by hand for one edition of
PS3.16, gives such concepts a row, as ``supplementary_actions.toml`` gives
rules to attributes that Table E.1-1 omits (D-022), each with a note that
says why:

- the patient characteristics that Table E.1-1 keeps only under Retain
  Patient Characteristics, as codes or text: coded patient state, the sex
  parameters for clinical use, racial group, pregnancy, and smoking, each
  removed (X), and kept (K) under that option, except the free-text comment
  on the sex parameters, which Table E.1-1 cleans (C) and which is removed
  under every option, since no cleaner of content items settles C;
- Body Mass Index, removed under every option, as the reviewed rules remove
  Patient's Body Mass Index (0010,1022);
- a UDI as a CODE, as TID 11004 row 26 and TID 11005 row 17 give it,
  removed (X), and kept (K) under Retain Device Identity, as Table E.1-1
  treats UDI Sequence (0018,100A) and Unique Device Identifier (0018,1009);
  and
- Subject ID as a CODE, as TID 1007 row 3 gives it, removed under every
  option. Table E.3.4-1 lists Subject ID only as TEXT, and of the concepts
  that PS3.16 2026d's templates use with a Value Type that the table does not
  list for them, it is the only one whose value there holds what the listed
  row removes or replaces (D-047).

A row has the fields of a row of Table E.3.4-1 that the engine reads: a
concept name, by its Coding Scheme Designator and Code Value, a Value Type,
and the actions of the Basic Profile and of each option. A row never covers a
concept and Value Type that the table lists, so it never changes an action
that the table gives.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import types
from collections.abc import Mapping

from pymedphys._imports import tomlkit

from .codes import CODE_MEANING_MAX_LENGTH, CODE_VALUE_MAX_LENGTH
from .structured_content import (
    VALUE_TYPES,
    is_code_text,
    is_designator,
    load_table_e3_4_1,
)

SCHEMA = "pymedphys-deid-supplementary-concepts/1"
SUPPLEMENTARY_CONCEPTS_PATH = (
    pathlib.Path(__file__).resolve().parent / "supplementary_concepts.toml"
)
# The Basic Profile action that a row may give: removal.
BASIC_PROFILE_ACTIONS = frozenset({"X"})
# The action that each option may give, overriding the Basic Profile action:
# Retain Patient Characteristics keeps (K) a characteristic, and Retain Device
# Identity a device's identifier, as Table E.1-1 keeps the attribute that
# holds it.
OPTION_ACTIONS: Mapping[str, str] = types.MappingProxyType(
    {"retain_patient_characteristics": "K", "retain_device_identity": "K"}
)
_FIELDS = frozenset(
    {
        "scheme_designator",
        "code_value",
        "value_type",
        "code_meaning",
        "basic_profile",
        "note",
    }
)
_OPTIONAL_FIELDS = frozenset({"options"})


class SupplementaryConceptError(ValueError):
    """A supplementary concepts file that cannot be used."""


@dataclasses.dataclass(frozen=True)
class SupplementaryConcept:
    """One supplementary row for a content item's concept.

    Attributes
    ----------
    scheme_designator, code_value : str
        The concept name's Coding Scheme Designator (0008,0102) and Code
        Value (0008,0100), such as ``"SCT"`` and ``"60621009"``.
    value_type : str
        The content item's Value Type (0040,A040), one of
        :data:`~.structured_content.VALUE_TYPES`.
    code_meaning : str
        As PS3.16's templates give it, such as ``"Body Mass Index"``.
    basic_profile : str
        The Basic Profile action, ``"X"``.
    note : str
        Why the concept has its actions.
    options : Mapping of str to str
        The action under each option that gives one, as in
        :attr:`~.structured_content.ContentItemConcept.options`. Read-only.
    """

    scheme_designator: str
    code_value: str
    value_type: str
    code_meaning: str
    basic_profile: str
    note: str
    # A mapping is not hashable, so it is left out of the hash.
    options: Mapping[str, str] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({}), hash=False
    )

    @property
    def key(self) -> tuple[str, str, str]:
        """The coding scheme designator, code value, and value type."""
        return (self.scheme_designator, self.code_value, self.value_type)


@dataclasses.dataclass(frozen=True)
class SupplementaryConcepts:
    """The supplementary rows for one edition of PS3.16.

    Attributes
    ----------
    edition : str
        The edition of PS3.16 whose templates the rows cover, which is the
        edition of Table E.3.4-1 too.
    acknowledgement : str
        ``"DICOM PS3.16 <edition>, © NEMA"``.
    concepts : tuple of SupplementaryConcept
        In the file's order.
    """

    edition: str
    acknowledgement: str
    concepts: tuple[SupplementaryConcept, ...]


def _options_problem(options: object) -> str | None:
    if not isinstance(options, dict) or not options:
        return "has options that are not a table of option actions"
    for option, action in options.items():
        if option not in OPTION_ACTIONS:
            return (
                f"gives an action under {option}; a row may give one only "
                f"under {', '.join(OPTION_ACTIONS)}"
            )
        if action != OPTION_ACTIONS[option]:
            return f"gives {option} an action other than {OPTION_ACTIONS[option]}"
    return None


def _row_problem(entry: object, listed: frozenset) -> str | None:
    """Return what is wrong with a row, or None if it is valid."""
    if not isinstance(entry, dict) or not (
        _FIELDS <= entry.keys() <= _FIELDS | _OPTIONAL_FIELDS
    ):
        return (
            "does not have exactly the fields scheme_designator, code_value, "
            "value_type, code_meaning, basic_profile, and note, and "
            "optionally options"
        )
    checks = (
        (is_designator(entry["scheme_designator"]), "a coding scheme designator"),
        (
            is_code_text(entry["code_value"], CODE_VALUE_MAX_LENGTH),
            "a code value of at most 16 characters",
        ),
        (
            isinstance(entry["value_type"], str) and entry["value_type"] in VALUE_TYPES,
            "a value type that PS3.3 defines",
        ),
        (
            is_code_text(entry["code_meaning"], CODE_MEANING_MAX_LENGTH),
            "a code meaning of at most 64 characters",
        ),
        (
            isinstance(entry["basic_profile"], str)
            and entry["basic_profile"] in BASIC_PROFILE_ACTIONS,
            "X as its Basic Profile action",
        ),
        (
            isinstance(entry["note"], str) and bool(entry["note"].strip()),
            "a note that is non-empty text",
        ),
    )
    for passed, wanted in checks:
        if not passed:
            return f"does not have {wanted}"
    if "options" in entry:
        problem = _options_problem(entry["options"])
        if problem:
            return problem
    key = (entry["scheme_designator"], entry["code_value"], entry["value_type"])
    if key in listed:
        return "is listed in Table E.3.4-1, whose action it must not change"
    return None


def load_supplementary_concepts(
    path: pathlib.Path | None = None,
) -> SupplementaryConcepts:
    """Load the supplementary rows for content items' concepts.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The rows file. Defaults to the one shipped with PyMedPhys.

    Raises
    ------
    SupplementaryConceptError
        If the file cannot be read; has another schema; covers another
        edition than Table E.3.4-1, or lacks its acknowledgement; does not
        give its rows as an array of tables; has a row without exactly the
        fields scheme_designator, code_value, value_type, code_meaning,
        basic_profile, and note, and optionally options; has a row whose
        designator, code value, value type, or code meaning is not one that
        Table E.3.4-1 could give, whose Basic Profile action is not X, or
        whose note is empty; has options that are not a non-empty table, or
        that give an action other than those in :data:`OPTION_ACTIONS`; has
        a row for a concept and Value Type that Table E.3.4-1 lists; or
        repeats a concept and Value Type.
    """
    return _load((path or SUPPLEMENTARY_CONCEPTS_PATH).resolve())


@functools.lru_cache(maxsize=None)
def _load(path: pathlib.Path) -> SupplementaryConcepts:
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except (OSError, ValueError, tomlkit.exceptions.TOMLKitError) as error:
        raise SupplementaryConceptError(f"{path.name} could not be read") from error
    if document.get("schema") != SCHEMA:
        raise SupplementaryConceptError(f"{path.name} is not a {SCHEMA} file (schema)")
    table = load_table_e3_4_1()
    if document.get("edition") != table.edition:
        raise SupplementaryConceptError(
            f"{path.name} does not cover the edition of Table E.3.4-1, {table.edition}"
        )
    acknowledgement = f"DICOM PS3.16 {table.edition}, © NEMA"
    if document.get("acknowledgement") != acknowledgement:
        raise SupplementaryConceptError(
            f"{path.name} lacks the acknowledgement {acknowledgement}"
        )
    entries = document.get("concept", [])
    if not isinstance(entries, list):
        raise SupplementaryConceptError(f"{path.name} rows are not an array of tables")
    listed = frozenset(concept.key for concept in table.concepts)
    concepts: dict[tuple[str, str, str], SupplementaryConcept] = {}
    for number, entry in enumerate(entries, start=1):
        problem = _row_problem(entry, listed)
        if problem:
            raise SupplementaryConceptError(f"{path.name} row {number} {problem}")
        options = types.MappingProxyType(dict(entry.get("options", {})))
        concept = SupplementaryConcept(
            **{name: entry[name] for name in _FIELDS}, options=options
        )
        if concept.key in concepts:
            raise SupplementaryConceptError(
                f"{path.name} row {number} repeats {', '.join(concept.key)}"
            )
        concepts[concept.key] = concept
    return SupplementaryConcepts(
        edition=table.edition,
        acknowledgement=acknowledgement,
        concepts=tuple(concepts.values()),
    )
