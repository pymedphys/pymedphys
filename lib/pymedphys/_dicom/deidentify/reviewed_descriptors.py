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

"""Reviewers' decisions on descriptor values, kept for a site or project.

Under the Clean Descriptors Option, Table E.1-1 and the reviewed rules for
text that it omits give C to free-text descriptors such as Series
Description, Protocol Name, and Image Comments. A reviewer reads a value that
a run held for review and keeps it, maps it to another value, or has it
emptied, as for ROI Names (:mod:`.reviewed_roi_names`). The decisions are kept
in a :class:`ReviewedDescriptors` list for the site or project and reused on
later runs, which is the pooled human review that D-009 requires before a
descriptor string is retained.

A decision is for one attribute, by its tag, and one value, by its exact
spelling once padding is removed, and applies wherever that attribute holds
that value: at the top level or in the items of a sequence, and in any
instance. A value of an attribute whose VR allows several values, such as
Admitting Diagnoses Description (0008,1080), is decided on alone, as each of
its values is. The attributes a decision can be recorded for are those that
:func:`descriptor_attributes` gives. ROI Name (3006,0026) is not one of them,
since the reviewed-names list decides on it.

What a kept or mapped value would write is checked for echoes of the
instance's patient and other person identifiers, as the reviewed tier of ROI
Name cleaning checks it, and held if it echoes one, since a reviewer may have
decided on it for another patient. A value that the list does not cover is
held too, unless the automatic tier of technique descriptors
(:mod:`.technique_descriptors`) keeps it and it echoes no identifier: the
list's decisions take precedence over that tier. The caller holds an instance with a held value for review and does
not release it, unless the user chooses explicitly to empty held values so
that the run proceeds. :class:`DescriptorReviewQueue` collects the distinct
held values of a run for the confidential QC material.

The list holds source values verbatim, so it is confidential state: the
custodian keeps it with the key and subject profiles, outside output and QC
directories. Its ``repr``, the results, and every error message hold no
value. It changes what the engine writes, so the method digest is to cover it
through its keyed digest (:meth:`ReviewedDescriptors.keyed_digest`), which
reveals neither a value nor whether a list holds one to anyone without the
key.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import functools
import json
import os
import pathlib
import re
import types
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from . import custodian_lists, roi_names
from .keys import DeidKey, warn_where_owner_only_modes_are_not_enforced
from .reviewed_roi_names import Review
from .standard import load_data_dictionary, load_table_e1_1
from .supplementary_actions import load_supplementary_actions

if TYPE_CHECKING:
    from .technique_descriptors import TechniqueVocabulary

FORMAT = "pymedphys-deid-reviewed-descriptors/1"
# The domain of the list's keyed digest, which no other derivation uses.
DIGEST_DOMAIN = "reviewed-descriptors"
CLEAN_DESCRIPTORS = "clean_descriptors"
_ROI_NAME = "(3006,0026)"
# The most characters a value of each text VR can hold (PS3.5 Section 6.2).
# UC and UT are limited only by the length of a value field.
MAX_CHARACTERS = types.MappingProxyType(
    {
        "SH": 16,
        "LO": 64,
        "ST": 1024,
        "LT": 10240,
        "UC": 2**32 - 2,
        "UT": 2**32 - 2,
    }
)
# The VRs whose values a backslash separates (PS3.5 Section 6.2); in the
# others, a backslash is a character of the text.
_MULTI_VALUED = frozenset({"SH", "LO", "UC"})
# The control characters that the default character repertoire allows in
# ST, LT, and UT text (PS3.5 Section 6.1.3).
_TEXT_CONTROLS = frozenset("\t\n\f\r")
_TEXT = frozenset({"ST", "LT", "UT"})
# Values may be padded with spaces (PS3.5 Section 6.2); some writers pad with
# NUL instead.
_PADDING = " \x00"
_PRINTABLE_ASCII = re.compile(r"[\x20-\x7e]+")
_NOT_ALPHANUMERIC = re.compile(r"[\W_]+")
# The fewest letters and digits of an identifier, or a word of one, that is
# looked for within a descriptor value's own; a shorter one, such as a
# two-letter family name, is found only as a word, so that it is not found
# inside unrelated words.
MIN_EMBEDDED = 4


class ReviewedDescriptorsError(ValueError):
    """A reviewed descriptors list, or a decision for it, that cannot be used."""


@functools.cache
def descriptor_attributes() -> Mapping[str, str]:
    """Return the attributes whose values a reviewer can decide on, with their VRs.

    They are the attributes that Table E.1-1, or a reviewed rule for text
    that the table omits, gives C under the Clean Descriptors Option, and
    that the pinned data dictionary gives VR SH, LO, ST, LT, UC, or UT, other
    than ROI Name (3006,0026), which the reviewed-names list decides on. The
    sequences, binary values, and code strings given C are not among them.

    Returns
    -------
    Mapping of str to str
        Each tag, as ``(gggg,eeee)``, to its VR. Read-only.
    """
    tags = {
        row.tag
        for row in load_table_e1_1().attributes
        if row.options.get(CLEAN_DESCRIPTORS) == "C"
    } | {
        tag
        for tag, rule in load_supplementary_actions().rules.items()
        if rule.options.get(CLEAN_DESCRIPTORS) == "C"
    }
    vrs = {row.tag: row.vrs for row in load_data_dictionary().attributes}
    return types.MappingProxyType(
        {
            tag: vrs[tag][0]
            for tag in sorted(tags - {_ROI_NAME})
            if len(vrs.get(tag, ())) == 1 and vrs[tag][0] in MAX_CHARACTERS
        }
    )


def stripped(value: str) -> str:
    """Return a value without its padding, as the list holds it."""
    return value.strip(_PADDING)


def _value_problem(value: object, vr: str) -> str | None:
    if not isinstance(value, str):
        return "is not text"
    if not value or value != stripped(value):
        return "is empty or padded"
    allowed = _TEXT_CONTROLS if vr in _TEXT else frozenset()
    # A lone surrogate cannot be encoded, so the list could not be saved.
    if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in allowed for c in value):
        return "holds a control character or a surrogate"
    if vr in _MULTI_VALUED and "\\" in value:
        return "holds a backslash, which separates values of its VR"
    return None


def _written_problem(to: str, vr: str) -> str | None:
    if len(to) > MAX_CHARACTERS[vr]:
        return f"is longer than {vr} allows"
    if vr in _MULTI_VALUED and "\\" in to:
        return "holds a backslash, which separates values of its VR"
    return None


def _decision_problem(tag: object, value: object, decision: object) -> str | None:
    """Return why a decision cannot be recorded, without the value, or None."""
    vr = descriptor_attributes().get(tag) if isinstance(tag, str) else None
    if vr is None:
        return "the attribute is not a descriptor that Clean Descriptors cleans"
    problem = _value_problem(value, vr)
    if problem:
        return f"the value {problem}"
    if not isinstance(decision, ReviewedDescriptor):
        return "the decision must be a ReviewedDescriptor"
    if decision.to is not None:
        problem = _written_problem(decision.to, vr)
        if problem:
            return f"the value to write {problem}"
    return None


class Held(enum.Enum):
    """Why a descriptor value is held for review."""

    UNREVIEWED = "unreviewed"
    ECHOES_IDENTIFIER = "echoes identifier"


@dataclasses.dataclass(frozen=True)
class ReviewedDescriptor:
    """A reviewer's decision on one descriptor value.

    Attributes
    ----------
    review : Review
    to : str or None
        For ``MAP``, the value written instead: printable ASCII, without
        surrounding spaces. :meth:`ReviewedDescriptors.record` also checks
        that the attribute's VR can hold it. None otherwise.

    Raises
    ------
    ReviewedDescriptorsError
        If ``to`` is given for ``KEEP`` or ``EMPTY``, or is not such a value
        for ``MAP``. The message holds no value.
    """

    review: Review
    to: str | None = dataclasses.field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.review, Review):
            raise ReviewedDescriptorsError("the review must be keep, map, or empty")
        if self.review is not Review.MAP:
            if self.to is not None:
                raise ReviewedDescriptorsError("only a mapping has a value to write")
        elif (
            not isinstance(self.to, str)
            or not _PRINTABLE_ASCII.fullmatch(self.to)
            or self.to != self.to.strip(" ")
        ):
            raise ReviewedDescriptorsError(
                "a mapping needs a value of printable ASCII characters, without "
                "surrounding spaces"
            )


class ReviewedDescriptors:
    """The reviewer's decisions on descriptor values for a site or project.

    Use :meth:`open` for the list the custodian keeps, and :meth:`empty` for
    a list kept for one run only. One process at a time should use a list: a
    save replaces the whole file.
    """

    def __init__(
        self,
        path: pathlib.Path | None,
        decisions: dict[str, dict[str, ReviewedDescriptor]],
    ) -> None:
        self._path = path
        self._decisions = decisions

    @classmethod
    def empty(cls) -> ReviewedDescriptors:
        """Return an empty list that is never saved."""
        return cls(None, {})

    @classmethod
    def open(
        cls,
        path: str | os.PathLike,
        *,
        protected_dirs: Iterable[str | os.PathLike] = (),
    ) -> ReviewedDescriptors:
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
        ReviewedDescriptorsError
            If ``path`` is inside a protected directory, or an existing list
            cannot be read, is not a :data:`FORMAT` file, or has a malformed
            or repeated attribute, value, or decision. The message holds no
            value.
        """
        resolved = custodian_lists.custodian_path(
            path,
            protected_dirs,
            what="reviewed descriptors list",
            error=ReviewedDescriptorsError,
        )
        decisions = _read(resolved) if resolved.exists() else {}
        return cls(resolved, decisions)

    def get(self, tag: str, value: str) -> ReviewedDescriptor | None:
        """Return the decision on ``value`` of ``tag``, given without padding, or None."""
        return self._decisions.get(tag, {}).get(value)

    def record(
        self,
        tag: str,
        value: str,
        decision: ReviewedDescriptor,
        *,
        replace: bool = False,
    ) -> None:
        """Record a reviewer's decision on one value of an attribute.

        Raises
        ------
        ReviewedDescriptorsError
            If ``tag`` is not one of :func:`descriptor_attributes`; if
            ``value`` is empty or padded, or holds a character that its VR
            cannot hold in one value; if ``decision`` is not a
            :class:`ReviewedDescriptor`, or maps to a value that the VR
            cannot hold; or if the value already has a different decision and
            ``replace`` is false. The message holds no value.
        """
        problem = _decision_problem(tag, value, decision)
        if problem:
            raise ReviewedDescriptorsError(problem)
        values = self._decisions.setdefault(tag, {})
        if not replace and values.get(value, decision) != decision:
            raise ReviewedDescriptorsError("the value already has a different decision")
        values[value] = decision

    def __len__(self) -> int:
        return sum(len(values) for values in self._decisions.values())

    def snapshot(self) -> ReviewedDescriptors:
        """Return a copy of the decisions as they stand, which is never saved.

        A decision recorded in either list afterwards does not change the
        other, so a run can apply, and record the keyed digest of, one
        version of the list.
        """
        return ReviewedDescriptors(
            None, {tag: dict(values) for tag, values in self._decisions.items()}
        )

    def _document(self) -> dict:
        attributes = {
            tag: {
                value: {"review": d.review.value, "to": d.to}
                if d.review is Review.MAP
                else {"review": d.review.value}
                for value, d in sorted(values.items())
            }
            for tag, values in sorted(self._decisions.items())
            if values
        }
        return {"format": FORMAT, "attributes": attributes}

    def canonical_bytes(self) -> bytes:
        """Return the list's canonical form, which its keyed digest is computed from.

        The form is the list's file without whitespace outside text: one JSON
        object with the members ``format`` (:data:`FORMAT`) and
        ``attributes``, encoded as UTF-8, with every object's members sorted
        by key, compared by code point, and every character other than ``"``,
        ``\\``, and the control characters written as itself. The same
        decisions therefore give the same bytes whatever order they were
        recorded in.

        The bytes hold the list's values, so they are as confidential as the
        list.
        """
        text = json.dumps(
            self._document(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return text.encode("utf-8")

    def keyed_digest(self, key: DeidKey) -> str:
        """Return the list's keyed digest, as 64 lowercase hexadecimal digits.

        It is the HMAC-SHA-256 of :meth:`canonical_bytes` under ``key`` in the
        :data:`DIGEST_DOMAIN` domain (:meth:`~.keys.DeidKey.derive`). The
        same list under the same key always gives the same digest, and any
        change to a decision, a value, or an attribute changes it. Without
        the key, the digest cannot be checked against a guessed list, so it
        reveals no value.

        Raises
        ------
        TypeError
            If ``key`` is not a :class:`~.keys.DeidKey`.
        """
        if not isinstance(key, DeidKey):
            raise TypeError("the list's keyed digest needs a DeidKey")
        return key.derive(DIGEST_DOMAIN, self.canonical_bytes()).hex()

    def __repr__(self) -> str:
        return f"ReviewedDescriptors(values={len(self)})"

    def save(self) -> pathlib.Path:
        """Write the list, replacing the previous version atomically.

        The file is created readable only by its owner where the platform
        enforces file modes; elsewhere a warning says that access depends on
        the directory's access control.

        Raises
        ------
        ReviewedDescriptorsError
            If the list was made by :meth:`empty`, so has no file.
        """
        if self._path is None:
            raise ReviewedDescriptorsError(
                "a list made by empty() has no file to save to"
            )
        custodian_lists.save_document(self._path, self._document())
        warn_where_owner_only_modes_are_not_enforced("reviewed descriptors list")
        return self._path


def _read(path: pathlib.Path) -> dict[str, dict[str, ReviewedDescriptor]]:
    document = custodian_lists.read_document(
        path, what="reviewed descriptors list", error=ReviewedDescriptorsError
    )
    if (
        not isinstance(document, dict)
        or document.keys() != {"format", "attributes"}
        or document["format"] != FORMAT
        or not isinstance(document["attributes"], dict)
    ):
        raise ReviewedDescriptorsError(f"the file is not a {FORMAT} file")
    decisions: dict[str, dict[str, ReviewedDescriptor]] = {}
    for number, (tag, values) in enumerate(document["attributes"].items(), start=1):
        if not isinstance(values, dict) or not values:
            raise ReviewedDescriptorsError(f"attribute {number} is malformed")
        for item, (value, entry) in enumerate(values.items(), start=1):
            where = f"value {item} of attribute {number}"
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("review"), str)
                or entry["review"] not in {r.value for r in Review}
                or entry.keys()
                != ({"review", "to"} if entry["review"] == "map" else {"review"})
            ):
                raise ReviewedDescriptorsError(f"{where} has a malformed decision")
            try:
                decision = ReviewedDescriptor(Review(entry["review"]), entry.get("to"))
            except ReviewedDescriptorsError as error:
                raise ReviewedDescriptorsError(f"{where}: {error}") from None
            problem = _decision_problem(tag, value, decision)
            if problem:
                raise ReviewedDescriptorsError(f"{where}: {problem}")
            decisions.setdefault(tag, {})[value] = decision
    return decisions


class Outcome(enum.Enum):
    """What is written for a descriptor value."""

    EMPTY = "empty"  # the value was empty
    KEPT = "kept"
    KEPT_BY_VOCABULARY = "kept by vocabulary"  # the automatic tier kept it
    MAPPED = "mapped"
    EMPTIED = "emptied"  # by a reviewer's decision
    HELD = "held"  # for review; nothing is written
    EMPTIED_UNREVIEWED = "emptied unreviewed"  # held, but the user chose to empty


# The outcomes that a reviewer's decision gives, apart from the empty value.
REVIEWED = frozenset({Outcome.EMPTY, Outcome.KEPT, Outcome.MAPPED, Outcome.EMPTIED})


@dataclasses.dataclass(frozen=True)
class CleanedDescriptor:
    """What is written for one descriptor value, and why.

    Attributes
    ----------
    outcome : Outcome
    held_because : Held or None
        Why the value is ``HELD`` or ``EMPTIED_UNREVIEWED``; None otherwise.
    value : str or None
        The value written, without padding, which is None where the value is
        held. It is left out of the ``repr``, since a kept value is a source
        value.
    """

    outcome: Outcome
    held_because: Held | None
    value: str | None = dataclasses.field(repr=False)


_OUTCOMES = {
    Review.KEEP: Outcome.KEPT,
    Review.MAP: Outcome.MAPPED,
    Review.EMPTY: Outcome.EMPTIED,
}


def clean_descriptor_values(
    tag: str,
    values: Sequence[str],
    reviewed: ReviewedDescriptors,
    *,
    identifiers: Iterable[str],
    vocabulary: TechniqueVocabulary | None = None,
    empty_held: bool = False,
) -> tuple[CleanedDescriptor, ...]:
    """Decide what is written for each value of one descriptor element.

    Parameters
    ----------
    tag : str
        The attribute's tag, one of :func:`descriptor_attributes`.
    values : sequence of str
        The element's decoded values, in order, with or without their
        padding: one for a VR that holds one value, or for an element with
        one value.
    reviewed : ReviewedDescriptors
    identifiers : iterable of str
        The decoded values of the instance's patient and other person
        identifiers, as for :func:`.roi_names.clean_roi_names`.
    vocabulary : TechniqueVocabulary, optional
        The automatic tier (:mod:`.technique_descriptors`), which keeps a
        value that the list does not cover where it is made only of
        vocabulary words. The list's decision takes precedence. Without it,
        every value the list does not cover is held.
    empty_held : bool, optional
        Whether to empty a held value rather than hold it, as the user may
        choose explicitly so that the run proceeds.

    Returns
    -------
    tuple of CleanedDescriptor
        One for each value, in the same order.

    Raises
    ------
    TypeError
        If ``values`` or ``identifiers`` is a single string, or holds
        anything but strings. The message holds no value.
    ValueError
        If ``tag`` is not one of :func:`descriptor_attributes`.
    """
    if tag not in descriptor_attributes():
        raise ValueError(
            "the attribute is not a descriptor that Clean Descriptors cleans"
        )
    if isinstance(values, (str, bytes)) or isinstance(identifiers, (str, bytes)):
        raise TypeError("values and identifiers must be sequences of strings")
    values, identifiers = tuple(values), tuple(identifiers)
    if not all(isinstance(value, str) for value in values + identifiers):
        raise TypeError("values and identifiers must all be strings")
    results = []
    for value in map(stripped, values):
        result = _decide(tag, value, reviewed, identifiers, vocabulary)
        if empty_held and result.outcome is Outcome.HELD:
            result = CleanedDescriptor(
                Outcome.EMPTIED_UNREVIEWED, result.held_because, ""
            )
        results.append(result)
    return tuple(results)


def _decide(
    tag: str,
    value: str,
    reviewed: ReviewedDescriptors,
    identifiers: Sequence[str],
    vocabulary: TechniqueVocabulary | None,
) -> CleanedDescriptor:
    if not value:
        return CleanedDescriptor(Outcome.EMPTY, None, "")
    decision = reviewed.get(tag, value)
    if decision is None:
        if vocabulary is None or not vocabulary.keeps(tag, value):
            return CleanedDescriptor(Outcome.HELD, Held.UNREVIEWED, None)
        if echoes_identifier(value, identifiers):
            return CleanedDescriptor(Outcome.HELD, Held.ECHOES_IDENTIFIER, None)
        return CleanedDescriptor(Outcome.KEPT_BY_VOCABULARY, None, value)
    written = {Review.KEEP: value, Review.MAP: decision.to, Review.EMPTY: ""}[
        decision.review
    ]
    if written and echoes_identifier(written, identifiers):
        return CleanedDescriptor(Outcome.HELD, Held.ECHOES_IDENTIFIER, None)
    return CleanedDescriptor(_OUTCOMES[decision.review], None, written)


def echoes_identifier(value: str, identifiers: Iterable[str]) -> bool:
    """Return whether a descriptor value echoes a known identifier.

    It does where ROI Name cleaning finds an echo
    (:func:`.roi_names.echoes_identifier`): a word of ``value`` of more than
    one character is a word of an identifier, or the whole value is a whole
    identifier, once case and characters that are not letters or digits are
    disregarded. Since free text can also run an identifier into other text
    or reformat it, such as a Patient ID ``991234`` written as
    ``MRN 99-1234``, or a name ``NG^JANE`` as ``JANENG``, it does too where a
    whole identifier, or a word of one, of at least :data:`MIN_EMBEDDED`
    letters and digits is found among the value's letters and digits, so
    disregarded.
    """
    identifiers = tuple(identifiers)
    if roi_names.echoes_identifier(value, identifiers):
        return True
    text = _letters_and_digits(value)
    parts = {
        part
        for identifier in identifiers
        for part in (
            _letters_and_digits(identifier),
            *_NOT_ALPHANUMERIC.split(identifier.casefold()),
        )
    }
    return any(len(part) >= MIN_EMBEDDED and part in text for part in parts)


def _letters_and_digits(text: str) -> str:
    return _NOT_ALPHANUMERIC.sub("", text.casefold())


@dataclasses.dataclass(frozen=True)
class PendingDescriptor:
    """A distinct descriptor value held for review.

    Attributes
    ----------
    tag : str
        The attribute's tag.
    value : str
        The value, without its padding. It is left out of the ``repr``.
    reasons : frozenset of Held
        Every reason it was held for.
    elements : int
        How many elements held it.
    """

    tag: str
    value: str = dataclasses.field(repr=False)
    reasons: frozenset[Held]
    elements: int


@dataclasses.dataclass(frozen=True)
class DescriptorCounts:
    """What a run wrote for descriptor values, as counts without values.

    Only positive counts are present.

    Attributes
    ----------
    held : Mapping of Held to int
        How many distinct values, each of one attribute, were held for each
        reason, whether they were then held or emptied unreviewed. A value
        held for two reasons counts once for each. Read-only.
    outcomes : Mapping of Outcome to int
        How many values had each outcome, counting every value of every
        element added. Read-only.
    """

    # Mappings are not hashable, so they are left out of the hash.
    held: Mapping[Held, int] = dataclasses.field(hash=False)
    outcomes: Mapping[Outcome, int] = dataclasses.field(hash=False)

    def __post_init__(self) -> None:
        for field in ("held", "outcomes"):
            counts = {k: v for k, v in dict(getattr(self, field)).items() if v > 0}
            object.__setattr__(self, field, types.MappingProxyType(counts))


class DescriptorReviewQueue:
    """The descriptor values of a run, and the distinct values it held.

    :meth:`entries` lists the held values, with the values, for the
    confidential QC material; :meth:`report_counts` counts them by reason,
    and every value by outcome, without values, for the release report.
    """

    def __init__(self) -> None:
        self._reasons: dict[tuple[str, str], set[Held]] = collections.defaultdict(set)
        self._counts: collections.Counter[tuple[str, str]] = collections.Counter()
        self._outcomes: collections.Counter[Outcome] = collections.Counter()

    def add(
        self, tag: str, values: Sequence[str], results: Sequence[CleanedDescriptor]
    ) -> None:
        """Add the values of one element, with what is written for each.

        Raises
        ------
        ValueError
            If there is not one result for each value.
        """
        if len(values) != len(results):
            raise ValueError("there must be one result for each value")
        held: dict[str, set[Held]] = {}
        for value, result in zip(values, results):
            if result.held_because is not None:
                held.setdefault(stripped(value), set()).add(result.held_because)
        for value, reasons in held.items():
            self._reasons[(tag, value)] |= reasons
            self._counts[(tag, value)] += 1
        self._outcomes.update(result.outcome for result in results)

    def entries(self) -> tuple[PendingDescriptor, ...]:
        """Return each distinct held value, sorted by tag, then value."""
        return tuple(
            PendingDescriptor(
                tag, value, frozenset(reasons), self._counts[(tag, value)]
            )
            for (tag, value), reasons in sorted(self._reasons.items())
        )

    def report_counts(self) -> DescriptorCounts:
        """Return the held values by reason and every value by outcome, without values."""
        held: collections.Counter[Held] = collections.Counter()
        for reasons in self._reasons.values():
            held.update(reasons)
        return DescriptorCounts(held=dict(held), outcomes=dict(self._outcomes))

    def __repr__(self) -> str:
        return f"DescriptorReviewQueue(values={len(self._reasons)})"
