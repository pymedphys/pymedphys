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

"""Reviewers' decisions on Presentation State annotations, kept for a site or project.

Under the Clean Graphics Option, Table E.1-1 gives C to Graphic Annotation
Sequence (0070,0001), whose items are the text and graphics that a softcopy
Presentation State draws over its images: arrows, measurements, region
outlines, and typed notes. Text can name the patient, and a polyline can
spell a name, so no automatic check can tell that an annotation is safe to
keep. A reviewer sees each annotation that a run held for review, its text
and a drawing of its graphics in the confidential QC pack, and keeps it or
has it removed. The decisions are kept in a :class:`ReviewedAnnotations`
list for the site or project and reused on later runs, as the reviewed ROI
names and descriptors lists are (:mod:`.reviewed_roi_names`,
:mod:`.reviewed_descriptors`), as the maintainer chose on 7 November 2026
(D-062).

A decision is for one annotation, by its :func:`annotation_digest`: the
SHA-256 of a canonical form of every element of the item but its UIDs,
which name the images that it is drawn on and are replaced as every UID is.
It applies wherever an annotation has that digest: in any instance, at any
position in its sequence. A kept annotation is written as it was received,
but for its UIDs, and one whose text echoes one of its instance's patient or
other person identifiers is held all the same, since a reviewer may have
kept it for another patient (:func:`review_annotation`).

The list holds digests only, but an annotation's text is short and could be
guessed and checked against its digest, so the list is kept as confidential
state, as the other reviewed lists are: the custodian keeps it with the key
and subject profiles, outside output and QC directories. Its ``repr``, the
results, and every error message hold no digest. It changes what the engine
writes, so the method digest covers it through its keyed digest
(:meth:`ReviewedAnnotations.keyed_digest`).
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import hashlib
import json
import math
import os
import pathlib
import re
import types
from collections.abc import Iterable, Mapping, Sequence

from pymedphys._imports import pydicom

from . import custodian_lists
from .keys import DeidKey, warn_where_owner_only_modes_are_not_enforced
from .reviewed_descriptors import echoes_identifier

FORMAT = "pymedphys-deid-reviewed-annotations/1"
# The domain of the list's keyed digest, which no other derivation uses.
DIGEST_DOMAIN = "reviewed-annotations"
# The domain of an annotation's digest, which prefixes its canonical form.
ANNOTATION_DOMAIN = b"pymedphys-deid-annotation/1\x00"
_DIGEST = re.compile(r"[0-9a-f]{64}")
# The padding that a text value may carry, which its canonical form drops.
_PADDING = " \x00"
# The VRs whose values are text, which an annotation's texts are read from.
TEXT_VRS = frozenset({"LO", "LT", "SH", "ST", "UC", "UT", "PN", "CS"})
# The VRs of binary values, written in the canonical form as hexadecimal.
_BYTES_VRS = frozenset({"OB", "OD", "OF", "OL", "OV", "OW", "UN"})


class ReviewedAnnotationsError(ValueError):
    """A reviewed annotations list cannot be opened, read, or changed."""


class Review(enum.Enum):
    """A reviewer's decision on an annotation."""

    KEEP = "keep"
    REMOVE = "remove"


class Held(enum.Enum):
    """Why an annotation is held for review."""

    # the list has no decision on it
    NOT_REVIEWED = "not-reviewed"
    # the list keeps it, but its text echoes one of its instance's patient
    # or other person identifiers
    ECHOES_IDENTIFIER = "echoes-identifier"


class Outcome(enum.Enum):
    """What is written for an annotation."""

    KEPT = "kept"
    REMOVED = "removed"
    HELD = "held"  # for review; its instance is not released


@dataclasses.dataclass(frozen=True)
class ReviewedAnnotation:
    """What is written for one annotation, and why.

    Attributes
    ----------
    outcome : Outcome
    held_because : Held or None
        Why it is ``HELD``; None otherwise.
    """

    outcome: Outcome
    held_because: Held | None = None

    def __post_init__(self) -> None:
        if (self.outcome is Outcome.HELD) != (self.held_because is not None):
            raise ValueError("an annotation has a reason exactly when it is held")


def _canonical(dataset: pydicom.Dataset) -> list:
    """Return the canonical form of a data set's elements but its UIDs.

    Each element is ``[tag, VR, values]``, in the order of the tags, where
    ``values`` is a list: for a sequence, each item's canonical form; for
    text, each value without its padding; for a number, each value as
    ``float.hex`` of its float, or its integer; and for binary data, its
    bytes in hexadecimal.
    """
    form: list = []
    for element in dataset:
        if element.VR == "UI":
            continue
        tag = f"({element.tag.group:04X},{element.tag.element:04X})"
        if element.VR == "SQ":
            values: list = [_canonical(item) for item in element.value]
        elif element.VR in _BYTES_VRS:
            raw = element.value
            values = [] if raw is None else [bytes(raw).hex()]
        else:
            values = [_canonical_value(value) for value in _values(element)]
        form.append([tag, element.VR, values])
    return form


def _values(element: pydicom.DataElement) -> list:
    if element.value is None or element.value == "":
        return []
    if element.VM > 1 or isinstance(element.value, pydicom.multival.MultiValue):
        return list(element.value)
    return [element.value]


def _canonical_value(value: object) -> str | int:
    if isinstance(value, bool):
        raise TypeError("an annotation's value cannot be read")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return repr(value)
        return value.hex()
    if isinstance(value, pydicom.valuerep.PersonName):
        return str(value).rstrip(_PADDING)
    if isinstance(value, str):
        return value.rstrip(_PADDING)
    # DS and IS, which pydicom reads as numbers of its own types.
    if isinstance(value, (pydicom.valuerep.DSfloat, pydicom.valuerep.DSdecimal)):
        return float(value).hex()
    raise TypeError("an annotation's value cannot be read")


def annotation_digest(item: pydicom.Dataset) -> str:
    """Return an annotation's digest, as 64 lowercase hexadecimal digits.

    It is the SHA-256 of :data:`ANNOTATION_DOMAIN` followed by the UTF-8
    JSON, without whitespace, of the canonical form of every element of the
    item but its UIDs, at any depth: each element as its tag, its VR, and
    its values, in the order of its tags. Two annotations that differ in any
    text, coordinate, style, or layer have different digests; two that
    differ only in the images that they name have the same one.

    Raises
    ------
    TypeError
        If a value cannot be read as text, a number, or bytes.
    """
    text = json.dumps(_canonical(item), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(ANNOTATION_DOMAIN + text.encode("utf-8")).hexdigest()


def annotation_texts(item: pydicom.Dataset) -> tuple[str, ...]:
    """Return each text value of an annotation, at any depth, in file order.

    The values of every element whose VR is text (:data:`TEXT_VRS`), each
    without its padding, leaving out empty values. They are what a reviewer
    reads, and what a kept annotation is checked for echoes of its
    instance's identifiers in.
    """
    texts: list[str] = []
    for element in item:
        if element.VR == "SQ":
            for inner in element.value:
                texts.extend(annotation_texts(inner))
        elif element.VR in TEXT_VRS:
            for value in _values(element):
                text = str(value).rstrip(_PADDING)
                if text:
                    texts.append(text)
    return tuple(texts)


def review_annotation(
    digest: str,
    texts: Sequence[str],
    reviewed: ReviewedAnnotations,
    identifiers: Iterable[str],
) -> ReviewedAnnotation:
    """Return what is written for one annotation, from the list's decision.

    An annotation that the list removes is removed. One that it keeps is
    kept, unless one of ``texts`` echoes one of ``identifiers``
    (:func:`~.reviewed_descriptors.echoes_identifier`), so it is held. One
    that the list has no decision on is held.
    """
    decision = reviewed.get(digest)
    if decision is None:
        return ReviewedAnnotation(Outcome.HELD, Held.NOT_REVIEWED)
    if decision is Review.REMOVE:
        return ReviewedAnnotation(Outcome.REMOVED)
    identifiers = tuple(identifiers)
    if any(echoes_identifier(text, identifiers) for text in texts):
        return ReviewedAnnotation(Outcome.HELD, Held.ECHOES_IDENTIFIER)
    return ReviewedAnnotation(Outcome.KEPT)


class ReviewedAnnotations:
    """The reviewer's decisions on annotations for a site or project.

    Use :meth:`open` for the list the custodian keeps, and :meth:`empty` for
    a list kept for one run only. One process at a time should use a list: a
    save replaces the whole file.
    """

    def __init__(self, path: pathlib.Path | None, decisions: dict[str, Review]) -> None:
        self._path = path
        self._decisions = decisions

    @classmethod
    def empty(cls) -> ReviewedAnnotations:
        """Return an empty list that is never saved."""
        return cls(None, {})

    @classmethod
    def open(
        cls,
        path: str | os.PathLike,
        *,
        protected_dirs: Iterable[str | os.PathLike] = (),
    ) -> ReviewedAnnotations:
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
        ReviewedAnnotationsError
            If ``path`` is inside a protected directory, or an existing list
            cannot be read, is not a :data:`FORMAT` file, or has a malformed
            or repeated digest or decision. The message holds no digest.
        """
        resolved = custodian_lists.custodian_path(
            path,
            protected_dirs,
            what="reviewed annotations list",
            error=ReviewedAnnotationsError,
        )
        decisions = _read(resolved) if resolved.exists() else {}
        return cls(resolved, decisions)

    def get(self, digest: str) -> Review | None:
        """Return the decision on the annotation with ``digest``, or None."""
        return self._decisions.get(digest)

    def record(self, digest: str, review: Review, *, replace: bool = False) -> None:
        """Record a reviewer's decision on one annotation, by its digest.

        Raises
        ------
        ReviewedAnnotationsError
            If ``digest`` is not 64 lowercase hexadecimal digits, ``review``
            is not a :class:`Review`, or the annotation already has a
            different decision and ``replace`` is false. The message holds
            no digest.
        """
        problem = _decision_problem(digest, review)
        if problem:
            raise ReviewedAnnotationsError(problem)
        if not replace and self._decisions.get(digest, review) is not review:
            raise ReviewedAnnotationsError(
                "the annotation already has a different decision"
            )
        self._decisions[digest] = review

    def __len__(self) -> int:
        return len(self._decisions)

    def snapshot(self) -> ReviewedAnnotations:
        """Return a copy of the decisions as they stand, which is never saved.

        A decision recorded in either list afterwards does not change the
        other, so a run can apply, and record the keyed digest of, one
        version of the list.
        """
        return ReviewedAnnotations(None, dict(self._decisions))

    def _document(self) -> dict:
        return {
            "format": FORMAT,
            "annotations": {
                digest: {"review": review.value}
                for digest, review in sorted(self._decisions.items())
            },
        }

    def canonical_bytes(self) -> bytes:
        """Return the list's canonical form, which its keyed digest is computed from.

        The form is the list's file without whitespace: one JSON object with
        the members ``format`` (:data:`FORMAT`) and ``annotations``, encoded
        as UTF-8, with every object's members sorted by key. The same
        decisions therefore give the same bytes whatever order they were
        recorded in.
        """
        text = json.dumps(
            self._document(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return text.encode("utf-8")

    def keyed_digest(self, key: DeidKey) -> str:
        """Return the list's keyed digest, as 64 lowercase hexadecimal digits.

        It is the HMAC-SHA-256 of :meth:`canonical_bytes` under ``key`` in the
        :data:`DIGEST_DOMAIN` domain (:meth:`~.keys.DeidKey.derive`), which
        changes with any decision, and cannot be checked against a guessed
        list without the key.

        Raises
        ------
        TypeError
            If ``key`` is not a :class:`~.keys.DeidKey`.
        """
        if not isinstance(key, DeidKey):
            raise TypeError("the list's keyed digest needs a DeidKey")
        return key.derive(DIGEST_DOMAIN, self.canonical_bytes()).hex()

    def __repr__(self) -> str:
        return f"ReviewedAnnotations(annotations={len(self)})"

    def save(self) -> pathlib.Path:
        """Write the list, replacing the previous version atomically.

        The file is created readable only by its owner where the platform
        enforces file modes; elsewhere a warning says that access depends on
        the directory's access control.

        Raises
        ------
        ReviewedAnnotationsError
            If the list was made by :meth:`empty`, so has no file.
        """
        if self._path is None:
            raise ReviewedAnnotationsError(
                "a list made by empty() has no file to save to"
            )
        custodian_lists.save_document(self._path, self._document())
        warn_where_owner_only_modes_are_not_enforced("reviewed annotations list")
        return self._path


def _decision_problem(digest: object, review: object) -> str | None:
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        return "an annotation's digest must be 64 lowercase hexadecimal digits"
    if not isinstance(review, Review):
        return "a decision must be a Review"
    return None


def _read(path: pathlib.Path) -> dict[str, Review]:
    document = custodian_lists.read_document(
        path, what="reviewed annotations list", error=ReviewedAnnotationsError
    )
    if (
        not isinstance(document, dict)
        or document.keys() != {"format", "annotations"}
        or document["format"] != FORMAT
        or not isinstance(document["annotations"], dict)
    ):
        raise ReviewedAnnotationsError(f"the file is not a {FORMAT} file")
    decisions: dict[str, Review] = {}
    reviews = {review.value: review for review in Review}
    for number, (digest, entry) in enumerate(document["annotations"].items(), start=1):
        if (
            not isinstance(entry, dict)
            or entry.keys() != {"review"}
            or not isinstance(entry["review"], str)
            or entry["review"] not in reviews
        ):
            raise ReviewedAnnotationsError(
                f"annotation {number} has a malformed decision"
            )
        problem = _decision_problem(digest, reviews[entry["review"]])
        if problem:
            raise ReviewedAnnotationsError(f"annotation {number}: {problem}")
        decisions[digest] = reviews[entry["review"]]
    return decisions


@dataclasses.dataclass(frozen=True)
class PendingAnnotation:
    """A distinct annotation held for review, for the confidential QC pack.

    Attributes
    ----------
    digest : str
        Its :func:`annotation_digest`, which a reviewer records a decision
        by. It is left out of the ``repr``.
    texts : tuple of str
        Its text values (:func:`annotation_texts`). Left out of the ``repr``.
    reasons : frozenset of Held
        Every reason it was held for.
    instances : int
        How many instances held it.
    """

    digest: str = dataclasses.field(repr=False)
    texts: tuple[str, ...] = dataclasses.field(repr=False)
    reasons: frozenset[Held]
    instances: int


@dataclasses.dataclass(frozen=True)
class AnnotationCounts:
    """What a run wrote for annotations, as counts without text or digests.

    Only positive counts are present.

    Attributes
    ----------
    held : Mapping of Held to int
        How many distinct annotations were held for each reason. One held
        for two reasons counts once for each. Read-only.
    outcomes : Mapping of Outcome to int
        How many annotations had each outcome, counting every annotation of
        every instance added. Read-only.
    """

    held: Mapping[Held, int] = dataclasses.field(hash=False)
    outcomes: Mapping[Outcome, int] = dataclasses.field(hash=False)

    def __post_init__(self) -> None:
        for field in ("held", "outcomes"):
            counts = {k: v for k, v in dict(getattr(self, field)).items() if v > 0}
            object.__setattr__(self, field, types.MappingProxyType(counts))


class AnnotationReviewQueue:
    """The annotations of a run, and the distinct annotations it held.

    :meth:`entries` lists the held annotations, with their texts, for the
    confidential QC material; :meth:`report_counts` counts them by reason,
    and every annotation by outcome, without texts or digests, for the
    release report.
    """

    def __init__(self) -> None:
        self._reasons: dict[str, set[Held]] = collections.defaultdict(set)
        self._texts: dict[str, tuple[str, ...]] = {}
        self._instances: collections.Counter[str] = collections.Counter()
        self._outcomes: collections.Counter[Outcome] = collections.Counter()

    def add(
        self,
        digests: Sequence[str],
        texts: Sequence[tuple[str, ...]],
        results: Sequence[ReviewedAnnotation],
    ) -> None:
        """Add the annotations of one instance, with what is written for each.

        Raises
        ------
        ValueError
            If there is not one digest, one tuple of texts, and one result
            for each annotation.
        """
        if not len(digests) == len(texts) == len(results):
            raise ValueError("there must be one digest and result for each annotation")
        held: dict[str, set[Held]] = {}
        for digest, text, result in zip(digests, texts, results):
            if result.held_because is not None:
                held.setdefault(digest, set()).add(result.held_because)
                self._texts[digest] = tuple(text)
        for digest, reasons in held.items():
            self._reasons[digest] |= reasons
            self._instances[digest] += 1
        self._outcomes.update(result.outcome for result in results)

    def entries(self) -> tuple[PendingAnnotation, ...]:
        """Return each distinct held annotation, sorted by digest."""
        return tuple(
            PendingAnnotation(
                digest,
                self._texts[digest],
                frozenset(self._reasons[digest]),
                self._instances[digest],
            )
            for digest in sorted(self._reasons)
        )

    def report_counts(self) -> AnnotationCounts:
        """Return the held annotations by reason, and every one by outcome."""
        held: collections.Counter[Held] = collections.Counter()
        for reasons in self._reasons.values():
            held.update(reasons)
        return AnnotationCounts(held=dict(held), outcomes=dict(self._outcomes))

    def __repr__(self) -> str:
        return f"AnnotationReviewQueue(annotations={len(self._reasons)})"
