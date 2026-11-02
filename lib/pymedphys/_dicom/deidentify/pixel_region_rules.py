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

"""Reviewed region rules for the Clean Pixel Data Option (D-037).

Equipment that burns text into its images usually burns it in the same
places: a header band of an ultrasound scanner, or the corner where a
workstation writes the patient's name on a screen capture. A reviewer who
has seen such text records a rule: the rectangles to black out in every
frame of every image of one kind, keyed by the instance's SOP Class UID
(0008,0016), Manufacturer (0008,0070), Manufacturer's Model Name
(0008,1090), Rows (0028,0010), and Columns (0028,0011). The rules are kept in
a :class:`PixelRegionRules` store for the site or project and reused on
later runs.

Under the option, :func:`~.pixel_cleaning.black_out` blacks out a matching
rule's rectangles in every frame alongside the regions that the text finder
finds, and the instance is held for review as every instance that the
option cleans is. The QC pack lists the rule's rectangles among each frame's
regions, and records which of them a rule gave, so a reviewer's verdict
accepts them with the finder's, and a later run given the verdict blacks
them out again without the store. A rule therefore adds regions that the
finder could miss, such as faint text; it never removes one, and never
releases an instance without review.

A key matches an instance whose five attributes have exactly the key's
values, the Manufacturer and Manufacturer's Model Name without their padding
and compared with case, and Rows and Columns as integers. An instance that
lacks one of them, or holds one in another form, such as several values,
matches no rule. Each rectangle lies within the key's Rows and Columns, so a
rule never needs to be clipped to the frame it is applied to.

The store holds Manufacturer and Manufacturer's Model Name verbatim, which
together can identify a site's equipment, so it is kept as the
reviewed-names list is (:mod:`.custodian_lists`): with the key and subject
profiles, outside output and QC directories, readable only by its owner.
Its ``repr`` and every error message hold no value. It changes what the
engine writes, so the method digest covers it through its keyed digest
(:meth:`PixelRegionRules.keyed_digest`).

Examples
--------
A custodian records a rule from an instance that a reviewer has seen, and
saves the store:

.. code-block:: python

    rules = PixelRegionRules.open(path, protected_dirs=[output, qc])
    rules.record(key_of(dataset), [TextBox(0, 0, 40, 640)])
    rules.save()

:mod:`.pixel_region_rules_command` does this from an attested QC pack,
recording only regions that the reviewer's verdict approved for an image,
under the key of the source file that the pack binds.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import unicodedata
from collections.abc import Iterable

from pymedphys._imports import pydicom

from . import custodian_lists
from .diagnostics import redacted_diagnostics
from .keys import DeidKey, warn_where_owner_only_modes_are_not_enforced
from .text_detection import TextBox
from .uid_registry import UID_PATTERN

FORMAT = "pymedphys-deid-pixel-region-rules/1"
# The domain of the store's keyed digest, which no other derivation uses.
DIGEST_DOMAIN = "pixel-region-rules"
# What a store is called in its errors.
_WHAT = "pixel region rules store"
# LO values may be padded with spaces (PS3.5 Section 6.2); some writers pad
# with NUL instead.
_PADDING = " \x00"
# The most characters of an LO value (PS3.5 Table 6.2-1), and the largest
# value of US.
_LO_LENGTH = 64
_US_MAX = 0xFFFF
_UID_LENGTH = 64
_MEMBERS = frozenset(
    {"sop_class_uid", "manufacturer", "model_name", "rows", "columns", "boxes"}
)


class PixelRegionRulesError(ValueError):
    """A region rules store, or a rule for it, that cannot be used."""


def _text_problem(value: object) -> str | None:
    if not isinstance(value, str):
        return "is not text"
    if not value or value != value.strip(_PADDING):
        return "is empty or padded"
    if len(value) > _LO_LENGTH:
        return f"is longer than {_LO_LENGTH} characters"
    # A lone surrogate cannot be encoded, so the store could not be saved.
    if "\\" in value or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        return "holds a backslash, a control character, or a surrogate"
    return None


def _is_size(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and 0 < value <= _US_MAX
    )


@dataclasses.dataclass(frozen=True, order=True)
class RuleKey:
    """The kind of image that a rule applies to.

    Attributes
    ----------
    sop_class_uid : str
        SOP Class UID (0008,0016).
    manufacturer : str
        Manufacturer (0008,0070), without its padding. Left out of the
        ``repr``, as a source value.
    model_name : str
        Manufacturer's Model Name (0008,1090), without its padding. Left out
        of the ``repr``, as a source value.
    rows, columns : int
        Rows (0028,0010) and Columns (0028,0011).

    Raises
    ------
    PixelRegionRulesError
        If the SOP Class UID is not a UID; if the Manufacturer or
        Manufacturer's Model Name is empty, padded, longer than 64
        characters, or holds a backslash, a control character, or a
        surrogate; or if Rows or Columns is not an integer from 1 to 65535.
        The message holds no value.
    """

    sop_class_uid: str
    manufacturer: str = dataclasses.field(repr=False)
    model_name: str = dataclasses.field(repr=False)
    rows: int
    columns: int

    def __post_init__(self) -> None:
        if not (
            isinstance(self.sop_class_uid, str)
            and len(self.sop_class_uid) <= _UID_LENGTH
            and UID_PATTERN.fullmatch(self.sop_class_uid)
        ):
            raise PixelRegionRulesError("a rule's SOP Class UID must be a UID")
        for name, value in (
            ("Manufacturer", self.manufacturer),
            ("Manufacturer's Model Name", self.model_name),
        ):
            problem = _text_problem(value)
            if problem:
                raise PixelRegionRulesError(f"a rule's {name} {problem}")
        if not (_is_size(self.rows) and _is_size(self.columns)):
            raise PixelRegionRulesError(
                "a rule's Rows and Columns must be integers from 1 to 65535"
            )


def key_of(dataset: pydicom.Dataset) -> RuleKey | None:
    """Return the key of an instance's data set, or None if it has none.

    Parameters
    ----------
    dataset : pydicom.Dataset
        The instance's source data set.

    Returns
    -------
    RuleKey or None
        None where SOP Class UID, Manufacturer, Manufacturer's Model Name,
        Rows, or Columns is absent, empty, or not one value of a key's form,
        so that the instance matches no rule.
    """
    try:
        with redacted_diagnostics():
            uid = dataset["SOPClassUID"].value
            manufacturer = dataset["Manufacturer"].value
            model_name = dataset["ManufacturerModelName"].value
            rows, columns = dataset["Rows"].value, dataset["Columns"].value
        return RuleKey(
            str(uid).rstrip(_PADDING) if isinstance(uid, str) else uid,
            manufacturer.strip(_PADDING)
            if isinstance(manufacturer, str)
            else manufacturer,
            model_name.strip(_PADDING) if isinstance(model_name, str) else model_name,
            rows,
            columns,
        )
    # pydicom raises many types for a value it cannot read, and a message can
    # quote the value; an absent attribute raises KeyError.
    except Exception:  # pylint: disable = broad-exception-caught
        return None


def _boxes(key: RuleKey, boxes: object) -> tuple[TextBox, ...]:
    """Return the boxes of a rule, sorted, each once.

    Raises
    ------
    PixelRegionRulesError
        If ``boxes`` is not a sequence of at least one TextBox, or one goes
        past the key's Rows or Columns.
    """
    if isinstance(boxes, (str, bytes)) or not isinstance(boxes, Iterable):
        raise PixelRegionRulesError("a rule needs a sequence of TextBox objects")
    given = tuple(boxes)
    if not given or not all(isinstance(box, TextBox) for box in given):
        raise PixelRegionRulesError("a rule needs at least one TextBox")
    if any(box.bottom > key.rows or box.right > key.columns for box in given):
        raise PixelRegionRulesError(
            "a rule's region goes past the Rows or Columns of its key"
        )
    return tuple(sorted(set(given)))


class PixelRegionRules:
    """The reviewed region rules of a site or project.

    Use :meth:`open` for the store the custodian keeps, and :meth:`empty`
    for a store kept for one run only. One process at a time should use a
    store: a save replaces the whole file.
    """

    def __init__(
        self, path: pathlib.Path | None, rules: dict[RuleKey, tuple[TextBox, ...]]
    ) -> None:
        self._path = path
        self._rules = rules

    @classmethod
    def empty(cls) -> PixelRegionRules:
        """Return an empty store that is never saved."""
        return cls(None, {})

    @classmethod
    def open(
        cls,
        path: str | os.PathLike,
        *,
        protected_dirs: Iterable[str | os.PathLike] = (),
    ) -> PixelRegionRules:
        """Open the store at ``path``, or start a new one there.

        Parameters
        ----------
        path : str or os.PathLike
            The store, in a location only the custodian can read.
        protected_dirs : iterable of str or os.PathLike, optional
            Directories the store must not be inside, such as a run's output
            and QC directories. The PyMedPhys configuration directory is
            always protected.

        Raises
        ------
        PixelRegionRulesError
            If ``path`` is inside a protected directory, or an existing store
            cannot be read, is not a :data:`FORMAT` file, or has a malformed
            rule, a repeated key, or a repeated region in a rule. The message
            holds no value.
        """
        resolved = custodian_lists.custodian_path(
            path, protected_dirs, what=_WHAT, error=PixelRegionRulesError
        )
        rules = _read(resolved) if resolved.exists() else {}
        return cls(resolved, rules)

    def get(self, key: RuleKey | None) -> tuple[TextBox, ...]:
        """Return the regions of the rule for ``key``, or none if it has none."""
        return self._rules.get(key, ()) if isinstance(key, RuleKey) else ()

    def boxes_for(self, dataset: pydicom.Dataset) -> tuple[TextBox, ...]:
        """Return the regions to black out in every frame of an instance.

        They are those of the rule whose key is :func:`key_of` the
        instance's source data set, sorted, each once, or none where no rule
        matches.
        """
        return self.get(key_of(dataset)) if self._rules else ()

    def record(
        self, key: RuleKey, boxes: Iterable[TextBox], *, replace: bool = False
    ) -> None:
        """Record a reviewer's rule.

        Raises
        ------
        PixelRegionRulesError
            If ``key`` is not a :class:`RuleKey`; if ``boxes`` holds no
            TextBox, or anything else, or a box that goes past the key's
            Rows or Columns; or if the key already has other regions and
            ``replace`` is false.
        """
        if not isinstance(key, RuleKey):
            raise PixelRegionRulesError("a rule's key must be a RuleKey")
        regions = _boxes(key, boxes)
        if not replace and self._rules.get(key, regions) != regions:
            raise PixelRegionRulesError("the key already has other regions")
        self._rules[key] = regions

    def remove(self, key: RuleKey) -> None:
        """Remove the rule for ``key``, if there is one."""
        self._rules.pop(key, None)

    def __len__(self) -> int:
        return len(self._rules)

    def snapshot(self) -> PixelRegionRules:
        """Return a copy of the rules as they stand, which is never saved.

        A rule recorded in either store afterwards does not change the
        other, so a run can apply, and record the keyed digest of, one
        version of the store.
        """
        return PixelRegionRules(None, dict(self._rules))

    def _document(self) -> dict:
        return {
            "format": FORMAT,
            "rules": [
                {
                    "sop_class_uid": key.sop_class_uid,
                    "manufacturer": key.manufacturer,
                    "model_name": key.model_name,
                    "rows": key.rows,
                    "columns": key.columns,
                    "boxes": [
                        [box.top, box.left, box.bottom, box.right] for box in boxes
                    ],
                }
                for key, boxes in sorted(self._rules.items())
            ],
        }

    def canonical_bytes(self) -> bytes:
        """Return the store's canonical form, which its keyed digest is computed from.

        The form is the store's file without whitespace outside text: one
        JSON object with the members ``format`` (:data:`FORMAT`) and
        ``rules``, encoded as UTF-8, with every object's members sorted by
        key, compared by code point, every character other than ``"``,
        ``\\``, and the control characters written as itself, the rules
        sorted by key, and each rule's regions sorted. The same rules
        therefore give the same bytes whatever order they were recorded in.

        The bytes hold the rules' Manufacturer and Manufacturer's Model
        Name, so they are as confidential as the store.
        """
        text = json.dumps(
            self._document(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return text.encode("utf-8")

    def keyed_digest(self, key: DeidKey) -> str:
        """Return the store's keyed digest, as 64 lowercase hexadecimal digits.

        It is the HMAC-SHA-256 of :meth:`canonical_bytes` under ``key`` in
        the :data:`DIGEST_DOMAIN` domain (:meth:`~.keys.DeidKey.derive`),
        which the method digest records in place of the store. The same
        store under the same key always gives the same digest, and any
        change to a rule changes it. Without the key, the digest cannot be
        checked against a guessed store, so it reveals no equipment.

        Raises
        ------
        TypeError
            If ``key`` is not a :class:`~.keys.DeidKey`.
        """
        if not isinstance(key, DeidKey):
            raise TypeError("the store's keyed digest needs a DeidKey")
        return key.derive(DIGEST_DOMAIN, self.canonical_bytes()).hex()

    def __repr__(self) -> str:
        return f"PixelRegionRules(rules={len(self)})"

    def save(self) -> pathlib.Path:
        """Write the store, replacing the previous version atomically.

        The file is created readable only by its owner where the platform
        enforces file modes; elsewhere a warning says that access depends on
        the directory's access control.

        Raises
        ------
        PixelRegionRulesError
            If the store was made by :meth:`empty`, so has no file.
        """
        if self._path is None:
            raise PixelRegionRulesError(
                "a store made by empty() has no file to save to"
            )
        custodian_lists.save_document(self._path, self._document())
        warn_where_owner_only_modes_are_not_enforced(_WHAT)
        return self._path


def _read(path: pathlib.Path) -> dict[RuleKey, tuple[TextBox, ...]]:
    document = custodian_lists.read_document(
        path, what=_WHAT, error=PixelRegionRulesError
    )
    if (
        not isinstance(document, dict)
        or document.keys() != {"format", "rules"}
        or document["format"] != FORMAT
        or not isinstance(document["rules"], list)
    ):
        raise PixelRegionRulesError(f"the file is not a {FORMAT} file")
    rules: dict[RuleKey, tuple[TextBox, ...]] = {}
    for number, entry in enumerate(document["rules"], start=1):
        if not isinstance(entry, dict) or entry.keys() != _MEMBERS:
            raise PixelRegionRulesError(f"rule {number} is malformed")
        try:
            key = RuleKey(
                entry["sop_class_uid"],
                entry["manufacturer"],
                entry["model_name"],
                entry["rows"],
                entry["columns"],
            )
        except PixelRegionRulesError as error:
            raise PixelRegionRulesError(f"rule {number}: {error}") from None
        if key in rules:
            raise PixelRegionRulesError(f"rule {number} repeats another's key")
        boxes = entry["boxes"]
        if not isinstance(boxes, list) or not all(_is_box(box) for box in boxes):
            raise PixelRegionRulesError(
                f"rule {number} needs regions of four integers, each with rows "
                "and columns"
            )
        given = [TextBox(*box) for box in boxes]
        if len(set(given)) != len(given):
            raise PixelRegionRulesError(f"rule {number} repeats a region")
        try:
            rules[key] = _boxes(key, given)
        except PixelRegionRulesError as error:
            raise PixelRegionRulesError(f"rule {number}: {error}") from None
    return rules


def _is_box(box: object) -> bool:
    if not (
        isinstance(box, list)
        and len(box) == 4
        and all(isinstance(n, int) and not isinstance(n, bool) for n in box)
    ):
        return False
    top, left, bottom, right = box
    return 0 <= top < bottom and 0 <= left < right
