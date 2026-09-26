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
The tables are "DICOM PS3.15, © NEMA"; ``_standard/LICENSE-NEMA-DICOM`` holds
NEMA's notices for them.
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
        The acknowledgement of the table's source, such as
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
        raise StandardTableError(f"{path.name} lacks the NEMA acknowledgement")
    if content_sha256(document.get("rows", [])) != document.get("content_sha256"):
        raise StandardTableError(
            f"{path.name} rows do not match their recorded digest; "
            "regenerate the tables with pymedphys dev deid-tables"
        )
    return document


def load_table_e1_1(path: pathlib.Path | None = None) -> ProfileTable:
    """Load Table E.1-1 of DICOM PS3.15, as generated from the pinned edition.

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
        NEMA acknowledgement, or has rows that do not match its recorded
        digest.
    """
    return _load_table_e1_1(path or STANDARD_DIR / "e1_1.json")


@functools.lru_cache(maxsize=None)
def _load_table_e1_1(path: pathlib.Path) -> ProfileTable:
    document = _read(path, "PS3.15 Table E.1-1")
    try:
        attributes = tuple(
            ProfileAttribute(
                name=row["name"],
                tag=row["tag"],
                retired=row["retired"],
                in_standard_iod=row["in_standard_iod"],
                basic_profile=row["basic_profile"],
                options=types.MappingProxyType(dict(row["options"])),
            )
            for row in document["rows"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise StandardTableError(f"{path.name} has a malformed row") from error
    return ProfileTable(
        edition=document["edition"],
        acknowledgement=document["acknowledgement"],
        attributes=attributes,
    )
