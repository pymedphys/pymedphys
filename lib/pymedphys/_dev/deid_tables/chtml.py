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

"""Extract titled tables from NEMA's HTML pages of the DICOM standard.

NEMA publishes each part both as chtml pages, one per section, and as a single
HTML page. Both mark up tables in the same way.
"""

from __future__ import annotations

import collections
import dataclasses
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from html.parser import HTMLParser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymedphys._dicom.deidentify.uid_registry import RegistryTableSpec

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
        Every other row, including empty rows.
    has_merged_cells : bool
        Whether any cell spans more than one row or column.
    section : str
        The number of the last section whose anchor comes before the table,
        such as ``"C.7.1.1"``, or ``""`` if none does.
    """

    title: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    has_merged_cells: bool
    section: str = ""


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", _INVISIBLE.sub("", text)).strip()


@dataclasses.dataclass
class _Cell:
    is_header: bool
    rowspan: int
    colspan: int
    parts: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class _Table:
    title: str
    section: str
    rows: list[list[_Cell]] = dataclasses.field(default_factory=list)
    cell: _Cell | None = None


def _span(attrs: dict[str, str | None], name: str) -> int:
    value = attrs.get(name) or "1"
    try:
        return int(value)
    except ValueError as error:
        raise TableFormatError(f"{name}={value!r} is not an integer") from error


class _TableCollector(HTMLParser):
    """Collect every table in document order, with its title and section."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[_Table] = []
        self._open: list[_Table] = []
        self._title_parts: list[str] | None = None
        self._pending_title = ""
        self._section = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            table = _Table(title=self._pending_title, section=self._section)
            self._pending_title = ""
            self._open.append(table)
            self.tables.append(table)
        elif not self._open:
            anchor = attributes.get("id") or ""
            if tag == "a" and anchor.startswith("sect_"):
                self._section = anchor.removeprefix("sect_")
            elif tag == "p":
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
            table.cell = _Cell(
                is_header=tag == "th",
                rowspan=_span(attributes, "rowspan"),
                colspan=_span(attributes, "colspan"),
            )
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


def _expanded(rows: list[list[_Cell]]) -> list[tuple[str, ...]]:
    """Return each row's text with every merged cell's text in each place it covers."""
    grid: dict[tuple[int, int], str] = {}
    for number, row in enumerate(rows):
        column = 0
        for cell in row:
            while (number, column) in grid:
                column += 1
            text = _normalise("".join(cell.parts))
            for below in range(cell.rowspan):
                for across in range(cell.colspan):
                    grid[number + below, column + across] = text
            column += cell.colspan
    width = collections.Counter(number for number, _ in grid)
    return [
        tuple(grid[number, column] for column in range(width[number]))
        for number in range(len(rows))
    ]


def extract_tables(page: str, *, expand_spans: bool = False) -> list[HtmlTable]:
    """Return every table on a page, in document order.

    Parameters
    ----------
    page : str
        The decoded HTML of one page.
    expand_spans : bool, optional
        Repeat the text of a cell that spans several rows or columns in each
        place it covers, so every row of a regular table has one cell per
        column. By default a merged cell appears once, in its first row.

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
        rows = table.rows
        texts = (
            _expanded(rows)
            if expand_spans
            else [
                tuple(_normalise("".join(cell.parts)) for cell in row) for row in rows
            ]
        )
        has_header = bool(rows and rows[0]) and all(cell.is_header for cell in rows[0])
        tables.append(
            HtmlTable(
                title=table.title,
                header=texts[0] if has_header else (),
                rows=tuple(texts[1:] if has_header else texts),
                has_merged_cells=any(
                    (cell.rowspan, cell.colspan) != (1, 1)
                    for row in rows
                    for cell in row
                ),
                section=table.section,
            )
        )
    return tables


def select_table(
    tables: Sequence[HtmlTable], label: str, *, allow_merged: bool = False
) -> HtmlTable:
    """Return the one table whose title starts with ``label``.

    Parameters
    ----------
    tables : sequence of HtmlTable
        Tables from :func:`extract_tables`.
    label : str
        The table's label as the standard numbers it, such as
        ``"Table E.1-1"``. It must be followed in the title by a full stop or
        a space, so ``"Table E.1-1"`` does not select ``"Table E.1-1a"``.
    allow_merged : bool, optional
        Accept a table with merged cells, as extracted with ``expand_spans``.

    Returns
    -------
    HtmlTable

    Raises
    ------
    TableFormatError
        If no table or more than one table has the label, if the table has
        merged cells and ``allow_merged`` is false, or if a row has a
        different number of cells from the header.
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
    if table.has_merged_cells and not allow_merged:
        raise TableFormatError(f"{label} has merged cells, which are not supported")
    if table.header:
        for number, row in enumerate(table.rows, start=1):
            if len(row) != len(table.header):
                raise TableFormatError(
                    f"{label}: row {number} has {len(row)} cells, "
                    f"but the header has {len(table.header)}"
                )
    return table


def check_columns(
    label: str, header: tuple[str, ...], columns: Collection[str]
) -> None:
    """Check that ``header`` has each of ``columns`` exactly once, and no other.

    Columns are matched by their header text, so a new edition that reorders
    them still parses, and one that adds, renames, or removes one fails.
    """
    for column in header:
        if column not in columns:
            raise TableFormatError(f"{label} has an unknown column {column!r}")
    for column in columns:
        count = header.count(column)
        if count == 0:
            raise TableFormatError(f"{label} is missing column {column!r}")
        if count > 1:
            raise TableFormatError(f"{label} has column {column!r} {count} times")


def check_unique(label: str, keys: Iterable[str]) -> None:
    """Check that no key repeats, listing each one that does."""
    counts = collections.Counter(keys)
    repeated = [f"{key} appears {n} times" for key, n in counts.items() if n > 1]
    if repeated:
        raise TableFormatError(f"{label}: " + "; ".join(repeated))


def parse_registry_table(
    label: str,
    table: HtmlTable,
    columns: Mapping[str, str],
    spec: RegistryTableSpec,
) -> tuple:
    """Parse a registry table, applying the checks its loader applies.

    Cell text is kept as published.

    Parameters
    ----------
    label : str
        The table's label, such as ``"Table A-1"``, for messages.
    table : HtmlTable
        The table, as :func:`select_table` returns it for ``label``.
    columns : mapping of str to str
        Each column's header text and the field of ``spec.row_type`` it fills.
    spec : RegistryTableSpec
        How the table is checked and loaded.

    Returns
    -------
    tuple
        One ``spec.row_type`` per row of the table, in order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a row fails one of ``spec.checks``; or if a key in
        ``spec.unique`` appears more than once.
    """
    check_columns(label, table.header, columns)
    if not table.rows:
        raise TableFormatError(f"{label} has no rows")

    rows = []
    for number, cells in enumerate(table.rows, start=1):
        row = {columns[column]: cell for column, cell in zip(table.header, cells)}
        problem = spec.problem(row)
        if problem:
            raise TableFormatError(f"{label} row {number} {problem}")
        rows.append(row)

    keys = collections.defaultdict(list)
    for row in rows:
        for name, value in spec.keys(row):
            keys[name].append(value)
    for values in keys.values():
        check_unique(label, values)
    return tuple(spec.row_type(**row) for row in rows)
