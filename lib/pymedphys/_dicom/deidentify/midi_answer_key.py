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

"""Read an answer key of the NCI MIDI validation resources (D-018).

The MIDI-B collection (https://doi.org/10.7937/cf2p-aw56) comes with an answer key for each of its test data sets: an SQLite database
whose table ``answer_data`` has a row for each instance. The row names the
instance by its test data set's Patient ID, Study, Series, and SOP Instance
UIDs, and holds its **checks** as JSON in the column ``AnswerData``: an
object of objects, each with an ``action`` that says what a de-identifier
should have done to one attribute, the attribute's place (``tag_ds``), the
test data set's value (``value``), any text the check compares
(``action_text``), and the answer-key categories that the check scores
under (``answer_category_v2``).

The layout is that which the NCI validation script
(https://github.com/CBIIT/midi_validation_script, commit ``ccc0939``) and its
manual read; this module was written from them, not from a released answer
key, so a key that departs from it is refused rather than guessed at. Text
values are wrapped in ``<`` and ``>``, which are removed. A place is written
as the script's indexer writes it: ``<(0008,1140)>`` at the top level,
``<(0008,1140)>[<0000>]<(0008,1155)>`` inside the first item of a sequence,
and ``<(0019,"CREATOR",92)>`` for a private attribute, by its creator and the
last two hexadecimal digits of its element. A place that cannot be read in
that form is kept as unreadable, so that its check is reported as not
evaluated rather than dropped.

Nothing here quotes a value from the key in a message: the key holds the test
data set's identifiers, synthetic or not.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path

ANSWER_TABLE = "answer_data"
# The columns that the validation script reads from each row, apart from the
# optional "scope".
_COLUMNS = (
    "PatientID",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "SOPClassUID",
    "Modality",
    "AnswerData",
)


class AnswerKeyError(Exception):
    """An answer key that cannot be read. The message quotes no value."""


class Action(enum.Enum):
    """What a check says a de-identifier should have done."""

    # The attribute is present.
    TAG_RETAINED = "tag_retained"
    # The attribute is present with a value.
    TEXT_NOTNULL = "text_notnull"
    # The attribute holds the test data set's text.
    TEXT_RETAINED = "text_retained"
    # The attribute no longer holds the test data set's text.
    TEXT_REMOVED = "text_removed"
    # The attribute no longer holds the test data set's date.
    DATE_SHIFTED = "date_shifted"
    # The attribute no longer holds the test data set's UID.
    UID_CHANGED = "uid_changed"
    # The attribute holds the UID that the mapping gives the test data set's.
    UID_CONSISTENT = "uid_consistent"
    # The attribute holds the Patient ID that the mapping gives the test
    # data set's.
    PATID_CONSISTENT = "patid_consistent"
    # The Pixel Data are unchanged.
    PIXELS_RETAINED = "pixels_retained"
    # Text burned into the pixel data is no longer legible.
    PIXELS_HIDDEN = "pixels_hidden"


# The actions that the validation script fails for an instance missing from
# the output, because they ask for something to be kept; it passes the others.
RETAINING_ACTIONS = frozenset(
    {
        Action.TAG_RETAINED,
        Action.TEXT_NOTNULL,
        Action.TEXT_RETAINED,
        Action.PIXELS_RETAINED,
        Action.UID_CONSISTENT,
        Action.PATID_CONSISTENT,
    }
)


@dataclasses.dataclass(frozen=True)
class Element:
    """One element on an attribute's place.

    Attributes
    ----------
    group : int
    element : int
        For a standard attribute, the element number. For a private one,
        the last two hexadecimal digits of it, since the block that its
        creator reserves differs between files.
    creator : str or None
        A private attribute's creator, in upper case as the script records
        it; ``None`` for a standard attribute.
    """

    group: int
    element: int
    creator: str | None = None

    @property
    def is_private(self) -> bool:
        return self.creator is not None

    def __str__(self) -> str:
        if self.creator is None:
            return f"({self.group:04X},{self.element:04X})"
        # PS3.5 writes a private block's element as "xxee".
        return f"({self.group:04X},xx{self.element:02X})"


@dataclasses.dataclass(frozen=True)
class AttributePath:
    """The place of an attribute: its elements, outermost first.

    Attributes
    ----------
    elements : tuple of Element
        The sequences that hold the attribute, outermost first, and then
        the attribute.
    items : tuple of int
        For each sequence, the index of the item that holds the next
        element, from 0, so one fewer than ``elements``.
    """

    elements: tuple[Element, ...]
    items: tuple[int, ...]

    @property
    def attribute(self) -> Element:
        return self.elements[-1]

    def __str__(self) -> str:
        """The elements, joined by ``/``, without the item indexes."""
        return "/".join(str(element) for element in self.elements)


@dataclasses.dataclass(frozen=True)
class Categories:
    """The answer-key categories of a check, each a code or ``None``.

    The names are those of ``answer_category_v2``'s fields, such as
    ``hipaa.z`` for :attr:`hipaa_z`.
    """

    hipaa_z: str | None = None
    hipaa_m: str | None = None
    dicom_p15: str | None = None
    dicom_iod: str | None = None
    dicom_safe: str | None = None
    tcia_ptkb: str | None = None
    tcia_p15: str | None = None
    tcia_rev: str | None = None


@dataclasses.dataclass(frozen=True, order=True)
class Category:
    """The category a check is scored under: a family and a code."""

    family: str
    code: str

    def __str__(self) -> str:
        return f"{self.family} {self.code}"


@dataclasses.dataclass(frozen=True)
class Check:
    """One check of an instance.

    Attributes
    ----------
    action : Action or None
        ``None`` for an action that this module does not know.
    action_name : str
        The action as the key names it, without its ``<`` and ``>``.
    path : AttributePath or None
        ``None`` for a check without a place, such as one of pixel data, or
        one whose place could not be read.
    path_unreadable : bool
        Whether the check gave a place that could not be read.
    value : str or None
        The test data set's value.
    action_text : str or None
    categories : Categories
    """

    action: Action | None
    action_name: str
    path: AttributePath | None
    path_unreadable: bool
    value: str | None
    action_text: str | None
    categories: Categories

    @property
    def category(self) -> Category | None:
        """The category the check is scored under, as :func:`category_of` gives it."""
        return category_of(self.action, self.categories)


@dataclasses.dataclass(frozen=True)
class AnswerInstance:
    """An instance of the test data set, with its checks."""

    patient_id: str
    study_instance_uid: str
    series_instance_uid: str
    sop_instance_uid: str
    sop_class_uid: str
    modality: str
    scope: str | None
    checks: tuple[Check, ...]


@dataclasses.dataclass(frozen=True)
class AnswerKey:
    """An answer key, and the SHA-256 of its file, which names its version."""

    instances: tuple[AnswerInstance, ...]
    sha256: str

    def by_sop_instance(self) -> dict[str, AnswerInstance]:
        """The instances by SOP Instance UID; the first row of a repeated UID wins."""
        found: dict[str, AnswerInstance] = {}
        for instance in self.instances:
            found.setdefault(instance.sop_instance_uid, instance)
        return found


def category_of(action: Action | None, categories: Categories) -> Category | None:
    """Return the category that a check is scored under.

    The rule is the validation script's: an action that checks an attribute
    is kept scores under its DICOM IOD category; a shifted date, changed
    UID, and hidden pixels under HIPAA C, R, and A; a consistent Patient ID
    or UID under the Basic Profile's C and U; unchanged pixels under TCIA's
    ``TCIA-P15-PIX-K``; removed text under the first of its HIPAA M, HIPAA
    Z, TCIA P15, TCIA PTKB, and TCIA review categories that it has; and kept
    text under the first of its TCIA P15, PTKB, and review categories.

    Returns
    -------
    Category or None
        ``None`` where the rule gives no category, as the script's reports
        count under ``unknown``.
    """
    fixed = {
        Action.DATE_SHIFTED: ("hipaa", "HIPAA-C"),
        Action.UID_CHANGED: ("hipaa", "HIPAA-R"),
        Action.PIXELS_HIDDEN: ("hipaa", "HIPAA-A"),
        Action.PATID_CONSISTENT: ("dicom", "DICOM-P15-BASIC-C"),
        Action.UID_CONSISTENT: ("dicom", "DICOM-P15-BASIC-U"),
        Action.PIXELS_RETAINED: ("tcia", "TCIA-P15-PIX-K"),
    }
    if action in fixed:
        return Category(*fixed[action])
    if action in (Action.TAG_RETAINED, Action.TEXT_NOTNULL):
        ordered = [("dicom", categories.dicom_iod)]
    elif action is Action.TEXT_REMOVED:
        ordered = [
            ("hipaa", categories.hipaa_m),
            ("hipaa", categories.hipaa_z),
            ("tcia", categories.tcia_p15),
            ("tcia", categories.tcia_ptkb),
            ("tcia", categories.tcia_rev),
        ]
    elif action is Action.TEXT_RETAINED:
        ordered = [
            ("tcia", categories.tcia_p15),
            ("tcia", categories.tcia_ptkb),
            ("tcia", categories.tcia_rev),
        ]
    else:
        return None
    return next((Category(f, code) for f, code in ordered if code), None)


_ELEMENT = (
    r"<\((?P<group>[0-9A-Fa-f]{4}),"
    r"(?:(?P<element>[0-9A-Fa-f]{4})"
    r'|"(?P<creator>[^"]*)",(?P<low>[0-9A-Fa-f]{2}))\)>'
)
_ELEMENT_PATTERN = re.compile(_ELEMENT)
_ITEM_PATTERN = re.compile(r"\[<(?P<item>[0-9]{4,})>\]")


def parse_path(text: str) -> AttributePath | None:
    """Return the place that the script's indexer writes as ``text``.

    Returns
    -------
    AttributePath or None
        ``None`` if ``text`` is not of that form.

    Examples
    --------
    >>> str(parse_path("<(0008,1140)>[<0001>]<(0008,1155)>"))
    '(0008,1140)/(0008,1155)'
    >>> parse_path('<(0019,"SYNTHETIC CREATOR",92)>').attribute.creator
    'SYNTHETIC CREATOR'
    >>> parse_path("(0010,0010)") is None
    True
    """
    elements: list[Element] = []
    items: list[int] = []
    position = 0
    while True:
        match = _ELEMENT_PATTERN.match(text, position)
        if match is None:
            return None
        group = int(match["group"], 16)
        if match["creator"] is None:
            elements.append(Element(group, int(match["element"], 16)))
        else:
            elements.append(Element(group, int(match["low"], 16), match["creator"]))
        position = match.end()
        if position == len(text):
            return AttributePath(tuple(elements), tuple(items))
        item = _ITEM_PATTERN.match(text, position)
        if item is None:
            return None
        items.append(int(item["item"]))
        position = item.end()


def unwrap(value: object) -> str | None:
    """Return a text value without the ``<`` and ``>`` that wrap it.

    Anything but text is ``None``; so is text that is not wrapped.
    """
    if not isinstance(value, str) or len(value) < 2:
        return None
    if value[0] != "<" or value[-1] != ">":
        return None
    return value[1:-1]


def read_answer_key(path: str | Path) -> AnswerKey:
    """Read the answer key in the SQLite database at ``path``.

    Raises
    ------
    AnswerKeyError
        If the file is not an SQLite database with the table and columns
        that the validation script reads, a row's identifiers are not text,
        or its checks are not JSON of the script's form.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError:
        raise AnswerKeyError("the answer key could not be read") from None
    return AnswerKey(tuple(_instances(path)), hashlib.sha256(data).hexdigest())


def _instances(path: Path) -> Iterator[AnswerInstance]:
    try:
        connection = sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        raise AnswerKeyError("the answer key is not an SQLite database") from None
    try:
        try:
            names = [
                row[1]
                for row in connection.execute(f"PRAGMA table_info({ANSWER_TABLE})")
            ]
        except sqlite3.Error:
            raise AnswerKeyError("the answer key is not an SQLite database") from None
        missing = [column for column in _COLUMNS if column not in names]
        if not names or missing:
            raise AnswerKeyError(
                f"the answer key has no table {ANSWER_TABLE!r} with the columns "
                f"{', '.join(_COLUMNS)}"
            )
        columns = [*_COLUMNS, *(("scope",) if "scope" in names else ())]
        query = (
            f"SELECT {', '.join(columns)} FROM {ANSWER_TABLE} "  # nosec B608
            "ORDER BY rowid"
        )
        for number, row in enumerate(connection.execute(query), start=1):
            yield _instance(number, dict(zip(columns, row)))
    finally:
        connection.close()


def _instance(number: int, row: Mapping[str, object]) -> AnswerInstance:
    identifiers = {}
    for column in _COLUMNS[:-1]:
        value = row[column]
        if not isinstance(value, str):
            raise AnswerKeyError(f"row {number} has no text {column}")
        identifiers[column] = value
    try:
        answers = json.loads(row["AnswerData"])  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise AnswerKeyError(f"row {number}'s AnswerData is not JSON") from None
    if isinstance(answers, Mapping):
        answers = list(answers.values())
    if not isinstance(answers, list) or not all(
        isinstance(answer, Mapping) for answer in answers
    ):
        raise AnswerKeyError(f"row {number}'s AnswerData is not a set of checks")
    scope = row.get("scope")
    return AnswerInstance(
        patient_id=identifiers["PatientID"],
        study_instance_uid=identifiers["StudyInstanceUID"],
        series_instance_uid=identifiers["SeriesInstanceUID"],
        sop_instance_uid=identifiers["SOPInstanceUID"],
        sop_class_uid=identifiers["SOPClassUID"],
        modality=identifiers["Modality"],
        scope=unwrap(scope) if isinstance(scope, str) else None,
        checks=tuple(parse_check(answer, row=number) for answer in answers),
    )


def parse_check(answer: Mapping[str, object], *, row: int | None = None) -> Check:
    """Return the check that one object of a row's ``AnswerData`` describes.

    Raises
    ------
    AnswerKeyError
        If the check has no action, naming ``row`` if it is given.
    """
    action_name = unwrap(answer.get("action"))
    if action_name is None:
        where = "a check" if row is None else f"a check of row {row}"
        raise AnswerKeyError(f"{where} has no action")
    try:
        action: Action | None = Action(action_name)
    except ValueError:
        action = None
    place = answer.get("tag_ds")
    path = None
    if isinstance(place, str) and place:
        path = parse_path(place)
    return Check(
        action=action,
        action_name=action_name,
        path=path,
        path_unreadable=isinstance(place, str) and bool(place) and path is None,
        value=unwrap(answer.get("value")),
        action_text=unwrap(answer.get("action_text")),
        categories=_categories(answer.get("answer_category_v2")),
    )


def _categories(value: object) -> Categories:
    """Return the categories of ``answer_category_v2``, nested or dotted."""
    if isinstance(value, str):
        try:
            value = json.loads(unwrap(value) or value)
        except ValueError:
            return Categories()
    if not isinstance(value, Mapping):
        return Categories()
    flat: dict[str, object] = {}
    for family, codes in value.items():
        if isinstance(codes, Mapping):
            for name, code in codes.items():
                flat[f"{family}_{name}"] = code
        else:
            flat[str(family).replace(".", "_")] = codes
    return Categories(
        **{
            field.name: code if isinstance(code, str) and code else None
            for field in dataclasses.fields(Categories)
            for code in [flat.get(field.name)]
        }
    )
