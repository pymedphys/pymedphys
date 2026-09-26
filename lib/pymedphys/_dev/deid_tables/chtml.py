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

"""Extract titled tables from NEMA's chtml pages of the DICOM standard."""

from __future__ import annotations

import dataclasses
import re
from html.parser import HTMLParser

# Zero-width characters appear inside some cell text in the published pages.
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WHITESPACE = re.compile(r"\s+")


class TableFormatError(ValueError):
    """A table is missing or does not have the structure the parser expects."""


@dataclasses.dataclass(frozen=True)
class HtmlTable:
    """One table from a page, with normalised cell text.

    Attributes
    ----------
    title : str
        Text of the ``p.title`` element immediately before the table, such as
        ``"Table E.1-1. Application Level Confidentiality Profile Attributes"``,
        or ``""`` for an untitled table such as page navigation.
    header : tuple of str
        The first row when every cell in it is a ``th`` cell, otherwise empty.
    rows : tuple of tuple of str
        Every other row.
    has_merged_cells : bool
        Whether any cell spans more than one row or column.
    """

    title: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    has_merged_cells: bool


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", _INVISIBLE.sub("", text)).strip()


@dataclasses.dataclass
class _Cell:
    is_header: bool
    merged: bool
    parts: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class _Table:
    title: str
    rows: list[list[_Cell]] = dataclasses.field(default_factory=list)
    cell: _Cell | None = None


def _span(attrs: dict[str, str | None], name: str) -> int:
    value = attrs.get(name) or "1"
    try:
        return int(value)
    except ValueError as error:
        raise TableFormatError(f"{name}={value!r} is not an integer") from error


class _TableCollector(HTMLParser):
    """Collect every table in document order, with the title before it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[_Table] = []
        self._open: list[_Table] = []
        self._title_parts: list[str] | None = None
        self._pending_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            table = _Table(title=self._pending_title)
            self._pending_title = ""
            self._open.append(table)
            self.tables.append(table)
        elif not self._open:
            if tag == "p":
                # A title applies to the next table only if no other
                # paragraph comes between them.
                self._pending_title = ""
                if attributes.get("class") == "title":
                    self._title_parts = []
        elif tag == "tr":
            self._open[-1].rows.append([])
        elif tag in ("td", "th"):
            table = self._open[-1]
            if not table.rows:
                table.rows.append([])
            merged = (
                _span(attributes, "colspan") != 1 or _span(attributes, "rowspan") != 1
            )
            table.cell = _Cell(is_header=tag == "th", merged=merged)
            table.rows[-1].append(table.cell)
        elif tag == "br" and self._open[-1].cell is not None:
            self._open[-1].cell.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._open:
            self._open.pop()
        elif tag in ("td", "th") and self._open:
            self._open[-1].cell = None
        elif tag == "p" and self._title_parts is not None:
            self._pending_title = _normalise("".join(self._title_parts))
            self._title_parts = None

    def handle_data(self, data: str) -> None:
        if self._open:
            cell = self._open[-1].cell
            if cell is not None:
                cell.parts.append(data)
        elif self._title_parts is not None:
            self._title_parts.append(data)


def extract_tables(page: str) -> list[HtmlTable]:
    """Return every table on a chtml page, in document order.

    Parameters
    ----------
    page : str
        The decoded HTML of one page.

    Returns
    -------
    list of HtmlTable
        Tables nested inside another table's cell are listed after it, and
        their text is not part of the outer cell.
    """
    collector = _TableCollector()
    collector.feed(page)
    collector.close()

    tables = []
    for table in collector.tables:
        rows = [row for row in table.rows if row]
        texts = [tuple(_normalise("".join(cell.parts)) for cell in row) for row in rows]
        has_header = bool(rows) and all(cell.is_header for cell in rows[0])
        tables.append(
            HtmlTable(
                title=table.title,
                header=texts[0] if has_header else (),
                rows=tuple(texts[1:] if has_header else texts),
                has_merged_cells=any(cell.merged for row in rows for cell in row),
            )
        )
    return tables


def select_table(tables: list[HtmlTable], label: str) -> HtmlTable:
    """Return the one table whose title starts with ``label``.

    Parameters
    ----------
    tables : list of HtmlTable
        Tables from :func:`extract_tables`.
    label : str
        The table's label as the standard numbers it, such as
        ``"Table E.1-1"``. It must be followed in the title by a full stop or
        a space, so ``"Table E.1-1"`` does not select ``"Table E.1-1a"``.

    Returns
    -------
    HtmlTable

    Raises
    ------
    TableFormatError
        If no table or more than one table has the label, if the table has
        merged cells, or if a row has a different number of cells from the
        header.
    """
    matches = [
        table
        for table in tables
        if table.title == label or table.title.startswith((f"{label}.", f"{label} "))
    ]
    if not matches:
        raise TableFormatError(f"no table titled {label!r}")
    if len(matches) > 1:
        raise TableFormatError(f"{len(matches)} tables titled {label!r}")

    table = matches[0]
    if table.has_merged_cells:
        raise TableFormatError(f"{label} has merged cells, which are not supported")
    if table.header:
        for number, row in enumerate(table.rows, start=1):
            if len(row) != len(table.header):
                raise TableFormatError(
                    f"{label}: row {number} has {len(row)} cells, "
                    f"but the header has {len(table.header)}"
                )
    return table
