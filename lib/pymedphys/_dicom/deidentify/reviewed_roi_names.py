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
"""The reviewed-names list for ROI Name cleaning.

Under the Clean Descriptors Option, ROI Name (3006,0026) is cleaned in two
tiers (D-009). The automatic tier (:mod:`.roi_names`) writes a ROI Name that
matches the published TG-263 vocabulary in the vocabulary's spelling. Every
other name is for human review: a reviewer keeps it, maps it to another name,
or has it emptied. This module holds those decisions, in a
:class:`ReviewedNames` list for the site or project that is reused on later
runs. A decision applies to every ROI Name with exactly its spelling, once
the name's padding is removed, so a mapping is a bulk rename across a
collection. Applying the decisions to a structure set comes separately.

The list holds source ROI Names verbatim, so it is confidential state: the
custodian keeps it with the key and subject profiles, outside output and QC
directories (D-016). Its ``repr`` and every error message hold no name.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import pathlib
import re
import tempfile
import unicodedata
from collections.abc import Iterable

from .keys import (
    custodian_location_problem,
    warn_where_owner_only_modes_are_not_enforced,
)

FORMAT = "pymedphys-deid-reviewed-roi-names/1"
# A name written to ROI Name (3006,0026), which is LO, in the default
# repertoire: at most 64 printable ASCII characters other than backslash
# (PS3.5 Section 6.2), with no padding.
_LO_NAME = re.compile(
    r"[\x21-\x5b\x5d-\x7e](?:[\x20-\x5b\x5d-\x7e]{0,62}[\x21-\x5b\x5d-\x7e])?"
)
# LO values may be padded with spaces (PS3.5 Section 6.2); some writers pad
# with NUL instead.
_PADDING = " \x00"


class ReviewedNamesError(ValueError):
    """A reviewed-names list, or a decision for it, that cannot be used."""


class Review(enum.Enum):
    """A reviewer's decision on a ROI Name."""

    KEEP = "keep"
    MAP = "map"
    EMPTY = "empty"


@dataclasses.dataclass(frozen=True)
class ReviewedName:
    """A reviewer's decision on one ROI Name.

    Attributes
    ----------
    review : Review
    to : str or None
        For ``MAP``, the name written instead: at most 64 printable ASCII
        characters, without a backslash or surrounding spaces. None otherwise.

    Raises
    ------
    ReviewedNamesError
        If ``to`` is given for ``KEEP`` or ``EMPTY``, or is not such a name
        for ``MAP``. The message holds no name.
    """

    review: Review
    to: str | None = dataclasses.field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.review, Review):
            raise ReviewedNamesError("the review must be keep, map, or empty")
        if self.review is not Review.MAP:
            if self.to is not None:
                raise ReviewedNamesError("only a mapping has a name to write")
        elif not isinstance(self.to, str) or not _LO_NAME.fullmatch(self.to):
            raise ReviewedNamesError(
                "a mapping needs a name of 1 to 64 printable ASCII characters, "
                "without a backslash or surrounding spaces"
            )


def _name_problem(name: object) -> str | None:
    if not isinstance(name, str):
        return "is not text"
    if not name or name != name.strip(_PADDING):
        return "is empty or padded"
    # A lone surrogate cannot be encoded, so the list could not be saved.
    if "\\" in name or any(unicodedata.category(c) in {"Cc", "Cs"} for c in name):
        return "holds a backslash, a control character, or a surrogate"
    return None


class ReviewedNames:
    """The reviewer's decisions on ROI Names for a site or project.

    Use :meth:`open` for the list the custodian keeps, and :meth:`empty` for
    a list kept for one run only. One process at a time should use a list: a
    save replaces the whole file.
    """

    def __init__(
        self, path: pathlib.Path | None, names: dict[str, ReviewedName]
    ) -> None:
        self._path = path
        self._names = names

    @classmethod
    def empty(cls) -> ReviewedNames:
        """Return an empty list that is never saved."""
        return cls(None, {})

    @classmethod
    def open(
        cls,
        path: str | os.PathLike,
        *,
        protected_dirs: Iterable[str | os.PathLike] = (),
    ) -> ReviewedNames:
        """Open the list at ``path``, or start a new one there.

        Parameters
        ----------
        path : str or os.PathLike
            The list, in a location only the custodian can read.
        protected_dirs : iterable of str or os.PathLike, optional
            Directories the list must not be inside, such as a run's output
            and QC directories. The PyMedPhys configuration directory is
            always protected.

        Raises
        ------
        ReviewedNamesError
            If ``path`` is inside a protected directory, or an existing list
            cannot be read, is not a :data:`FORMAT` file, or has a malformed
            or repeated name or decision. The message holds no name.
        """
        given = pathlib.Path(path).absolute()
        resolved = given.parent.resolve() / given.name
        problem = custodian_location_problem(resolved, protected_dirs)
        if problem:
            raise ReviewedNamesError(
                f"refusing to keep a reviewed-names list {problem}"
            )
        names = _read(resolved) if resolved.exists() else {}
        return cls(resolved, names)

    def get(self, name: str) -> ReviewedName | None:
        """Return the decision on ``name``, given without its padding, or None."""
        return self._names.get(name)

    def record(
        self, name: str, decision: ReviewedName, *, replace: bool = False
    ) -> None:
        """Record a reviewer's decision on a ROI Name.

        Raises
        ------
        ReviewedNamesError
            If ``name`` is empty, padded, or holds a backslash, a control
            character, or a surrogate; if ``decision`` is not a
            :class:`ReviewedName`; or if the name already has a different
            decision and ``replace`` is false.
        """
        problem = _name_problem(name)
        if problem:
            raise ReviewedNamesError(f"the ROI Name {problem}")
        if not isinstance(decision, ReviewedName):
            raise ReviewedNamesError("the decision must be a ReviewedName")
        if not replace and self._names.get(name, decision) != decision:
            raise ReviewedNamesError("the ROI Name already has a different decision")
        self._names[name] = decision

    def __len__(self) -> int:
        return len(self._names)

    def __repr__(self) -> str:
        return f"ReviewedNames(names={len(self)})"

    def save(self) -> pathlib.Path:
        """Write the list, replacing the previous version atomically.

        The file is created readable only by its owner where the platform
        enforces file modes; elsewhere a warning says that access depends on
        the directory's access control.

        Raises
        ------
        ReviewedNamesError
            If the list was made by :meth:`empty`, so has no file.
        """
        if self._path is None:
            raise ReviewedNamesError("a list made by empty() has no file to save to")
        names = {
            name: {"review": d.review.value, "to": d.to}
            if d.review is Review.MAP
            else {"review": d.review.value}
            for name, d in sorted(self._names.items())
        }
        text = json.dumps(
            {"format": FORMAT, "names": names}, indent=1, ensure_ascii=False
        )
        # mkstemp creates the file readable and writable only by its owner.
        descriptor, temporary = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".part"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                file.write(text + "\n")
            os.replace(temporary, self._path)
        except BaseException:
            pathlib.Path(temporary).unlink(missing_ok=True)
            raise
        warn_where_owner_only_modes_are_not_enforced("reviewed-names list")
        return self._path


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for number, (key, value) in enumerate(pairs, start=1):
        if key in document:
            raise ReviewedNamesError(
                f"item {number} of an object in the list is repeated"
            )
        document[key] = value
    return document


def _read(path: pathlib.Path) -> dict[str, ReviewedName]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs
        )
    except ReviewedNamesError:
        raise
    except (OSError, ValueError, RecursionError):
        # Not chained, since a decoding or parsing error holds the file's text.
        raise ReviewedNamesError("the reviewed-names list could not be read") from None
    if (
        not isinstance(document, dict)
        or document.keys() != {"format", "names"}
        or document["format"] != FORMAT
        or not isinstance(document["names"], dict)
    ):
        raise ReviewedNamesError(f"the file is not a {FORMAT} file")
    names = {}
    for number, (name, entry) in enumerate(document["names"].items(), start=1):
        problem = _name_problem(name)
        if problem:
            raise ReviewedNamesError(f"name {number} {problem}")
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("review"), str)
            or entry["review"] not in {r.value for r in Review}
            or entry.keys()
            != ({"review", "to"} if entry["review"] == "map" else {"review"})
        ):
            raise ReviewedNamesError(f"name {number} has a malformed decision")
        try:
            names[name] = ReviewedName(Review(entry["review"]), entry.get("to"))
        except ReviewedNamesError as error:
            raise ReviewedNamesError(f"name {number}: {error}") from None
    return names
