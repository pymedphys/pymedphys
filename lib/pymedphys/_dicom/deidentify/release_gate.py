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

"""Decide whether a written file may be released, from its residual coverage.

The residual search (:mod:`~pymedphys._dicom.deidentify.residuals`) reports
the source values it found in a written file, and the forms it did not
search. What it cannot report is a value that was never given to it. A
value that de-identification removed or replaced without decoding it was
transformed safely, but its copies in other attributes or encodings were not
searched for, so a search that finds nothing is not on its own a reason to
release the file. :func:`release_condition` therefore runs the search
itself, for exactly the values that the :class:`Coverage` collected, and
decides from both.

**Coverage.** Collection is :attr:`~CollectionOutcome.COMPLETE` only when
each value planned for collection was collected from its decoded form,
under a VR that the pinned dictionary gives its attribute. It is
:attr:`~CollectionOutcome.INCOMPLETE` where a planned value was neither
collected nor reported as not collected; where a value could not be
collected; where text outside ISO 646 with no Specific Character Set was
read only as bytes, as ISO 8859-1, since searching those bytes may still
find a copy but does not stand in for the decoded text; and where a value
was collected under another VR, so that the search derived the wrong forms
from it or left it out. The forms that the search itself leaves out by its
rules, such as forms shorter than four characters and binary values, are its
exclusions; they are listed, and never count as incomplete.
The values searched for in a file, and so its coverage, are pooled across
its subject: the instance's own and those of the subject's other instances
in the run, since a sibling's value that was not collected was not searched
for in this file either. :meth:`Coverage.merge` pools them.

**Decision.** Each reason has a decision, and the file takes the most severe
of them. It is withheld (:attr:`~Decision.WITHHOLD`) when collection is
incomplete for a person name (PN), UID (UI), date (DA), datetime (DT), or
direct identifier (:func:`direct_identifiers`), or for a sequence, whose
items' content is unknown; when the file's structure was not read to its
end; and when the search finds a person name, UID, date, datetime, or
direct identifier anywhere, or anything outside the data set, which
includes Data Set Trailing Padding. Kinds are taken from the VR that the
pinned dictionary gives the source attribute, whatever VR the value was
collected under, and from the search only for an attribute to which the
dictionary gives none. The file goes to QC review (:attr:`~Decision.QC_REVIEW`)
when collection is incomplete for any other value, including a private
value or one to which the dictionary gives no VR, or the search finds other
text inside the data set. Otherwise it may be released
(:attr:`~Decision.RELEASE`). There is no setting that changes this.

Reasons name an attribute path, a code, and for a finding its place, never a
value, and nothing is logged or warned.

Examples
--------
>>> name = ElementPath((), "(0010,0010)")
>>> coverage = Coverage(
...     planned=frozenset({name}),
...     collected=(),
...     uncollected=(Uncollected(name, "could not be decoded"),),
... )
>>> condition = release_condition(coverage, b"")  # not even a preamble
>>> condition
ReleaseCondition(decision='withhold', outcome='incomplete', reasons=2, exclusions=0)
>>> print(condition)
withhold
withhold: (0010,0010): uncollected
withhold: the file: unreadable-file
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import re

from .file_layout import ElementPath, Location, Region
from .residuals import (
    Finding,
    NotSearched,
    ResidualSearch,
    SourceValue,
    ValueKind,
    find_residuals,
)
from .standard import ProfileTable, dictionary_attribute, load_table_e1_1

# The PS3.6 groups of the patient, a visit, the study, and a procedure or
# order, in which direct identifiers are selected.
IDENTIFIER_GROUPS = frozenset({"0008", "0010", "0020", "0032", "0038", "0040"})
IDENTIFIER_WORDS = frozenset({"ID", "IDs", "Number", "Numbers", "Locator"})
# The kinds of value, by VR, that must be collected completely for release.
REQUIRED_KINDS = {
    "PN": ValueKind.PERSON_NAME,
    "UI": ValueKind.UID,
    "DA": ValueKind.DATE,
    "DT": ValueKind.DATETIME,
}
# The reason that Coverage.merge gives a planned value that an instance
# neither collected nor reported as not collected.
NOT_REPORTED = "was planned, but neither collected nor reported as not collected"
# A keyword's words: "IDs", a run of capitals before another capital or the
# end, a capitalised word, or digits.
_WORD = re.compile(r"IDs(?![a-z])|[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|[0-9]+")
_RETAINS_OR_CLEANS = frozenset({"K", "C"})


class CollectionOutcome(enum.Enum):
    """Whether every planned value was collected from its decoded form."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class Decision(enum.Enum):
    """What may happen to a written file, least severe first."""

    RELEASE = "release"
    QC_REVIEW = "qc-review"
    WITHHOLD = "withhold"


_SEVERITY = {decision: index for index, decision in enumerate(Decision)}


class ReasonCode(enum.Enum):
    """Why a file is not released as it is."""

    UNCOLLECTED = "uncollected"  # a value that could not be collected
    NOT_REPORTED = "not-reported"  # planned, but neither collected nor uncollected
    READ_AS_LATIN_1 = "read-as-latin-1"  # text read only as ISO 8859-1 bytes
    COLLECTED_AS_OTHER_VR = "collected-as-other-vr"  # not the dictionary's VR
    UNREADABLE_FILE = "unreadable-file"  # the structure was not read to its end
    RESIDUAL_PERSON_NAME = "residual-person-name"
    RESIDUAL_UID = "residual-uid"
    RESIDUAL_DATE = "residual-date"
    RESIDUAL_DATETIME = "residual-datetime"
    RESIDUAL_DIRECT_IDENTIFIER = "residual-direct-identifier"
    RESIDUAL_OUTSIDE_DATA_SET = "residual-outside-data-set"
    RESIDUAL_TEXT = "residual-text"  # other text, inside the data set


_RESIDUAL_KINDS = {
    ValueKind.PERSON_NAME: ReasonCode.RESIDUAL_PERSON_NAME,
    ValueKind.UID: ReasonCode.RESIDUAL_UID,
    ValueKind.DATE: ReasonCode.RESIDUAL_DATE,
    ValueKind.DATETIME: ReasonCode.RESIDUAL_DATETIME,
}


@dataclasses.dataclass(frozen=True, repr=False)
class Uncollected:
    """A value to search for that could not be collected.

    Its ``repr`` shows only the path.

    Attributes
    ----------
    path : ElementPath
        Where the value was in the source.
    reason : str
        Why, naming no value, such as ``"could not be decoded as VR PN"``.
        It is kept for the confidential QC material, and no decision
        depends on it.

    Raises
    ------
    ValueError
        If the path is not an :class:`ElementPath` or the reason is not
        non-empty text.
    """

    path: ElementPath
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, ElementPath):
            raise ValueError("an uncollected value needs the ElementPath of its source")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError(f"the uncollected value at {self.path} needs a reason")

    def __repr__(self) -> str:
        return f"Uncollected(path={str(self.path)!r})"


@dataclasses.dataclass(frozen=True, repr=False, kw_only=True)
class Coverage:
    """What was planned for collection, what was collected, and what was not.

    Its ``repr`` shows only counts, and its fields are keyword-only.

    Attributes
    ----------
    planned : frozenset of ElementPath
        The source paths of every value that had to be collected, such as
        each element that de-identification removes or replaces.
    collected : tuple of SourceValue
        The values collected, including those read only as bytes. Each is a
        value the written file must not hold, so a value meant to stay,
        such as a registered UID that is retained, is neither planned nor
        collected.
    uncollected : tuple of Uncollected, optional
        The values that could not be collected.
    decoded_as_bytes : frozenset of ElementPath, optional
        The source paths of collected text read as ISO 8859-1, because it
        has bytes outside ISO 646 and no Specific Character Set applies.

    Raises
    ------
    TypeError
        If an attribute is missing, or not of these types.
    """

    planned: frozenset[ElementPath]
    collected: tuple[SourceValue, ...]
    uncollected: tuple[Uncollected, ...] = ()
    decoded_as_bytes: frozenset[ElementPath] = frozenset()

    def __post_init__(self) -> None:
        for name, container, kind in (
            ("planned", frozenset, ElementPath),
            ("collected", tuple, SourceValue),
            ("uncollected", tuple, Uncollected),
            ("decoded_as_bytes", frozenset, ElementPath),
        ):
            given = getattr(self, name)
            if not isinstance(given, container) or not all(
                isinstance(each, kind) for each in given
            ):
                raise TypeError(
                    f"{name} must be a {container.__name__} of {kind.__name__}"
                )

    @classmethod
    def merge(cls, *coverages: Coverage) -> Coverage:
        """Pool the coverage of a subject's instances, in order, once each.

        A value that one instance planned but did not report stays a gap,
        as an :class:`Uncollected` with the reason :data:`NOT_REPORTED`,
        even where another instance collected a value at the same path.

        Parameters
        ----------
        *coverages : Coverage
            Such as an instance's own and those of its subject's other
            instances in the run.

        Returns
        -------
        Coverage

        Raises
        ------
        TypeError
            If any is not a :class:`Coverage`.
        """
        if not all(isinstance(each, Coverage) for each in coverages):
            raise TypeError("only coverages can be merged")
        uncollected = [
            gap
            for each in coverages
            for gap in (
                *each.uncollected,
                *(Uncollected(path, NOT_REPORTED) for path in each.not_reported()),
            )
        ]
        return cls(
            planned=frozenset().union(*(each.planned for each in coverages)),
            collected=tuple(dict.fromkeys(v for c in coverages for v in c.collected)),
            uncollected=tuple(dict.fromkeys(uncollected)),
            decoded_as_bytes=frozenset().union(
                *(each.decoded_as_bytes for each in coverages)
            ),
        )

    def not_reported(self) -> tuple[ElementPath, ...]:
        """Return the planned paths neither collected nor uncollected."""
        reported = {value.source for value in self.collected}
        reported |= {gap.path for gap in self.uncollected}
        return tuple(sorted(self.planned - reported, key=str))

    def gaps(self) -> tuple[tuple[ElementPath, ReasonCode], ...]:
        """Return each path whose collection is incomplete, once, and why.

        A path takes the first of these that applies: not collected, not
        reported, read only as bytes, or collected under another VR.
        """
        found = [(gap.path, _gap_code(gap.reason)) for gap in self.uncollected]
        found += [(path, ReasonCode.NOT_REPORTED) for path in self.not_reported()]
        found += [
            (path, ReasonCode.READ_AS_LATIN_1)
            for path in sorted(self.decoded_as_bytes, key=str)
        ]
        found += [
            (value.source, ReasonCode.COLLECTED_AS_OTHER_VR)
            for value in self.collected
            if _other_vr(value)
        ]
        first: dict[ElementPath, ReasonCode] = {}
        for path, code in found:
            first.setdefault(path, code)
        return tuple(first.items())

    @property
    def outcome(self) -> CollectionOutcome:
        """Whether every planned value was collected from its decoded form."""
        if self.gaps():
            return CollectionOutcome.INCOMPLETE
        return CollectionOutcome.COMPLETE

    def __repr__(self) -> str:
        return (
            f"Coverage(planned={len(self.planned)}, collected={len(self.collected)}, "
            f"uncollected={len(self.uncollected)}, "
            f"decoded_as_bytes={len(self.decoded_as_bytes)})"
        )


def _gap_code(reason: str) -> ReasonCode:
    if reason == NOT_REPORTED:
        return ReasonCode.NOT_REPORTED
    return ReasonCode.UNCOLLECTED


def _vrs(tag: str) -> tuple[str, ...]:
    """Return the VRs that the pinned dictionary gives a tag, if any."""
    attribute = dictionary_attribute(tag)
    return () if attribute is None else attribute.vrs


def _other_vr(value: SourceValue) -> bool:
    """Return whether a value was collected under a VR its attribute lacks."""
    vrs = _vrs(value.source.tag)
    return bool(vrs) and value.vr not in vrs


@dataclasses.dataclass(frozen=True)
class ReleaseReason:
    """One reason that a file is not released as it is.

    Attributes
    ----------
    decision : Decision
        What this reason alone requires.
    code : ReasonCode
    path : ElementPath, optional
        The source attribute; ``None`` for the file as a whole.
    location : Location, optional
        For a finding, where in the written file it was found.
    """

    decision: Decision
    code: ReasonCode
    path: ElementPath | None = None
    location: Location | None = None

    def __str__(self) -> str:
        """Describe the reason by its decision, path, code, and place."""
        where = "" if self.location is None else f" in {self.location}"
        subject = "the file" if self.path is None else str(self.path)
        return f"{self.decision.value}: {subject}: {self.code.value}{where}"


@dataclasses.dataclass(frozen=True, repr=False)
class ReleaseCondition:
    """Whether a written file may be released, and why.

    Its ``repr`` shows the decision, the outcome, and counts.

    Attributes
    ----------
    decision : Decision
        The most severe of the reasons' decisions, or release if none.
    outcome : CollectionOutcome
    reasons : tuple of ReleaseReason
        Those of the coverage's gaps, in their order, then the file's, then
        those of the findings, in the search's order.
    exclusions : tuple of NotSearched
        The forms that the search did not search, as it lists them.
    search : ResidualSearch
        The search of the written file for the collected values, for the
        confidential QC material.
    """

    decision: Decision
    outcome: CollectionOutcome
    reasons: tuple[ReleaseReason, ...]
    exclusions: tuple[NotSearched, ...]
    search: ResidualSearch

    def __repr__(self) -> str:
        return (
            f"ReleaseCondition(decision={self.decision.value!r}, outcome="
            f"{self.outcome.value!r}, reasons={len(self.reasons)}, "
            f"exclusions={len(self.exclusions)})"
        )

    def __str__(self) -> str:
        """List the decision and each reason, one to a line."""
        return "\n".join([self.decision.value, *map(str, self.reasons)])


def release_condition(
    coverage: Coverage, written: bytes | bytearray | memoryview
) -> ReleaseCondition:
    """Decide whether a written file may be released, as the module describes.

    Parameters
    ----------
    coverage : Coverage
        The values planned and collected for the search, pooled across the
        file's subject (:meth:`Coverage.merge`).
    written : bytes, bytearray, or memoryview
        The whole written file, which is searched for exactly the values
        that ``coverage`` collected.

    Returns
    -------
    ReleaseCondition

    Raises
    ------
    TypeError
        If ``coverage`` is not a :class:`Coverage` or ``written`` not bytes.
    ValueError
        If the transfer syntax deflates the data set, which the search
        cannot read.
    """
    if not isinstance(coverage, Coverage) or not isinstance(
        written, (bytes, bytearray, memoryview)
    ):
        raise TypeError("the release condition needs a Coverage and the written bytes")
    search = find_residuals(written, coverage.collected)
    identifiers = direct_identifiers()
    reasons = [
        ReleaseReason(_gap_decision(path, identifiers), code, path)
        for path, code in coverage.gaps()
    ]
    if not search.readable:
        reasons.append(ReleaseReason(Decision.WITHHOLD, ReasonCode.UNREADABLE_FILE))
    reasons += (_finding_reason(each, identifiers) for each in search.findings)
    decision = max(
        (reason.decision for reason in reasons),
        key=_SEVERITY.__getitem__,
        default=Decision.RELEASE,
    )
    return ReleaseCondition(
        decision, coverage.outcome, tuple(reasons), search.not_searched, search
    )


def _gap_decision(path: ElementPath, identifiers: frozenset[str]) -> Decision:
    """Withhold for a gap in a required kind or a sequence; review any other."""
    vrs = _vrs(path.tag)
    required = (
        any(vr in REQUIRED_KINDS for vr in vrs)
        or "SQ" in vrs  # its items, and what they hold, are unknown
        or path.tag in identifiers
    )
    return Decision.WITHHOLD if required else Decision.QC_REVIEW


def _finding_reason(finding: Finding, identifiers: frozenset[str]) -> ReleaseReason:
    """Give a finding its reason, by its kind, its source, then its place."""
    vrs = _vrs(finding.source.tag)
    kinds = [REQUIRED_KINDS[vr] for vr in vrs if vr in REQUIRED_KINDS]
    kind = (kinds or [ValueKind.TEXT])[0] if vrs else finding.kind
    code = _RESIDUAL_KINDS.get(kind)
    if code is None and finding.source.tag in identifiers:
        code = ReasonCode.RESIDUAL_DIRECT_IDENTIFIER
    if code is None and finding.location.region is not Region.DATA_SET:
        code = ReasonCode.RESIDUAL_OUTSIDE_DATA_SET
    if code is None:
        return ReleaseReason(
            Decision.QC_REVIEW,
            ReasonCode.RESIDUAL_TEXT,
            finding.source,
            finding.location,
        )
    return ReleaseReason(Decision.WITHHOLD, code, finding.source, finding.location)


def direct_identifiers(table: ProfileTable | None = None) -> frozenset[str]:
    """Return the tags of the direct identifiers, from the pinned tables.

    A direct identifier is an attribute that Table E.1-1 lists in PS3.6
    group 0008, 0010, 0020, 0032, 0038, or 0040, that the pinned dictionary
    makes neither a sequence (SQ) nor a UID (UI), that no option retains (K)
    or cleans (C), and whose keyword has ``ID``, ``IDs``, ``Number``,
    ``Numbers``, or ``Locator`` as a word, such as ``PatientID`` or
    ``PlacerOrderNumberImagingServiceRequest``. A keyword is split into
    words at each capital that starts a word, and a run of capitals is one
    word up to the capital that starts the next, so an acronym directly
    before ``ID``, as in a keyword such as ``MRNID``, would be one word and
    not selected; no keyword of the pinned edition that the other rules
    select is written so.

    Parameters
    ----------
    table : ProfileTable, optional
        Table E.1-1. Defaults to
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1`.

    Returns
    -------
    frozenset of str
        Tags such as ``"(0010,0020)"``.

    Examples
    --------
    >>> "(0010,0020)" in direct_identifiers()
    True
    >>> len(direct_identifiers())  # in the 2026d edition
    22
    """
    return _direct_identifiers(load_table_e1_1() if table is None else table)


@functools.cache
def _direct_identifiers(table: ProfileTable) -> frozenset[str]:
    selected = set()
    for row in table.attributes:
        if row.tag[1:5] not in IDENTIFIER_GROUPS:  # including the private row
            continue
        attribute = dictionary_attribute(row.tag)
        if (
            attribute is not None
            and {"SQ", "UI"}.isdisjoint(attribute.vrs)
            and _RETAINS_OR_CLEANS.isdisjoint(row.options.values())
            and not IDENTIFIER_WORDS.isdisjoint(_WORD.findall(attribute.keyword))
        ):
            selected.add(row.tag)
    return frozenset(selected)
