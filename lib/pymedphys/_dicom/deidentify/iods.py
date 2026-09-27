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

"""Load the attribute Types of the supported IODs, as DICOM PS3.3 defines them.

``pymedphys dev deid-tables`` generates two tables from the pinned edition of
PS3.3. ``iod_modules.json`` lists each supported IOD's modules, and
``module_attributes.json`` holds the attribute tables of those modules and of
every macro they include, with rows as published. The loader expands each
IOD's modules, following every "Include" row, into the attributes it defines
at each place in the data set, with their Types.

The design resolves compound actions of Table E.1-1, such as X/Z/D, from these
Types (PS3.15 E.1.1).
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import pathlib
import re
import types
from collections.abc import Iterator, Mapping, Sequence

from .standard import (
    StandardTableError,
    _default,
    _is_text,
    _read,
    is_dictionary_tag,
)

IOD_MODULES_TABLE = "PS3.3 IOD Modules"
MODULE_ATTRIBUTES_TABLE = "PS3.3 Module Attributes"

# The attribute Types of PS3.5 Section 7.4.
ATTRIBUTE_TYPES = frozenset({"1", "1C", "2", "2C", "3"})
# Mandatory, conditional, and user-optional modules (PS3.3 Section A.1.3).
MODULE_USAGES = frozenset({"M", "C", "U"})
# A table's label, such as "Table C.7-1", "Table 10-11", or "Table 8.8-1a".
TABLE_LABEL_PATTERN = re.compile(r"Table [0-9A-Z](?:[0-9A-Za-z.\-]*[0-9A-Za-z])?")

_IOD_FIELDS = frozenset({"label", "iod", "modules"})
_MODULE_FIELDS = frozenset(
    {"information_entity", "module", "section", "usage", "condition", "table"}
)
_TABLE_FIELDS = frozenset({"label", "title", "rows"})
_ROW_FIELDS = frozenset({"depth", "name", "tag", "type", "include"})
# Groups 5000-501E and 6000-601E repeat (PS3.5 Section 7.6); PS3.3 gives
# their attributes with "xx" in place of the group's last two digits.
_REPEATING_GROUP = re.compile(r"\((50|60)([0-1][0-9A-E]),([0-9A-F]{4})\)")


@dataclasses.dataclass(frozen=True)
class ModuleUsage:
    """One row of an IOD's modules table, such as Table A.3-1.

    Attributes
    ----------
    information_entity : str
        The information entity, such as ``"Patient"``.
    module : str
        The module's name, such as ``"Patient"``.
    section : str
        The section of PS3.3 that defines the module, such as ``"C.7.1.1"``.
    usage : str
        ``"M"`` (mandatory), ``"C"`` (conditional), or ``"U"``
        (user-optional).
    condition : str
        The text after the usage code, such as a conditional module's
        condition, or ``""``.
    table : str
        The label of the module's attribute table, such as ``"Table C.7-1"``.
    """

    information_entity: str
    module: str
    section: str
    usage: str
    condition: str
    table: str


@dataclasses.dataclass(frozen=True)
class AttributeRow:
    """One row of a module or macro attribute table, as published.

    Attributes
    ----------
    depth : int
        The number of ">" characters before the name: 0 at the top level of
        the table, and one more for each enclosing sequence.
    name : str
        The attribute's name, or ``""`` for an "Include" row.
    tag : str
        The attribute's tag, such as ``"(0010,0020)"`` or ``"(60xx,3000)"``;
        or ``""`` for an "Include" row, or for a row that describes
        attributes in words, such as "Any Attribute from the top level Data
        Set that was modified or removed".
    type : str
        The attribute's Type, one of :data:`ATTRIBUTE_TYPES`, or ``""`` for
        an "Include" row.
    include : str
        For an "Include" row, the label of the included table, whose rows are
        added at this row's depth; otherwise ``""``.
    """

    depth: int
    name: str
    tag: str
    type: str
    include: str


@dataclasses.dataclass(frozen=True)
class AttributeTable:
    """A module or macro attribute table of PS3.3, such as Table C.7-1.

    Attributes
    ----------
    label : str
        The table's label, such as ``"Table C.7-1"``.
    title : str
        The table's title without its label, such as
        ``"Patient Module Attributes"``.
    rows : tuple of AttributeRow
        The table's rows, in order. Rows that only head a group of rows are
        omitted.
    """

    label: str
    title: str
    rows: tuple[AttributeRow, ...]


@dataclasses.dataclass(frozen=True)
class AttributeDefinition:
    """Where an IOD's module defines an attribute, and its Type there.

    Attributes
    ----------
    path : tuple of str
        The tags of the sequences whose items contain the attribute,
        outermost first, or ``()`` at the top level of the data set.
    tag : str
        The attribute's tag, as the table gives it.
    name : str
        The attribute's name, as the table gives it.
    type : str
        The attribute's Type there, one of :data:`ATTRIBUTE_TYPES`.
    module : str
        The name of the module that defines it.
    tables : tuple of str
        The labels of the tables that lead to the definition: the module's
        attribute table, then each macro table included, outermost first.
    """

    path: tuple[str, ...]
    tag: str
    name: str
    type: str
    module: str
    tables: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class IOD:
    """An IOD's modules and the attributes they define.

    Attributes
    ----------
    name : str
        The IOD's name, such as ``"CT Image"``.
    label : str
        The label of its modules table, such as ``"Table A.3-1"``.
    modules : tuple of ModuleUsage
        Its modules, in the table's order.
    definitions : tuple of AttributeDefinition
        Every attribute its modules define, with each macro expanded, in the
        order of the modules and their rows.
    """

    name: str
    label: str
    modules: tuple[ModuleUsage, ...]
    definitions: tuple[AttributeDefinition, ...] = dataclasses.field(repr=False)
    _index: Mapping[tuple[tuple[str, ...], str], tuple[AttributeDefinition, ...]] = (
        dataclasses.field(init=False, repr=False, compare=False)
    )

    def __post_init__(self) -> None:
        index: dict[tuple[tuple[str, ...], str], list[AttributeDefinition]] = (
            collections.defaultdict(list)
        )
        for definition in self.definitions:
            index[definition.path, definition.tag].append(definition)
        object.__setattr__(
            self,
            "_index",
            types.MappingProxyType({key: tuple(value) for key, value in index.items()}),
        )

    def lookup(
        self, tag: str, path: Sequence[str] = ()
    ) -> tuple[AttributeDefinition, ...]:
        """Return every definition of an attribute at a place in the data set.

        Parameters
        ----------
        tag : str
            The attribute's tag, such as ``"(0010,0020)"``, with upper-case
            hexadecimal digits. An attribute of a repeating group, such as
            ``"(6002,3000)"``, also matches its definition for the group,
            ``"(60xx,3000)"``.
        path : sequence of str, optional
            The tags of the sequences whose items contain the attribute,
            outermost first. Defaults to the top level of the data set.

        Returns
        -------
        tuple of AttributeDefinition
            One for each place in the IOD's modules that defines the
            attribute there, or ``()`` if none does. Different modules can
            give the same attribute different Types.
        """
        key = tuple(path)
        found = self._index.get((key, tag), ())
        repeating = _REPEATING_GROUP.fullmatch(tag)
        if repeating:
            group, _, element = repeating.groups()
            found += self._index.get((key, f"({group}xx,{element})"), ())
        return found


@dataclasses.dataclass(frozen=True)
class IODTables:
    """The supported IODs, as generated from one edition of PS3.3.

    Attributes
    ----------
    edition : str
        The edition of DICOM PS3.3, such as ``"2026d"``.
    acknowledgement : str
        The copyright attribution, such as ``"DICOM PS3.3 2026d, © NEMA"``.
    iods : Mapping of str to IOD
        Each IOD by name, such as ``"CT Image"``, in the generated order.
    attribute_tables : Mapping of str to AttributeTable
        Each module and macro attribute table by label.
    """

    edition: str
    acknowledgement: str
    iods: Mapping[str, IOD]
    attribute_tables: Mapping[str, AttributeTable]


def _fields_problem(entry: object, fields: frozenset[str], what: str) -> str | None:
    if not isinstance(entry, dict) or set(entry) != fields:
        return f"has {what} without exactly the fields {', '.join(sorted(fields))}"
    return None


def _include_problem(row: dict) -> str | None:
    """Return what is wrong with an "Include" row, or None."""
    if not TABLE_LABEL_PATTERN.fullmatch(row["include"]):
        return "includes something that is not a table label"
    if row["name"] or row["tag"] or row["type"]:
        return "is an Include row with a name, tag, or Type"
    return None


def _attribute_problem(row: dict) -> str | None:
    """Return what is wrong with an attribute row, or None."""
    if not row["name"] or row["type"] not in ATTRIBUTE_TYPES:
        return "has no name, or a Type other than 1, 1C, 2, 2C, or 3"
    if row["tag"] and not is_dictionary_tag(row["tag"]):
        return "has a tag that is not of the form (gggg,eeee)"
    return None


def _row_problem(row: dict, above: AttributeRow | None) -> str | None:
    """Return what is wrong with a row of an attribute table, or None."""
    depth = row["depth"]
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
        return "has a depth that is not a non-negative integer"
    if not all(_is_text(row[field], empty=True) for field in _ROW_FIELDS - {"depth"}):
        return "has a name, tag, Type, or include that is not text"
    problem = _include_problem(row) if row["include"] else _attribute_problem(row)
    if problem:
        return problem
    # A row can be one level deeper than an attribute with a tag above it,
    # which is then a sequence, and no deeper than any other row above it.
    allowed = 0 if above is None else above.depth + bool(above.tag)
    if depth > allowed:
        return "is nested more deeply than the row above allows"
    return None


def _attribute_tables(document: dict, name: str) -> dict[str, AttributeTable]:
    tables: dict[str, AttributeTable] = {}
    for entry in document["rows"]:
        problem = _fields_problem(entry, _TABLE_FIELDS, "a table")
        if problem:
            raise StandardTableError(f"{name} {problem}")
        label = entry["label"]
        if not isinstance(label, str) or not TABLE_LABEL_PATTERN.fullmatch(label):
            raise StandardTableError(f"{name} has a table without a label")
        if label in tables:
            raise StandardTableError(f"{name} has {label} more than once")
        if not _is_text(entry["title"]):
            raise StandardTableError(f"{name}: {label} has no title")
        if not isinstance(entry["rows"], list) or not entry["rows"]:
            raise StandardTableError(f"{name}: {label} has no rows")
        rows: list[AttributeRow] = []
        for number, row in enumerate(entry["rows"], start=1):
            problem = _fields_problem(row, _ROW_FIELDS, "a row") or _row_problem(
                row, rows[-1] if rows else None
            )
            if problem:
                raise StandardTableError(f"{name}: {label} row {number} {problem}")
            rows.append(AttributeRow(**row))
        tables[label] = AttributeTable(label, entry["title"], tuple(rows))

    for label in tables:
        _check_includes(tables, label, (), name)
    return tables


def _check_includes(
    tables: Mapping[str, AttributeTable], label: str, chain: tuple[str, ...], name: str
) -> None:
    """Check that every table ``label`` includes exists and never includes itself."""
    if label in chain:
        raise StandardTableError(
            f"{name}: {label} includes itself: "
            + " > ".join((*chain[chain.index(label) :], label))
        )
    for row in tables[label].rows:
        if row.include and row.include not in tables:
            raise StandardTableError(
                f"{name}: {label} includes {row.include}, which is not in the file"
            )
        if row.include:
            _check_includes(tables, row.include, (*chain, label), name)


def _definitions(
    tables: Mapping[str, AttributeTable],
    label: str,
    module: str,
    enclosing: tuple[str, ...],
    via: tuple[str, ...],
) -> Iterator[AttributeDefinition]:
    """Yield the definitions of a table's rows, with each include expanded."""
    path = list(enclosing)
    for row in tables[label].rows:
        del path[len(enclosing) + row.depth :]
        if row.include:
            yield from _definitions(
                tables, row.include, module, tuple(path), (*via, label)
            )
        elif row.tag:
            yield AttributeDefinition(
                tuple(path), row.tag, row.name, row.type, module, (*via, label)
            )
            path.append(row.tag)


def _iod(entry: object, tables: Mapping[str, AttributeTable], name: str) -> IOD:
    if not isinstance(entry, dict) or set(entry) != _IOD_FIELDS:
        raise StandardTableError(
            f"{name} has an IOD without exactly the fields "
            + ", ".join(sorted(_IOD_FIELDS))
        )
    label = entry["label"]
    if not isinstance(label, str) or not TABLE_LABEL_PATTERN.fullmatch(label):
        raise StandardTableError(f"{name} has an IOD without a table label")
    if not _is_text(entry["iod"]):
        raise StandardTableError(f"{name}: {label} has no IOD name")
    if not isinstance(entry["modules"], list) or not entry["modules"]:
        raise StandardTableError(f"{name}: {label} has no modules")

    modules: list[ModuleUsage] = []
    for number, module in enumerate(entry["modules"], start=1):
        problem = _fields_problem(module, _MODULE_FIELDS, "a module")
        if not problem and not all(
            _is_text(module[field], empty=field == "condition")
            for field in _MODULE_FIELDS
        ):
            problem = "has a module field that is not text, or is empty"
        elif not problem and module["usage"] not in MODULE_USAGES:
            problem = "has a usage other than M, C, or U"
        elif not problem and module["table"] not in tables:
            problem = (
                f"refers to {module['table']}, which is not in the attribute tables"
            )
        if problem:
            raise StandardTableError(f"{name}: {label} module {number} {problem}")
        modules.append(ModuleUsage(**module))
    if len({module.module for module in modules}) != len(modules):
        raise StandardTableError(f"{name}: {label} lists a module more than once")

    definitions = tuple(
        definition
        for module in modules
        for definition in _definitions(tables, module.table, module.module, (), ())
    )
    return IOD(entry["iod"], label, tuple(modules), definitions)


def load_iod_tables(
    modules_path: pathlib.Path | None = None,
    attributes_path: pathlib.Path | None = None,
) -> IODTables:
    """Load the supported IODs, as generated from the pinned edition of PS3.3.

    The files are read once and cached, keyed by their resolved paths.

    Parameters
    ----------
    modules_path : pathlib.Path, optional
        The generated IOD modules tables. Defaults to the ones shipped with
        PyMedPhys.
    attributes_path : pathlib.Path, optional
        The generated module and macro attribute tables. Defaults to the ones
        shipped with PyMedPhys.

    Returns
    -------
    IODTables

    Raises
    ------
    StandardTableError
        If either file is missing, unreadable, not the expected table, or
        without the copyright acknowledgement; if its rows differ from their
        recorded digest; if the files name different editions; or if a table,
        row, IOD, or module lacks its fields or has an invalid value. This
        includes a row nested more deeply than the row above allows, an
        Include of a table the file lacks, a table that includes itself, and
        a module whose attribute table the file lacks.
    """
    return _load_iod_tables(
        _default(modules_path, "iod_modules.json"),
        _default(attributes_path, "module_attributes.json"),
    )


@functools.lru_cache(maxsize=None)
def _load_iod_tables(
    modules_path: pathlib.Path, attributes_path: pathlib.Path
) -> IODTables:
    attributes = _read(attributes_path, MODULE_ATTRIBUTES_TABLE)
    modules = _read(modules_path, IOD_MODULES_TABLE)
    if modules["edition"] != attributes["edition"]:
        raise StandardTableError(
            f"{modules_path.name} and {attributes_path.name} name different editions"
        )

    tables = _attribute_tables(attributes, attributes_path.name)
    iods: dict[str, IOD] = {}
    for entry in modules["rows"]:
        iod = _iod(entry, tables, modules_path.name)
        if iod.name in iods:
            raise StandardTableError(
                f"{modules_path.name} lists {iod.name} more than once"
            )
        iods[iod.name] = iod
    return IODTables(
        edition=modules["edition"],
        acknowledgement=modules["acknowledgement"],
        iods=types.MappingProxyType(iods),
        attribute_tables=types.MappingProxyType(tables),
    )
