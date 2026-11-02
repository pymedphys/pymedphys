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

"""Parse the DICOM PS3.15 Annex E tables and paragraphs that de-identification needs.

The tables are Table E.1-1, the attribute confidentiality profile; Table
E.1-1a, its action codes; Table E.3.4-1, the concept names of content items
for the Clean Structured Content Option; and Table E.3.10-1, the safe private
attributes. The paragraphs are those that contain "shall", outside Notes and
tables, which the requirements register records.
"""

from __future__ import annotations

import dataclasses
import posixpath
import re
import types
from collections.abc import Collection, Iterator, Mapping
from html.parser import HTMLParser

from pymedphys._dicom.deidentify.codes import (
    CODE_MEANING_MAX_LENGTH,
    CODE_VALUE_MAX_LENGTH,
)
from pymedphys._dicom.deidentify.requirements import AnnexEParagraph
from pymedphys._dicom.deidentify.standard import (
    ACTION_CODES,
    PRIVATE_ATTRIBUTES_TAG,
    ActionCode,
    ProfileAttribute,
    SafePrivateAttribute,
    is_private_tag,
    is_vm,
    is_vr_text,
)
from pymedphys._dicom.deidentify.structured_content import (
    VALUE_TYPES,
    ContentItemConcept,
    is_code_text,
    split_designator,
)

from .chtml import (
    HtmlTable,
    TableFormatError,
    _normalise,
    check_columns,
    check_unique,
)

TABLE_E1_1 = "Table E.1-1"
TABLE_E1_1A = "Table E.1-1a"
TABLE_E3_4_1 = "Table E.3.4-1"
TABLE_E3_10_1 = "Table E.3.10-1"

# Columns are matched by their header text, so a new edition that reorders
# them still parses, and one that adds, renames, or removes one fails.
_NAME = "Attribute Name"
_TAG = "Tag"
_RETIRED = "Retd. (from PS3.6)"
_IN_STANDARD_IOD = "In Std. Comp. IOD (from PS3.3)"
_BASIC_PROFILE = "Basic Prof."

OPTION_COLUMNS = {
    "Rtn. Safe Priv. Opt.": "retain_safe_private",
    "Rtn. UIDs Opt.": "retain_uids",
    "Rtn. Dev. Id. Opt.": "retain_device_identity",
    "Rtn. Inst. Id. Opt.": "retain_institution_identity",
    "Rtn. Pat. Chars. Opt.": "retain_patient_characteristics",
    "Rtn. Long. Full Dates Opt.": "retain_longitudinal_full_dates",
    "Rtn. Long. Modif. Dates Opt.": "retain_longitudinal_modified_dates",
    "Clean Desc. Opt.": "clean_descriptors",
    "Clean Struct. Cont. Opt.": "clean_structured_content",
    "Clean Graph. Opt.": "clean_graphics",
}

COLUMNS = (_NAME, _TAG, _RETIRED, _IN_STANDARD_IOD, _BASIC_PROFILE, *OPTION_COLUMNS)

# A tag, where an "x" stands for any hexadecimal digit, as in (60xx,3000).
_TAG_PATTERN = re.compile(r"\([0-9A-Fx]{4},[0-9A-Fx]{4}\)")


def _flag(value: str, column: str, row: int, table: str = TABLE_E1_1) -> bool:
    if value == "Y":
        return True
    if value == "N":
        return False
    raise TableFormatError(f"{table} row {row}: {column} is {value!r}, not Y or N")


def _action(value: str, column: str, row: int, table: str = TABLE_E1_1) -> str:
    if value not in ACTION_CODES:
        raise TableFormatError(
            f"{table} row {row}: {column} has action {value!r}, "
            "which is not defined in Table E.1-1a"
        )
    return value


def _tag(value: str, row: int) -> str:
    if value != PRIVATE_ATTRIBUTES_TAG and not _TAG_PATTERN.fullmatch(value):
        raise TableFormatError(
            f"{TABLE_E1_1} row {row}: tag {value!r} is not recognised"
        )
    return value


def parse_table_e1_1(table: HtmlTable) -> tuple[ProfileAttribute, ...]:
    """Parse Table E.1-1 of DICOM PS3.15 Annex E.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.1-1"``.

    Returns
    -------
    tuple of ProfileAttribute
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if a Y/N column holds
        anything else; if a tag has an unrecognised form or appears more than
        once; if an action is not defined in Table E.1-1a; or if the table
        has no rows. The Basic Profile action is required; option actions may
        be empty.
    """
    check_columns(TABLE_E1_1, table.header, COLUMNS)
    if not table.rows:
        raise TableFormatError(f"{TABLE_E1_1} has no rows")

    attributes = []
    for number, cells in enumerate(table.rows, start=1):
        row = dict(zip(table.header, cells))
        name = row[_NAME]
        if not name:
            raise TableFormatError(
                f"{TABLE_E1_1} row {number}: the attribute name is empty"
            )
        attributes.append(
            ProfileAttribute(
                name=name,
                tag=_tag(row[_TAG], number),
                retired=_flag(row[_RETIRED], _RETIRED, number),
                in_standard_iod=_flag(row[_IN_STANDARD_IOD], _IN_STANDARD_IOD, number),
                basic_profile=_action(row[_BASIC_PROFILE], _BASIC_PROFILE, number),
                options=types.MappingProxyType(
                    {
                        option: _action(row[column], column, number)
                        for column, option in OPTION_COLUMNS.items()
                        if row[column]
                    }
                ),
            )
        )

    check_unique(TABLE_E1_1, (attribute.tag for attribute in attributes))
    return tuple(attributes)


def parse_table_e1_1a(table: HtmlTable) -> tuple[ActionCode, ...]:
    """Parse Table E.1-1a of DICOM PS3.15 Annex E, the action codes.

    The published table has no header row: each row is a code and its
    description.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.1-1a"``.

    Returns
    -------
    tuple of ActionCode
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If the table has a header row or no rows; if a row does not have
        exactly two cells or has an empty description; or if the codes are
        not exactly :data:`~pymedphys._dicom.deidentify.standard.ACTION_CODES`,
        each once. A new edition that adds or removes a code therefore fails
        until the engine implements the change.
    """
    if table.header:
        raise TableFormatError(
            f"{TABLE_E1_1A} has a header row; expected only code and description rows"
        )
    if not table.rows:
        raise TableFormatError(f"{TABLE_E1_1A} has no rows")

    codes = []
    for number, cells in enumerate(table.rows, start=1):
        if len(cells) != 2:
            raise TableFormatError(
                f"{TABLE_E1_1A} row {number} has {len(cells)} cells, not 2"
            )
        code, description = cells
        if code not in ACTION_CODES:
            raise TableFormatError(
                f"{TABLE_E1_1A} row {number}: {code!r} is not an action code "
                "PyMedPhys implements"
            )
        if not description:
            raise TableFormatError(
                f"{TABLE_E1_1A} row {number}: the description is empty"
            )
        codes.append(ActionCode(code=code, description=description))

    check_unique(TABLE_E1_1A, (action.code for action in codes))
    missing = ACTION_CODES - {action.code for action in codes}
    if missing:
        raise TableFormatError(
            f"{TABLE_E1_1A} does not define {', '.join(sorted(missing))}"
        )
    return tuple(codes)


# Columns of Table E.3.10-1 by header text, and the field each fills.
E3_10_1_COLUMNS = {
    "Data Element": "tag",
    "Private Creator": "private_creator",
    "VR": "vr",
    "VM": "vm",
    "Meaning": "meaning",
}


def parse_table_e3_10_1(table: HtmlTable) -> tuple[SafePrivateAttribute, ...]:
    """Parse Table E.3.10-1 of DICOM PS3.15 Annex E, the safe private attributes.

    Cell text is kept as published, including lower-case hexadecimal digits
    in some tags, empty VRs, and empty meanings.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.3.10-1"``.

    Returns
    -------
    tuple of SafePrivateAttribute
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a Data Element is not a private tag of the form
        ``(gggg,xxee)``; if a private creator is empty; if a VR is neither
        empty nor one or more VRs from PS3.5 Table 6.2-1 such as ``OW/OB``;
        if a VM is not of the form ``1``, ``1-n``, or ``3-4`` with ascending
        bounds; or if a private creator and tag appear more than once,
        comparing tags without regard to case.
    """
    check_columns(TABLE_E3_10_1, table.header, E3_10_1_COLUMNS)
    if not table.rows:
        raise TableFormatError(f"{TABLE_E3_10_1} has no rows")

    attributes = []
    for number, cells in enumerate(table.rows, start=1):
        row = {
            E3_10_1_COLUMNS[column]: cell for column, cell in zip(table.header, cells)
        }
        where = f"{TABLE_E3_10_1} row {number}"
        if not is_private_tag(row["tag"]):
            raise TableFormatError(
                f"{where}: {row['tag']!r} is not a private Data Element such as "
                "(0019,xx0C)"
            )
        if not row["private_creator"]:
            raise TableFormatError(f"{where}: the private creator is empty")
        if not is_vr_text(row["vr"]):
            raise TableFormatError(f"{where}: VR {row['vr']!r} is not recognised")
        if not is_vm(row["vm"]):
            raise TableFormatError(f"{where}: VM {row['vm']!r} is not recognised")
        attributes.append(SafePrivateAttribute(**row))

    check_unique(
        TABLE_E3_10_1,
        (f"{a.private_creator} {a.tag.upper()}" for a in attributes),
    )
    return tuple(attributes)


# Columns of Table E.3.4-1 by header text. The flags and actions are headed as
# in Table E.1-1, except that the table records whether a code is retired in
# PS3.16 and used in a template of PS3.16, and has no column for the Retain
# Safe Private, Clean Structured Content, or Clean Graphics Options.
_CODE_MEANING = "Code Meaning"
_CODE_VALUE = "Code Value"
_DESIGNATOR = "Coding Scheme Designator"
_VALUE_TYPE = "Value Type"
_RETIRED_CODE = "Retd. (from PS3.16)"
_IN_STANDARD_TEMPLATE = "In Std. Tpl. (from PS3.16)"
E3_4_1_OPTION_COLUMNS = {
    column: option
    for column, option in OPTION_COLUMNS.items()
    if option
    not in ("retain_safe_private", "clean_structured_content", "clean_graphics")
}
E3_4_1_COLUMNS = (
    _CODE_MEANING,
    _CODE_VALUE,
    _DESIGNATOR,
    _VALUE_TYPE,
    _RETIRED_CODE,
    _IN_STANDARD_TEMPLATE,
    _BASIC_PROFILE,
    *E3_4_1_OPTION_COLUMNS,
)


def _content_item_concept(row: dict[str, str], number: int) -> ContentItemConcept:
    """Return a row of Table E.3.4-1, checking each of its cells."""
    where = f"{TABLE_E3_4_1} row {number}"
    if not is_code_text(row[_CODE_MEANING], CODE_MEANING_MAX_LENGTH):
        raise TableFormatError(
            f"{where}: the code meaning is not text of at most 64 characters"
        )
    if not is_code_text(row[_CODE_VALUE], CODE_VALUE_MAX_LENGTH):
        raise TableFormatError(
            f"{where}: the code value is not text of at most 16 characters"
        )
    designator = split_designator(row[_DESIGNATOR])
    if designator is None:
        raise TableFormatError(
            f"{where}: coding scheme designator {row[_DESIGNATOR]!r} is not recognised"
        )
    if row[_VALUE_TYPE] not in VALUE_TYPES:
        raise TableFormatError(
            f"{where}: value type {row[_VALUE_TYPE]!r} is not defined in PS3.3"
        )
    return ContentItemConcept(
        code_meaning=row[_CODE_MEANING],
        code_value=row[_CODE_VALUE],
        scheme_designator=designator[0],
        scheme_version=designator[1],
        value_type=row[_VALUE_TYPE],
        retired=_flag(row[_RETIRED_CODE], _RETIRED_CODE, number, TABLE_E3_4_1),
        in_standard_template=_flag(
            row[_IN_STANDARD_TEMPLATE], _IN_STANDARD_TEMPLATE, number, TABLE_E3_4_1
        ),
        basic_profile=_action(
            row[_BASIC_PROFILE], _BASIC_PROFILE, number, TABLE_E3_4_1
        ),
        options=types.MappingProxyType(
            {
                option: _action(row[column], column, number, TABLE_E3_4_1)
                for column, option in E3_4_1_OPTION_COLUMNS.items()
                if row[column]
            }
        ),
    )


def parse_table_e3_4_1(
    table: HtmlTable, designators: frozenset[str], left_out: frozenset[str]
) -> tuple[ContentItemConcept, ...]:
    """Parse Table E.3.4-1 of DICOM PS3.15 Annex E, keeping the rows of some schemes.

    The table gives the Coding Scheme Version after the designator, in
    brackets, where it gives one, as in ``"NCDR [2.0b]"``.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.3.4-1"``.
    designators : frozenset of str
        The coding schemes whose rows are kept, by designator without
        version, such as ``"DCM"``.
    left_out : frozenset of str
        The coding schemes whose rows are left out. Every row's scheme must
        be in exactly one of the two sets, and every scheme in them must have
        a row, so that a new edition that adds or drops a scheme fails until
        the pin is reviewed.

    Returns
    -------
    tuple of ContentItemConcept
        One per kept row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a code meaning is not text of at most 64 characters or a
        code value of at most 16, or either has leading or trailing spaces, a
        backslash, or a control character; if a designator is not one such
        as ``"DCM"``, optionally followed by a version in brackets; if a
        value type is not one of PS3.3 Section C.17.3.2.1; if a Y/N column
        holds anything else; if an action is not defined in Table E.1-1a,
        the Basic Profile action being required; if a designator, code value,
        and value type appear more than once; or if the schemes do not match
        ``designators`` and ``left_out`` as described above.
    """
    check_columns(TABLE_E3_4_1, table.header, E3_4_1_COLUMNS)
    if not table.rows:
        raise TableFormatError(f"{TABLE_E3_4_1} has no rows")
    both = designators & left_out
    if both:
        raise TableFormatError(
            f"{TABLE_E3_4_1}: the pin both keeps and leaves out "
            + ", ".join(sorted(both))
        )

    concepts = [
        _content_item_concept(dict(zip(table.header, cells)), number)
        for number, cells in enumerate(table.rows, start=1)
    ]
    check_unique(
        TABLE_E3_4_1,
        (
            f"{concept.scheme_designator} {concept.code_value} {concept.value_type}"
            for concept in concepts
        ),
    )

    found = {concept.scheme_designator for concept in concepts}
    unknown = found - designators - left_out
    if unknown:
        raise TableFormatError(
            f"{TABLE_E3_4_1} has rows of coding schemes the pin neither keeps nor "
            "leaves out: " + ", ".join(sorted(unknown))
        )
    absent = (designators | left_out) - found
    if absent:
        raise TableFormatError(
            f"{TABLE_E3_4_1} has no rows of coding schemes the pin names: "
            + ", ".join(sorted(absent))
        )
    return tuple(
        concept for concept in concepts if concept.scheme_designator in designators
    )


# The paragraphs of Annex E that contain "shall". Each chtml page gives each
# paragraph an anchor, and links to the next page in the head.
FIRST_PAGE = "chtml/part15/chapter_E.html"
_ANNEX_E_PAGE = re.compile(r"(?:chapter_E|sect_E(?:\.[0-9]+)+)\.html")
_PARAGRAPH_ANCHOR = re.compile(
    r"para_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
_SHALL = re.compile(r"\bshall\b")
# Elements with no content or end tag.
_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "wbr"}
)
# Divisions whose paragraphs are not requirements: Notes, tables, and the
# page's navigation. Any division not listed here or below fails parsing, so
# that a new kind of content is reviewed before it is read or skipped.
_SKIPPED = frozenset({"note", "table", "navheader", "navfooter", "breadcrumbs"})
_READ = frozenset({"chapter", "section", "titlepage"})
# The divisions that hold a list, which a paragraph before them introduces.
_LISTS = frozenset({"itemizedlist", "orderedlist"})


@dataclasses.dataclass
class _Element:
    tag: str
    attributes: dict[str, str]
    children: list[_Element | str] = dataclasses.field(default_factory=list)

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attributes.get("class", "").split())

    def elements(self) -> list[_Element]:
        return [child for child in self.children if isinstance(child, _Element)]

    def iter(self) -> Iterator[_Element]:
        yield self
        for child in self.elements():
            yield from child.iter()

    def text(self) -> str:
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag == "br":
                parts.append(" ")
            else:
                parts.append(child.text())
        return "".join(parts)


class _TreeBuilder(HTMLParser):
    """Build a page's element tree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("", {})
        self._open = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = _Element(tag, {name: value or "" for name, value in attrs})
        self._open[-1].children.append(element)
        if tag not in _VOID:
            self._open.append(element)

    def handle_endtag(self, tag: str) -> None:
        # Close the innermost open element of this tag, and any left open in it.
        for depth in range(len(self._open) - 1, 0, -1):
            if self._open[depth].tag == tag:
                del self._open[depth:]
                return

    def handle_data(self, data: str) -> None:
        self._open[-1].children.append(data)


@dataclasses.dataclass
class _Walk:
    """The page being read, the section reached, and the paragraphs found."""

    page: str
    section: str = ""
    paragraphs: list[AnnexEParagraph] = dataclasses.field(default_factory=list)


def _anchor(paragraph: _Element, where: str) -> str:
    """Return the anchor that a paragraph starts with."""
    first = next(iter(paragraph.elements()), None)
    anchor = first.attributes.get("id", "") if first and first.tag == "a" else ""
    if not _PARAGRAPH_ANCHOR.fullmatch(anchor):
        raise TableFormatError(f"{where}: a paragraph with 'shall' has no anchor")
    return anchor


def _list_text(division: _Element, where: str) -> str:
    """Return the items of a list, one per line, each marked as published."""
    (kind,) = division.classes & _LISTS
    lists = [child for child in division.elements() if child.tag in ("ul", "ol")]
    if len(lists) != 1:
        raise TableFormatError(f"{where}: a list is not one ul or ol element")
    lines = []
    for number, item in enumerate(lists[0].elements(), start=1):
        content = [child for child in item.elements() if not child.classes & {"note"}]
        if item.tag != "li" or [child.tag for child in content] != ["p"]:
            raise TableFormatError(
                f"{where}: item {number} of a list that a paragraph with 'shall' "
                "introduces is not one paragraph"
            )
        marker = "-" if kind == "itemizedlist" else f"{number}."
        lines.append(f"{marker} {_normalise(content[0].text())}")
    if not lines:
        raise TableFormatError(f"{where}: a list has no items")
    return "\n".join(lines)


def _walk(element: _Element, walk: _Walk) -> None:
    """Find the paragraphs with "shall" below ``element``, in document order."""
    children = element.elements()
    folded: set[int] = set()
    for index, child in enumerate(children):
        anchor = child.attributes.get("id", "")
        if child.tag == "a" and anchor.startswith("sect_"):
            walk.section = anchor.removeprefix("sect_")
        if index in folded or child.tag == "table" or child.classes & _SKIPPED:
            continue
        if child.tag == "p":
            text = _normalise(child.text())
            if not _SHALL.search(text):
                continue
            where = (
                f"{posixpath.basename(walk.page)} section {walk.section or '(none)'}"
            )
            if not walk.section.startswith("E"):
                raise TableFormatError(
                    f"{where}: a paragraph with 'shall' is outside a section"
                )
            following = children[index + 1] if index + 1 < len(children) else None
            if following is not None and following.classes & _LISTS:
                text += "\n\n" + _list_text(following, where)
                folded.add(index + 1)
            walk.paragraphs.append(
                AnnexEParagraph(
                    section=walk.section,
                    page=walk.page,
                    anchor=_anchor(child, where),
                    text=text,
                )
            )
            continue
        unknown = child.classes - _READ - _LISTS if child.tag == "div" else frozenset()
        if unknown:
            raise TableFormatError(
                f"{posixpath.basename(walk.page)}: a division of class "
                f"{' '.join(sorted(unknown))!r} is neither read nor skipped"
            )
        _walk(child, walk)


def _next_page(root: _Element, page: str) -> str:
    """Return the path of the page that the ``Next`` link in the head names."""
    links = [
        element.attributes.get("href", "")
        for element in root.iter()
        if element.tag == "link" and element.attributes.get("rel") == "next"
    ]
    if len(links) != 1 or not links[0] or "/" in links[0]:
        raise TableFormatError(
            f"{posixpath.basename(page)} does not link to one next page of its part"
        )
    return posixpath.join(posixpath.dirname(page), links[0])


def parse_annex_e_paragraphs(
    pages: Mapping[str, bytes], pinned: Collection[str]
) -> tuple[tuple[AnnexEParagraph, ...], tuple[str, ...]]:
    """Parse the paragraphs of PS3.15 Annex E that contain "shall".

    Starting from :data:`FIRST_PAGE`, each page's ``Next`` link is followed
    until it leaves Annex E. A paragraph is a ``p`` element; those in Notes
    and tables are skipped. A paragraph with "shall" that a list follows
    introduces it, and the list's items are added to its text rather than
    read as paragraphs of their own.

    Parameters
    ----------
    pages : mapping of str to bytes
        The pages, by their paths below ``output/``.
    pinned : collection of str
        The paths of the pages of Annex E that the pin lists.

    Returns
    -------
    paragraphs : tuple of AnnexEParagraph
        In the standard's order.
    read : tuple of str
        The pages read, in order.

    Raises
    ------
    TableFormatError
        If the ``Next`` links reach a page of Annex E that ``pinned`` lacks,
        reach a page twice, or do not reach one that it lists; if a page does
        not link to exactly one next page; if a division is of a class
        neither read nor skipped; if a paragraph with "shall" is outside a
        section of Annex E or does not start with its anchor, or introduces a
        list whose items are not each one paragraph; if an anchor repeats; or
        if no paragraph contains "shall".
    """
    paragraphs: list[AnnexEParagraph] = []
    read: list[str] = []
    page = FIRST_PAGE
    while _ANNEX_E_PAGE.fullmatch(posixpath.basename(page)):
        if page in read:
            raise TableFormatError(f"the Next links reach {page} twice")
        if page not in pinned:
            raise TableFormatError(
                f"Annex E continues on {page}, which the pin does not list"
            )
        read.append(page)
        builder = _TreeBuilder()
        builder.feed(pages[page].decode("utf-8"))
        builder.close()
        walk = _Walk(page)
        _walk(builder.root, walk)
        paragraphs.extend(walk.paragraphs)
        page = _next_page(builder.root, page)

    unread = sorted(set(pinned) - set(read))
    if unread:
        raise TableFormatError(
            "the Next links of Annex E do not reach " + ", ".join(unread)
        )
    if not paragraphs:
        raise TableFormatError("no paragraph of Annex E contains 'shall'")
    check_unique("Annex E", (paragraph.anchor for paragraph in paragraphs))
    return tuple(paragraphs), tuple(read)
