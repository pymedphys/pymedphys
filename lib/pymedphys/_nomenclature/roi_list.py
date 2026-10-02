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

"""Convert an institutional list of ROI names from CSV to JSON.

A site or project can keep its own list of structure names, beside or instead
of TG-263's. :func:`read_csv` reads one exported as UTF-8 CSV, with a ``Name``
column and, optionally, a ``Description`` column, and :func:`to_json` writes
it as JSON that records its source as an institutional list, with the file's
name, its SHA-256, and a version the user gives. :func:`load_json` reads that
JSON back and rejects a file edited without updating its content digest.

Unlike TG-263's, an institutional list can hold a name that identifies a site
or a person, such as ``ClinicX_Lung``. Its source record shows which list was
used, not that its names are safe to write, so de-identification sends every
match against such a list to human review rather than renaming automatically.

Leading and trailing whitespace is removed from every cell, blank rows and
empty trailing cells are ignored, and a byte order mark, as Excel writes, is
ignored. Malformed CSV, such as an unclosed quote, is rejected rather than
read as best it can be, which could join later rows into one cell. Each name
must be a valid DICOM LO value, as ROI Name (3006,0026) is, in the default
character repertoire: at most 64 printable ASCII characters, without
backslashes (PS3.5 Sections 6.1 and 6.2). Keeping to ASCII means a name needs
no Specific Character Set (0008,0005), and that no name can hold characters a
reviewer cannot see, such as a zero-width space or a right-to-left override.
A description, which is never written to DICOM, can hold any printable text
on one line. The version must also be printable text on one line.
"""

from __future__ import annotations

import collections
import csv
import dataclasses
import hashlib
import io
import json
import pathlib
import re
import unicodedata
from typing import Mapping, Sequence

FORMAT = "pymedphys-roi-list/1"
KIND = "institutional-list"
COLUMNS = ("Name", "Description")
_FIELDS = {"Name": "name", "Description": "description"}
_LO_MAX = 64
# Printable ASCII, the LO default repertoire without control characters.
_PRINTABLE_ASCII = frozenset(chr(code) for code in range(0x20, 0x7F))
# Unicode categories that print nothing visible or break a line: control,
# format, surrogate, private use, unassigned, and line and paragraph
# separators.
_UNPRINTABLE = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


class RoiListError(ValueError):
    """An institutional ROI name list that cannot be read as expected."""


@dataclasses.dataclass(frozen=True)
class Entry:
    """One name of an institutional list, and its description or ``""``."""

    name: str
    description: str


@dataclasses.dataclass(frozen=True)
class Source:
    """The CSV file an institutional list was converted from.

    Attributes
    ----------
    kind : str
        Always ``"institutional-list"``.
    file : str
        The file's name, without its directory.
    sha256 : str
        The SHA-256 of the file's bytes.
    version : str
        The list's version, as the user gave it.
    """

    kind: str
    file: str
    sha256: str
    version: str


@dataclasses.dataclass(frozen=True)
class RoiList:
    """The names of one institutional list, in the file's order."""

    source: Source
    entries: tuple[Entry, ...]


def content_sha256(entries: Sequence[Mapping[str, object]]) -> str:
    """Return the SHA-256 of entries in canonical JSON, as for TG-263."""
    canonical = json.dumps(
        entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_csv(path: pathlib.Path, *, version: str) -> RoiList:
    """Read an institutional list of ROI names from a UTF-8 CSV file.

    Parameters
    ----------
    path : pathlib.Path
        A CSV file whose header has a ``Name`` column and may have a
        ``Description`` column, in either order.
    version : str
        The list's version, such as a date; recorded with the source.

    Raises
    ------
    RoiListError
        If the version is empty, has surrounding whitespace, or is not
        printable text on one line; if the file is not UTF-8, is not valid
        CSV, or is empty; if a header is not one of :data:`COLUMNS` or
        repeats, or ``Name`` is missing; if a row has more non-empty cells
        than the header; if a name is empty, is not a valid LO value in the
        default repertoire, or repeats; if a description is not printable
        text on one line; or if there are no names. Errors name the CSV row,
        counting from 1, blank rows included.
    """
    path = pathlib.Path(path)
    if not _is_version(version):
        raise RoiListError("the version must be non-empty text on one line")
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RoiListError(f"{path.name} is not UTF-8") from error
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        rows = [[cell.strip() for cell in row] for row in reader]
    except csv.Error as error:
        raise RoiListError(
            f"{path.name} is not valid CSV near line {reader.line_num}: {error}"
        ) from error
    # Rows are numbered as a spreadsheet numbers them, counting blank ones.
    numbered = [(number, row) for number, row in enumerate(rows, start=1) if any(row)]
    if not numbered:
        raise RoiListError(f"{path.name} is empty")
    (_, header), *body = numbered
    header = _without_empty_tail(header)
    columns = _columns(header)
    entries = []
    for number, row in body:
        cells = _without_empty_tail(row)
        if len(cells) > len(header):
            raise RoiListError(f"row {number} has more cells than the header")
        values = {
            field: cells[index] if index < len(cells) else ""
            for field, index in columns.items()
        }
        values.setdefault("description", "")
        problem = _entry_problem(values, {"name": "Name", "description": "Description"})
        if problem:
            raise RoiListError(f"row {number}: {problem}")
        entries.append(Entry(**values))
    _check_entries(entries)
    return RoiList(
        source=Source(
            kind=KIND,
            file=path.name,
            sha256=hashlib.sha256(data).hexdigest(),
            version=version,
        ),
        entries=tuple(entries),
    )


def to_json(roi_list: RoiList) -> str:
    """Return an institutional list as deterministic JSON, ending with a newline."""
    entries = [dataclasses.asdict(entry) for entry in roi_list.entries]
    document = {
        "format": FORMAT,
        "source": dataclasses.asdict(roi_list.source),
        "content_sha256": content_sha256(entries),
        "entries": entries,
    }
    return json.dumps(document, indent=1, ensure_ascii=False) + "\n"


def load_json(path: pathlib.Path) -> RoiList:
    """Load an institutional list written by :func:`to_json`.

    Raises
    ------
    RoiListError
        If the file is not JSON or repeats a key; if it does not have
        exactly the keys :func:`to_json` writes, or has another format; if
        its source is malformed, including a file name with a directory; if an entry does not have exactly the fields of
        :class:`Entry` or has a value :func:`read_csv` would reject; if a
        name repeats; if it has no names; or if its entries do not match its
        ``content_sha256``.
    """
    path = pathlib.Path(path)
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys
        )
    except _RepeatedKey as error:
        raise RoiListError(f"{path.name} repeats the key {error.key!r}") from error
    except ValueError as error:
        raise RoiListError(f"{path.name} is not valid JSON") from error
    keys = {"format", "source", "content_sha256", "entries"}
    if not isinstance(document, dict) or set(document) != keys:
        raise RoiListError(f"{path.name} does not have the keys {sorted(keys)}")
    if document["format"] != FORMAT:
        raise RoiListError(
            f"{path.name} has format {document['format']!r}, not {FORMAT!r}"
        )
    source = document["source"]
    if not _is_source(source):
        raise RoiListError(f"{path.name} has a malformed source")
    entries = document["entries"]
    if not isinstance(entries, list):
        raise RoiListError(f"{path.name} has no list of entries")
    labels = {"name": "name", "description": "description"}
    for number, values in enumerate(entries, start=1):
        if not isinstance(values, dict) or set(values) != set(labels):
            raise RoiListError(f"entry {number} has keys other than {list(labels)}")
        problem = _entry_problem(values, labels)
        if problem:
            raise RoiListError(f"entry {number}: {problem}")
    loaded = [Entry(**values) for values in entries]
    _check_entries(loaded)
    if content_sha256(entries) != document["content_sha256"]:
        raise RoiListError(f"{path.name} does not match its content_sha256")
    return RoiList(source=Source(**source), entries=tuple(loaded))


class _RepeatedKey(Exception):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object, refusing a key that appears twice."""
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise _RepeatedKey(key)
        document[key] = value
    return document


def _without_empty_tail(row: list[str]) -> list[str]:
    """Return ``row`` without its empty trailing cells."""
    end = len(row)
    while end and not row[end - 1]:
        end -= 1
    return row[:end]


def _columns(header: Sequence[str]) -> dict[str, int]:
    """Map each Entry field to the index of its column."""
    names = list(header)
    if len(names) == 1 and ";" in names[0]:
        raise RoiListError(
            f"unknown column {names[0]!r}; the file must be separated by "
            'commas, as Excel\'s "CSV UTF-8" format is, not semicolons'
        )
    for name, count in collections.Counter(names).items():
        if count > 1:
            raise RoiListError(f"column {name!r} appears {count} times")
    for name in names:
        if name not in COLUMNS:
            raise RoiListError(f"unknown column {name!r}")
    if "Name" not in names:
        raise RoiListError("missing column 'Name'")
    return {_FIELDS[name]: index for index, name in enumerate(names)}


def _is_lo(value: str) -> bool:
    """Whether ``value`` is an LO value in the default repertoire."""
    return (
        len(value) <= _LO_MAX
        and "\\" not in value
        and all(char in _PRINTABLE_ASCII for char in value)
    )


def _is_printable(value: str) -> bool:
    """Whether ``value`` is visible text on one line."""
    return not any(unicodedata.category(char) in _UNPRINTABLE for char in value)


def _entry_problem(
    values: Mapping[str, object], labels: Mapping[str, str]
) -> str | None:
    """Return what is wrong with an entry's values, or None."""
    for field in ("name", "description"):
        value = values[field]
        if not isinstance(value, str):
            return f"{labels[field]!r} is not text"
        if value != value.strip():
            return f"{labels[field]!r} has surrounding whitespace"
    name = str(values["name"])
    if not name:
        return f"{labels['name']!r} is empty"
    if not _is_lo(name):
        return f"{labels['name']!r} is not a valid LO value"
    if not _is_printable(str(values["description"])):
        return f"{labels['description']!r} has a character that is not printable"
    return None


def _check_entries(entries: Sequence[Entry]) -> None:
    if not entries:
        raise RoiListError("there are no names")
    counts = collections.Counter(entry.name for entry in entries)
    for name, count in counts.items():
        if count > 1:
            raise RoiListError(f"name {name!r} appears {count} times")


def _is_version(version: object) -> bool:
    return (
        isinstance(version, str)
        and bool(version)
        and version == version.strip()
        and _is_printable(version)
    )


def _is_file_name(file: object) -> bool:
    """Whether ``file`` is a file's name alone, as :func:`read_csv` records it."""
    return (
        isinstance(file, str)
        and bool(file)
        and file == file.strip()
        and "/" not in file
        and "\\" not in file
        and file not in (".", "..")
        and _is_printable(file)
    )


def _is_source(source: object) -> bool:
    return (
        isinstance(source, dict)
        and set(source) == {"kind", "file", "sha256", "version"}
        and source["kind"] == KIND
        and _is_file_name(source["file"])
        and isinstance(source["sha256"], str)
        and bool(_SHA256.fullmatch(source["sha256"]))
        and _is_version(source["version"])
    )
