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

"""Clean ROI Names in both tiers: automatic renaming, then reviewed decisions.

The automatic tier (:mod:`.roi_names`) writes a ROI Name that matches the
published TG-263 vocabulary in the vocabulary's spelling. Every other name is
for human review. A reviewer keeps it, maps it to another name, or has it
emptied, and the decisions are kept in a :class:`ReviewedNames` list for the
site or project and reused on later runs. A decision applies to every ROI
Name with exactly that spelling, once its padding is removed, so a mapping is
a bulk rename across a collection.

A name the automatic tier renames is renamed whatever the list says. For
every other name, the list's decision is applied, including for a name the
automatic tier sends to review only because another name of the structure set
would be written the same, so a reviewer can map one of them elsewhere. Then
what would be written is checked again, as the automatic tier checks its own:

- a kept or mapped name that echoes a known patient or other person
  identifier of the instance is held, since a reviewer may have decided on it
  for another patient;
- different names of one structure set that would be written as the same
  name, ignoring case, whether by the automatic tier or the list, are all
  held, since duplicate ROI Names can make a planning system reject the
  import. Several empty names are not duplicates: the Basic Profile itself
  empties every ROI Name.

A name that the list does not cover is held too, with the automatic tier's
reason. The caller holds an instance with a held name for review and does not
release it: a run deletes its staged file, and a run after the review writes
it again. That is unless the user chooses explicitly to empty held names so
that the run proceeds (``empty_held``), which empties a name held by these checks as
well as one the list does not cover. :class:`ReviewQueue` collects the distinct
held names of a run for the confidential QC material.

The list holds source ROI Names verbatim, so it is confidential state: the
custodian keeps it with the key and subject profiles, outside output and QC
directories. Its ``repr``, the results, and every error message hold no name.
It changes what the engine writes, so the method digest covers it through
its keyed digest (:meth:`ReviewedNames.keyed_digest`), which reveals neither
a name nor whether a list holds one to anyone without the key.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import json
import os
import pathlib
import re
import tempfile
import types
import unicodedata
from collections.abc import Iterable, Mapping, Sequence

from . import roi_names
from .keys import (
    DeidKey,
    custodian_location_problem,
    warn_where_owner_only_modes_are_not_enforced,
)
from .roi_names import Reason

FORMAT = "pymedphys-deid-reviewed-roi-names/1"
# The domain of the list's keyed digest, which no other derivation uses.
DIGEST_DOMAIN = "reviewed-roi-names"
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

    def snapshot(self) -> ReviewedNames:
        """Return a copy of the decisions as they stand, which is never saved.

        A decision recorded in either list afterwards does not change the
        other, so a run can apply, and record the keyed digest of, one
        version of the list.
        """
        return ReviewedNames(None, dict(self._names))

    def _document(self) -> dict:
        names = {
            name: {"review": d.review.value, "to": d.to}
            if d.review is Review.MAP
            else {"review": d.review.value}
            for name, d in sorted(self._names.items())
        }
        return {"format": FORMAT, "names": names}

    def canonical_bytes(self) -> bytes:
        """Return the list's canonical form, which its keyed digest is computed from.

        The form is the list's file without whitespace outside text: one JSON
        object with the members ``format`` (:data:`FORMAT`) and ``names``,
        encoded as UTF-8, with every object's members sorted by key, compared
        by code point, and every character other than ``"``, ``\\``, and the
        control characters written as itself. The same decisions therefore
        give the same bytes whatever order they were recorded in.

        The bytes hold the list's names, so they are as confidential as the
        list.
        """
        text = json.dumps(
            self._document(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return text.encode("utf-8")

    def keyed_digest(self, key: DeidKey) -> str:
        """Return the list's keyed digest, as 64 lowercase hexadecimal digits.

        It is the HMAC-SHA-256 of :meth:`canonical_bytes` under ``key`` in the
        :data:`DIGEST_DOMAIN` domain (:meth:`~.keys.DeidKey.derive`), which
        the method digest records in place of the list. The same list under
        the same key always gives the same digest, and any change to a
        decision or a name changes it. Under a key kept for one run only,
        each run's digest differs even for the same list. Without the key,
        the digest cannot be checked against a guessed list, so it reveals no
        name.

        Raises
        ------
        TypeError
            If ``key`` is not a :class:`~.keys.DeidKey`.
        """
        if not isinstance(key, DeidKey):
            raise TypeError("the list's keyed digest needs a DeidKey")
        return key.derive(DIGEST_DOMAIN, self.canonical_bytes()).hex()

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
        text = json.dumps(self._document(), indent=1, ensure_ascii=False)
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


class Outcome(enum.Enum):
    """What is written for a ROI Name."""

    RENAMED = "renamed"  # the automatic tier's vocabulary spelling
    EMPTY = "empty"  # the name was empty
    KEPT = "kept"
    MAPPED = "mapped"
    EMPTIED = "emptied"  # by a reviewer's decision
    HELD = "held"  # for review; nothing is written
    EMPTIED_UNREVIEWED = "emptied unreviewed"  # held, but the user chose to empty


@dataclasses.dataclass(frozen=True)
class CleanedRoiName:
    """What is written for one ROI Name, and why.

    Attributes
    ----------
    outcome : Outcome
    held_because : Reason or None
        Why the name is ``HELD`` or ``EMPTIED_UNREVIEWED``: the automatic
        tier's reason where the list does not cover the name,
        ``ECHOES_IDENTIFIER`` or ``WOULD_DUPLICATE`` where what would be
        written echoes an identifier or duplicates another name. None
        otherwise.
    value : str or None
        The value written, which is None where the name is held. It is left
        out of the ``repr``, since a kept name is a source value.
    """

    outcome: Outcome
    held_because: Reason | None
    value: str | None = dataclasses.field(repr=False)


def clean_roi_names(
    names: Sequence[str],
    vocabulary: roi_names.RoiNameVocabulary | None,
    reviewed: ReviewedNames,
    *,
    identifiers: Iterable[str],
    empty_held: bool = False,
) -> tuple[CleanedRoiName, ...]:
    """Decide what is written for each ROI Name of one structure set.

    Parameters
    ----------
    names : sequence of str
        The decoded ROI Names of one structure set, in order, with or without
        their padding.
    vocabulary : RoiNameVocabulary or None
        The published TG-263 vocabulary, or None, in which case every name
        needs a reviewed decision.
    reviewed : ReviewedNames
    identifiers : iterable of str
        The decoded values of the instance's patient and other person
        identifiers, as for :func:`.roi_names.clean_roi_names`.
    empty_held : bool, optional
        Whether to empty a held name rather than hold it, as the user may
        choose explicitly so that the run proceeds.

    Returns
    -------
    tuple of CleanedRoiName
        One for each name, in the same order.

    Raises
    ------
    TypeError
        If ``names`` or ``identifiers`` is a single string, or holds anything
        but strings. The message holds no value.
    """
    if isinstance(names, (str, bytes)) or isinstance(identifiers, (str, bytes)):
        raise TypeError("ROI Names and identifiers must be sequences of strings")
    names, identifiers = tuple(names), tuple(identifiers)
    if not all(isinstance(value, str) for value in names + identifiers):
        raise TypeError("ROI Names and identifiers must all be strings")
    stripped = [name.strip(_PADDING) for name in names]
    if vocabulary is None:
        automatic = tuple(
            roi_names.RoiNameDecision(
                Reason.EMPTY if not name else Reason.UNMATCHED, "" if not name else None
            )
            for name in stripped
        )
    else:
        automatic = roi_names.clean_roi_names(
            stripped, vocabulary, identifiers=identifiers
        )
    results = [
        _decide(name, decision, vocabulary, reviewed, identifiers)
        for name, decision in zip(stripped, automatic)
    ]
    # Names written the same but for case are duplicates too, since some
    # planning systems compare structure names without case.
    sources: dict[str, set[str]] = collections.defaultdict(set)
    for name, result in zip(stripped, results):
        if result.value:
            sources[result.value.casefold()].add(name)
    for index, result in enumerate(results):
        if result.value and len(sources[result.value.casefold()]) > 1:
            results[index] = CleanedRoiName(Outcome.HELD, Reason.WOULD_DUPLICATE, None)
    if empty_held:
        results = [
            CleanedRoiName(Outcome.EMPTIED_UNREVIEWED, r.held_because, "")
            if r.outcome is Outcome.HELD
            else r
            for r in results
        ]
    return tuple(results)


_OUTCOMES = {
    Review.KEEP: Outcome.KEPT,
    Review.MAP: Outcome.MAPPED,
    Review.EMPTY: Outcome.EMPTIED,
}


def _decide(
    name: str,
    automatic: roi_names.RoiNameDecision,
    vocabulary: roi_names.RoiNameVocabulary | None,
    reviewed: ReviewedNames,
    identifiers: Sequence[str],
) -> CleanedRoiName:
    """Decide on one stripped name, before duplicates among all are considered."""
    if automatic.reason is Reason.MATCHED:
        return CleanedRoiName(Outcome.RENAMED, None, automatic.value)
    if automatic.reason is Reason.EMPTY:
        return CleanedRoiName(Outcome.EMPTY, None, "")
    decision = reviewed.get(name)
    if decision is None:
        if automatic.reason is Reason.WOULD_DUPLICATE and vocabulary is not None:
            # Renamed on its own, it may no longer duplicate a name that the
            # list maps elsewhere; duplicates among all are judged after.
            (alone,) = roi_names.clean_roi_names(
                [name], vocabulary, identifiers=identifiers
            )
            return CleanedRoiName(Outcome.RENAMED, None, alone.value)
        return CleanedRoiName(Outcome.HELD, automatic.reason, None)
    value = {Review.KEEP: name, Review.MAP: decision.to, Review.EMPTY: ""}[
        decision.review
    ]
    if value and roi_names.echoes_identifier(value, identifiers):
        return CleanedRoiName(Outcome.HELD, Reason.ECHOES_IDENTIFIER, None)
    return CleanedRoiName(_OUTCOMES[decision.review], None, value)


@dataclasses.dataclass(frozen=True)
class PendingName:
    """A distinct ROI Name held for review.

    Attributes
    ----------
    name : str
        The ROI Name, without its padding. It is left out of the ``repr``.
    reasons : frozenset of Reason
        Every reason it was held for.
    structure_sets : int
        How many structure sets held it.
    """

    name: str = dataclasses.field(repr=False)
    reasons: frozenset[Reason]
    structure_sets: int


@dataclasses.dataclass(frozen=True)
class RoiNameCounts:
    """What a run wrote for ROI Names, as counts without names, for the release report.

    Only positive counts are present.

    Attributes
    ----------
    held : Mapping of Reason to int
        How many distinct ROI Names were held for each reason, whether they
        were then held or emptied unreviewed, as :meth:`ReviewQueue.summary`
        gives. A name held for two reasons counts once for each. Read-only.
    outcomes : Mapping of Outcome to int
        How many ROI Names had each outcome, counting every name of every
        structure set added. Read-only.
    """

    # Mappings are not hashable, so they are left out of the hash.
    held: Mapping[Reason, int] = dataclasses.field(hash=False)
    outcomes: Mapping[Outcome, int] = dataclasses.field(hash=False)

    def __post_init__(self) -> None:
        for field in ("held", "outcomes"):
            counts = {k: v for k, v in dict(getattr(self, field)).items() if v > 0}
            object.__setattr__(self, field, types.MappingProxyType(counts))


class ReviewQueue:
    """The ROI Names of a run's structure sets, and the distinct names it held.

    :meth:`entries` lists the held names, with the names, for the
    confidential QC material; :meth:`summary` counts them by reason, and
    :meth:`report_counts` also counts every name by outcome, without names,
    for the release report.
    """

    def __init__(self) -> None:
        self._reasons: dict[str, set[Reason]] = collections.defaultdict(set)
        self._counts: collections.Counter[str] = collections.Counter()
        self._outcomes: collections.Counter[Outcome] = collections.Counter()

    def add(self, names: Sequence[str], results: Sequence[CleanedRoiName]) -> None:
        """Add the ROI Names of one structure set, with what is written for each.

        Raises
        ------
        ValueError
            If there is not one result for each name.
        """
        if len(names) != len(results):
            raise ValueError("there must be one result for each name")
        held: dict[str, set[Reason]] = {}
        for name, result in zip(names, results):
            if result.held_because is not None:
                held.setdefault(name.strip(_PADDING), set()).add(result.held_because)
        for name, reasons in held.items():
            self._reasons[name] |= reasons
            self._counts[name] += 1
        self._outcomes.update(result.outcome for result in results)

    def entries(self) -> tuple[PendingName, ...]:
        """Return each distinct held name, sorted by name."""
        return tuple(
            PendingName(name, frozenset(self._reasons[name]), self._counts[name])
            for name in sorted(self._reasons)
        )

    def summary(self) -> Mapping[Reason, int]:
        """Return how many distinct held names have each reason."""
        counts: collections.Counter[Reason] = collections.Counter()
        for reasons in self._reasons.values():
            counts.update(reasons)
        return dict(counts)

    def report_counts(self) -> RoiNameCounts:
        """Return the held names by reason and every name by outcome, without names."""
        return RoiNameCounts(held=self.summary(), outcomes=dict(self._outcomes))

    def __repr__(self) -> str:
        return f"ReviewQueue(names={len(self._reasons)})"
