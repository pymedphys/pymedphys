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

Leading and trailing whitespace is removed from every cell, blank rows are
skipped, and a byte order mark, as Excel writes, is ignored. Each name must be
a valid DICOM LO value, as ROI Name (3006,0026) is: at most 64 characters,
without backslashes or control characters (PS3.5 Section 6.2).
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
        If the version is empty or has surrounding whitespace or line
        breaks; if the file is not UTF-8 or is empty; if a header is not one
        of :data:`COLUMNS` or repeats, or ``Name`` is missing; if a row has
        more cells than the header; if a name is empty, is not a valid LO
        value, or repeats; or if there are no names. Errors name the CSV row,
        counting from 1.
    """
    path = pathlib.Path(path)
    if not _is_version(version):
        raise RoiListError("the version must be non-empty text on one line")
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RoiListError(f"{path.name} is not UTF-8") from error
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise RoiListError(f"{path.name} is empty")
    columns = _columns(rows[0])
    entries = []
    for number, row in enumerate(rows[1:], start=2):
        cells = [cell.strip() for cell in row]
        if not any(cells):
            continue
        if len(cells) > len(rows[0]):
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
        If the file is not JSON; if it does not have exactly the keys
        :func:`to_json` writes, or has another format; if its source is
        malformed; if an entry does not have exactly the fields of
        :class:`Entry` or has a value :func:`read_csv` would reject; if a
        name repeats; if it has no names; or if its entries do not match its
        ``content_sha256``.
    """
    path = pathlib.Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
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


def _columns(header: Sequence[str]) -> dict[str, int]:
    """Map each Entry field to the index of its column."""
    names = [cell.strip() for cell in header]
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
    return (
        len(value) <= _LO_MAX
        and "\\" not in value
        and not any(unicodedata.category(char) == "Cc" for char in value)
    )


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
        and "\n" not in version
        and "\r" not in version
    )


def _is_source(source: object) -> bool:
    return (
        isinstance(source, dict)
        and set(source) == {"kind", "file", "sha256", "version"}
        and source["kind"] == KIND
        and isinstance(source["file"], str)
        and bool(source["file"])
        and isinstance(source["sha256"], str)
        and bool(_SHA256.fullmatch(source["sha256"]))
        and _is_version(source["version"])
    )
