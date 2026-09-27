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

"""Load the rule tables generated from the DICOM standard.

``pymedphys dev deid-tables`` generates the tables in ``_standard/`` from the
pinned edition of DICOM PS3.15 (design decision D-001). They are never edited
by hand, so a table whose rows do not match its recorded digest is rejected.
Each table carries the copyright attribution
"DICOM PS3.15 <edition>, © NEMA".
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import pathlib
import types
from collections.abc import Mapping, Sequence

SCHEMA = "pymedphys-deid-table/1"

# Complete action codes from Table E.1-1a. Compound codes have defined
# meanings; other combinations, including "U*" alone, are not defined.
ACTION_CODES = frozenset(
    {"D", "Z", "X", "K", "C", "U", "Z/D", "X/Z", "X/D", "X/Z/D", "X/Z/U*"}
)

# The option columns of Table E.1-1, in the table's order.
OPTIONS = (
    "retain_safe_private",
    "retain_uids",
    "retain_device_identity",
    "retain_institution_identity",
    "retain_patient_characteristics",
    "retain_longitudinal_full_dates",
    "retain_longitudinal_modified_dates",
    "clean_descriptors",
    "clean_structured_content",
    "clean_graphics",
)

_ROW_FIELDS = frozenset(
    {"name", "tag", "retired", "in_standard_iod", "basic_profile", "options"}
)

STANDARD_DIR = pathlib.Path(__file__).resolve().parent / "_standard"


class StandardTableError(ValueError):
    """A generated table is missing, malformed, or altered since generation."""


@dataclasses.dataclass(frozen=True)
class ProfileAttribute:
    """One row of DICOM PS3.15 Table E.1-1.

    Attributes
    ----------
    name : str
        The attribute name, as the table gives it.
    tag : str
        The tag in the form ``(gggg,eeee)``, where ``x`` may stand for any
        hexadecimal digit, or ``"(gggg,eeee) where gggg is odd"`` for the row
        covering every private attribute.
    retired : bool
        Whether PS3.6 lists the attribute as retired.
    in_standard_iod : bool
        Whether PS3.3 uses the attribute in a standard composite IOD.
    basic_profile : str
        The Basic Profile action, one of the codes in Table E.1-1a, such as
        ``"X"`` or ``"X/Z/D"``.
    options : Mapping of str to str
        The action for each option that gives one, keyed by option names such
        as ``"retain_uids"``. Options with no action are omitted. The mapping
        is read-only.
    """

    name: str
    tag: str
    retired: bool
    in_standard_iod: bool
    basic_profile: str
    # A mapping is not hashable, so it is left out of the hash.
    options: Mapping[str, str] = dataclasses.field(hash=False)


@dataclasses.dataclass(frozen=True)
class ProfileTable:
    """Table E.1-1 as generated from one edition of the standard.

    Attributes
    ----------
    edition : str
        The edition of DICOM PS3.15, such as ``"2026d"``.
    acknowledgement : str
        The copyright attribution for the table's source, such as
        ``"DICOM PS3.15 2026d, © NEMA"``.
    attributes : tuple of ProfileAttribute
        One per row, in the table's order.
    """

    edition: str
    acknowledgement: str
    attributes: tuple[ProfileAttribute, ...]


def content_sha256(rows: Sequence[Mapping[str, object]]) -> str:
    """Return the SHA-256 of rows in canonical JSON.

    Keys are sorted, separators carry no whitespace, and text is UTF-8, so
    the digest does not depend on how the table file is laid out.
    """
    canonical = json.dumps(
        rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read(path: pathlib.Path, table: str) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StandardTableError(f"{path.name} could not be read") from error
    if not isinstance(document, dict):
        raise StandardTableError(f"{path.name} is not a {SCHEMA} file")
    if document.get("schema") != SCHEMA or document.get("table") != table:
        raise StandardTableError(f"{path.name} is not a {SCHEMA} file for {table}")
    edition = document.get("edition")
    if document.get("acknowledgement") != f"DICOM PS3.15 {edition}, © NEMA":
        raise StandardTableError(f"{path.name} lacks the copyright acknowledgement")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise StandardTableError(f"{path.name} has no rows")
    if content_sha256(rows) != document.get("content_sha256"):
        raise StandardTableError(
            f"{path.name} rows do not match their recorded digest; "
            "regenerate the tables with pymedphys dev deid-tables"
        )
    return document


def _is_action(value: object) -> bool:
    return isinstance(value, str) and value in ACTION_CODES


def _row_problem(row: object) -> str | None:
    """Return what is wrong with a row of Table E.1-1, or None if it is valid."""
    if not isinstance(row, dict) or row.keys() != _ROW_FIELDS:
        return f"does not have exactly the fields {', '.join(sorted(_ROW_FIELDS))}"
    if not all(isinstance(row[field], str) and row[field] for field in ("name", "tag")):
        return "has a name or tag that is not non-empty text"
    if not all(
        isinstance(row[field], bool) for field in ("retired", "in_standard_iod")
    ):
        return "has a retired or in_standard_iod value that is not true or false"
    if not _is_action(row["basic_profile"]):
        return "has a Basic Profile action not defined in Table E.1-1a"
    options = row["options"]
    if not isinstance(options, dict) or not all(
        option in OPTIONS and _is_action(action) for option, action in options.items()
    ):
        return "has an unknown option or an option action not defined in Table E.1-1a"
    return None


def load_table_e1_1(path: pathlib.Path | None = None) -> ProfileTable:
    """Load Table E.1-1 of DICOM PS3.15, as generated from the pinned edition.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    ProfileTable

    Raises
    ------
    StandardTableError
        If the file cannot be read, has another schema or table, lacks the
        copyright acknowledgement, or has rows that do not match its recorded
        digest; if it has no rows or repeats a tag; or if a row does not have
        exactly the expected fields, with non-empty text for the name and
        tag, true or false for the flags, and actions defined in Table
        E.1-1a for the Basic Profile and each known option.
    """
    return _load_table_e1_1((path or STANDARD_DIR / "e1_1.json").resolve())


@functools.lru_cache(maxsize=None)
def _load_table_e1_1(path: pathlib.Path) -> ProfileTable:
    document = _read(path, "PS3.15 Table E.1-1")
    attributes = []
    tags = set()
    for number, row in enumerate(document["rows"], start=1):
        problem = _row_problem(row)
        if problem:
            raise StandardTableError(f"{path.name} row {number} {problem}")
        if row["tag"] in tags:
            raise StandardTableError(f"{path.name} row {number} repeats a tag")
        tags.add(row["tag"])
        attributes.append(
            ProfileAttribute(
                name=row["name"],
                tag=row["tag"],
                retired=row["retired"],
                in_standard_iod=row["in_standard_iod"],
                basic_profile=row["basic_profile"],
                options=types.MappingProxyType(dict(row["options"])),
            )
        )
    return ProfileTable(
        edition=document["edition"],
        acknowledgement=document["acknowledgement"],
        attributes=tuple(attributes),
    )
