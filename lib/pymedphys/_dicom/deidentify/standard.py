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
import re
import types
from collections.abc import Callable, Hashable, Mapping, Sequence

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

# A private Data Element as Table E.3.10-1 gives it, such as "(0019,xx0C)":
# the group, "xx" for the private block, and the element within the block.
# The published table writes some hexadecimal digits in lower case.
PRIVATE_TAG_PATTERN = re.compile(r"\(([0-9A-Fa-f]{4}),xx([0-9A-Fa-f]{2})\)")
# Groups that PS3.5 Section 7.8.1 excludes from private use, although odd.
_RESERVED_ODD_GROUPS = frozenset({0x0001, 0x0003, 0x0005, 0x0007, 0xFFFF})
# A VR, or alternatives such as "OW/OB"; Table E.3.10-1 leaves some empty.
VR_PATTERN = re.compile(r"(?:[A-Z]{2}(?:/[A-Z]{2})*)?")
# A VM such as "1", "1-n", or "3-4".
VM_PATTERN = re.compile(r"[0-9]+(?:-(?:[0-9]+|n))?")

_E1_1_FIELDS = frozenset(
    {"name", "tag", "retired", "in_standard_iod", "basic_profile", "options"}
)
_E1_1A_FIELDS = frozenset({"code", "description"})
_E3_10_1_FIELDS = frozenset({"tag", "private_creator", "vr", "vm", "meaning"})

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


@dataclasses.dataclass(frozen=True)
class ActionCode:
    """One row of DICOM PS3.15 Table E.1-1a.

    Attributes
    ----------
    code : str
        The action code, such as ``"X/Z/D"``.
    description : str
        The table's description of the action.
    """

    code: str
    description: str


@dataclasses.dataclass(frozen=True)
class ActionCodeTable:
    """Table E.1-1a as generated from one edition of the standard.

    Attributes
    ----------
    edition : str
        The edition of DICOM PS3.15, such as ``"2026d"``.
    acknowledgement : str
        The copyright attribution for the table's source.
    codes : tuple of ActionCode
        One per row, in the table's order.
    """

    edition: str
    acknowledgement: str
    codes: tuple[ActionCode, ...]


@dataclasses.dataclass(frozen=True)
class SafePrivateAttribute:
    """One row of DICOM PS3.15 Table E.3.10-1.

    Attributes
    ----------
    tag : str
        The Data Element in the form ``(gggg,xxee)``, where ``xx`` stands for
        the private block, as the table gives it. Some hexadecimal digits are
        published in lower case, so compare tags without regard to case.
    private_creator : str
        The Private Creator that reserves the block.
    vr : str
        The VR, alternatives such as ``"OW/OB"``, or ``""`` where the table
        gives none.
    vm : str
        The VM, such as ``"1"`` or ``"1-n"``.
    meaning : str
        The table's description of the attribute, which may be ``""``.
    """

    tag: str
    private_creator: str
    vr: str
    vm: str
    meaning: str


@dataclasses.dataclass(frozen=True)
class SafePrivateTable:
    """Table E.3.10-1 as generated from one edition of the standard.

    Attributes
    ----------
    edition : str
        The edition of DICOM PS3.15, such as ``"2026d"``.
    acknowledgement : str
        The copyright attribution for the table's source.
    attributes : tuple of SafePrivateAttribute
        One per row, in the table's order.
    """

    edition: str
    acknowledgement: str
    attributes: tuple[SafePrivateAttribute, ...]


def is_private_tag(value: object) -> bool:
    """Return whether ``value`` is a private Data Element such as ``(0019,xx0C)``.

    The group must be odd and not one that PS3.5 Section 7.8.1 excludes from
    private use.
    """
    if not isinstance(value, str):
        return False
    match = PRIVATE_TAG_PATTERN.fullmatch(value)
    if not match:
        return False
    group = int(match.group(1), 16)
    return group % 2 == 1 and group not in _RESERVED_ODD_GROUPS


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
    if not isinstance(edition, str) or not edition:
        raise StandardTableError(f"{path.name} does not name its edition as text")
    if document.get("acknowledgement") != f"DICOM PS3.15 {edition}, © NEMA":
        raise StandardTableError(f"{path.name} lacks the copyright acknowledgement")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise StandardTableError(f"{path.name} has no rows")
    try:
        digest = content_sha256(rows)
    except UnicodeEncodeError as error:
        # JSON can escape a lone surrogate, which has no UTF-8 encoding.
        raise StandardTableError(
            f"{path.name} has a row with text that cannot be encoded as UTF-8"
        ) from error
    if digest != document.get("content_sha256"):
        raise StandardTableError(
            f"{path.name} rows do not match their recorded digest; "
            "regenerate the tables with pymedphys dev deid-tables"
        )
    return document


def _is_action(value: object) -> bool:
    return isinstance(value, str) and value in ACTION_CODES


def _is_text(value: object, *, empty: bool = False) -> bool:
    return isinstance(value, str) and (empty or bool(value))


def _e1_1_problem(row: dict) -> str | None:
    """Return what is wrong with a row of Table E.1-1, or None if it is valid."""
    if not all(_is_text(row[field]) for field in ("name", "tag")):
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


def _e1_1a_problem(row: dict) -> str | None:
    """Return what is wrong with a row of Table E.1-1a, or None if it is valid."""
    if not _is_action(row["code"]):
        return "has a code that is not an action code PyMedPhys implements"
    if not _is_text(row["description"]):
        return "has a description that is not non-empty text"
    return None


def _e3_10_1_problem(row: dict) -> str | None:
    """Return what is wrong with a row of Table E.3.10-1, or None if it is valid."""
    if not is_private_tag(row["tag"]):
        return "has a tag that is not a private Data Element such as (0019,xx0C)"
    if not _is_text(row["private_creator"]):
        return "has a private creator that is not non-empty text"
    if not (_is_text(row["vr"], empty=True) and VR_PATTERN.fullmatch(row["vr"])):
        return "has a VR that is not empty or one or more VRs such as OW/OB"
    if not (_is_text(row["vm"]) and VM_PATTERN.fullmatch(row["vm"])):
        return "has a VM that is not of the form 1, 1-n, or 3-4"
    if not _is_text(row["meaning"], empty=True):
        return "has a meaning that is not text"
    return None


def _checked_rows(
    path: pathlib.Path,
    document: dict,
    fields: frozenset[str],
    problem: Callable[[dict], str | None],
    key: Callable[[dict], Hashable],
    repeated: str,
) -> list[dict]:
    """Return a document's rows after checking each one and their keys."""
    rows: list[dict] = document["rows"]
    seen = set()
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or row.keys() != fields:
            raise StandardTableError(
                f"{path.name} row {number} does not have exactly the fields "
                + ", ".join(sorted(fields))
            )
        issue = problem(row)
        if issue:
            raise StandardTableError(f"{path.name} row {number} {issue}")
        if key(row) in seen:
            raise StandardTableError(f"{path.name} row {number} repeats {repeated}")
        seen.add(key(row))
    return rows


def _default(path: pathlib.Path | None, name: str) -> pathlib.Path:
    return (path or STANDARD_DIR / name).resolve()


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
        If the file cannot be read, has another schema or table, does not
        name its edition as non-empty text, lacks the copyright
        acknowledgement, has row text that cannot be encoded as UTF-8, or has
        rows that do not match its recorded digest; if it has no rows or
        repeats a tag; or if a row does not have exactly the expected fields,
        with non-empty text for the name and tag, true or false for the
        flags, and actions defined in Table E.1-1a for the Basic Profile and
        each known option.
    """
    return _load_table_e1_1(_default(path, "e1_1.json"))


@functools.lru_cache(maxsize=None)
def _load_table_e1_1(path: pathlib.Path) -> ProfileTable:
    document = _read(path, "PS3.15 Table E.1-1")
    rows = _checked_rows(
        path, document, _E1_1_FIELDS, _e1_1_problem, lambda row: row["tag"], "a tag"
    )
    return ProfileTable(
        edition=document["edition"],
        acknowledgement=document["acknowledgement"],
        attributes=tuple(
            ProfileAttribute(
                name=row["name"],
                tag=row["tag"],
                retired=row["retired"],
                in_standard_iod=row["in_standard_iod"],
                basic_profile=row["basic_profile"],
                options=types.MappingProxyType(dict(row["options"])),
            )
            for row in rows
        ),
    )


def load_table_e1_1a(path: pathlib.Path | None = None) -> ActionCodeTable:
    """Load Table E.1-1a of DICOM PS3.15, the de-identification action codes.

    The table must define exactly the codes in :data:`ACTION_CODES`, each of
    which the engine implements. Each file is read once and cached, keyed by
    its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    ActionCodeTable

    Raises
    ------
    StandardTableError
        For any of the file-level problems :func:`load_table_e1_1` rejects;
        if a row does not have exactly a code from :data:`ACTION_CODES` and a
        non-empty description; if a code repeats; or if a code is missing.
    """
    return _load_table_e1_1a(_default(path, "e1_1a.json"))


@functools.lru_cache(maxsize=None)
def _load_table_e1_1a(path: pathlib.Path) -> ActionCodeTable:
    document = _read(path, "PS3.15 Table E.1-1a")
    rows = _checked_rows(
        path,
        document,
        _E1_1A_FIELDS,
        _e1_1a_problem,
        lambda row: row["code"],
        "an action code",
    )
    missing = ACTION_CODES - {row["code"] for row in rows}
    if missing:
        raise StandardTableError(
            f"{path.name} does not define the action codes {', '.join(sorted(missing))}"
        )
    return ActionCodeTable(
        edition=document["edition"],
        acknowledgement=document["acknowledgement"],
        codes=tuple(
            ActionCode(code=row["code"], description=row["description"]) for row in rows
        ),
    )


def load_table_e3_10_1(path: pathlib.Path | None = None) -> SafePrivateTable:
    """Load Table E.3.10-1 of DICOM PS3.15, the safe private attributes.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    SafePrivateTable

    Raises
    ------
    StandardTableError
        For any of the file-level problems :func:`load_table_e1_1` rejects;
        if a row does not have exactly a private tag (see
        :func:`is_private_tag`), non-empty private creator text, a VR that
        is empty or matches :data:`VR_PATTERN`, a VM matching
        :data:`VM_PATTERN`, and meaning text; or if a private creator and
        tag repeat, comparing tags without regard to case.
    """
    return _load_table_e3_10_1(_default(path, "e3_10_1.json"))


@functools.lru_cache(maxsize=None)
def _load_table_e3_10_1(path: pathlib.Path) -> SafePrivateTable:
    document = _read(path, "PS3.15 Table E.3.10-1")
    rows = _checked_rows(
        path,
        document,
        _E3_10_1_FIELDS,
        _e3_10_1_problem,
        lambda row: (row["private_creator"], row["tag"].upper()),
        "a private creator and tag",
    )
    return SafePrivateTable(
        edition=document["edition"],
        acknowledgement=document["acknowledgement"],
        attributes=tuple(
            SafePrivateAttribute(
                tag=row["tag"],
                private_creator=row["private_creator"],
                vr=row["vr"],
                vm=row["vm"],
                meaning=row["meaning"],
            )
            for row in rows
        ),
    )
