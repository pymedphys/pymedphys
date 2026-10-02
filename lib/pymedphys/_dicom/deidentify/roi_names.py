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

"""Clean ROI Names automatically against a TG-263 vocabulary.

Under the Clean Descriptors Option, ROI Name (3006,0026) is cleaned in two
tiers. This module is the automatic tier: a ROI Name that matches a name of
the vocabulary once case, spaces, and the separators ``_`` and ``-`` are
disregarded is written in the vocabulary's own spelling, so ``lung l``,
``LUNG-L``, and ``Lung L`` all become ``Lung_L``. TG-263 writes ``-`` for a
subtraction, as in ``Lungs-PTV``, so a vocabulary name that contains ``-``
matches only a name with ``-`` in the same place: ``lungs - ptv`` becomes
``Lungs-PTV``, but ``Lungs PTV`` and ``Lungs_PTV`` do not. Every other name
goes to the second tier, human review, which is not part of this module.

A name goes to review, rather than being renamed, where:

- it matches no vocabulary name, including where it holds a character
  outside printable ASCII, since TG-263 names are ASCII and Unicode case
  folding and compatibility forms would match look-alike characters, and
  where, once its padding is removed, it starts with ``_`` or ``-``, since
  TG-263 marks a structure not used for dose evaluation, such as an
  optimisation contour, with a leading ``_``, so ``_Heart`` is not ``Heart``;
- its normalised form matches more than one vocabulary name, such as
  ``Bowel_Small`` and a ``Bowel-Small`` beside it, so renaming would need a
  choice;
- it echoes a known patient or other person identifier: a word of the name,
  or of the vocabulary name it would take, is a word of the identifier, or
  the whole name equals the whole identifier once case and characters that
  are not letters or digits are disregarded. Words of one character, such as
  initials or the ``L`` of ``Lung_L``, are not compared;
- another, differently spelt ROI Name of the same structure set would be
  written as the same vocabulary name, as ``Lung_L`` and ``LUNG-L`` would,
  since duplicate ROI Names can make a planning system reject the import.

A name that is empty once its padding is removed stays empty. Decisions hold
the vocabulary's spelling and a reason, never the source name, so they can be
logged; recording each rename for audit in the confidential QC material is
the caller's responsibility.

Automatic renaming is only for the list that AAPM publishes, whose entries
are generic names. The converter writes AAPM's attribution for any workbook
with the TG-263 columns, including one extended with local names, such as
``ClinicX_Lung``, so :class:`RoiNameVocabulary` accepts only a
:class:`~pymedphys._nomenclature.tg263.Nomenclature` whose entries have the
content digest of a published edition, as :data:`PUBLISHED_TG263` records.
Any other list, however converted, is refused, so the caller sends its names
to review.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import re
from collections.abc import Iterable, Mapping, Sequence

from pymedphys._nomenclature import tg263

# LO values may be padded with spaces (PS3.5 Section 6.2); some writers pad
# with NUL instead.
_PADDING = " \x00"
_DISREGARDED = re.compile(r"[ _-]")
# TG-263 gives a leading "_" to a structure not used for dose evaluation,
# such as an optimisation contour, so a name that starts with a separator is
# not the vocabulary name without it.
_PREFIXES = ("_", "-")
_DISREGARDED_BESIDE_HYPHENS = re.compile(r"[ _]")
_PRINTABLE_ASCII = re.compile(r"[\x20-\x7e]*")
_NOT_ALPHANUMERIC = re.compile(r"[\W_]+")


# The content digest (tg263.content_sha256) of the entries of the published
# edition of the TG-263 Structure Spreadsheet, by worksheet name: the edition
# that pymedphys._nomenclature.tg263_published.PUBLISHED pins, and which
# PyMedPhys downloads, as a test checks. The digest is written here rather
# than imported, so that the method digest, which covers this package's
# source, changes when the editions that rename automatically change.
PUBLISHED_TG263: dict[str, str] = {
    "TG263 v20170815": (
        "0a0eaeacf147bdf654e0090b3e12b005d76985e6adc95441d7563365ac6e7ffc"
    ),
}


class Reason(enum.Enum):
    """Why a ROI Name was renamed, left empty, or sent to review."""

    MATCHED = "matched"
    EMPTY = "empty"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    ECHOES_IDENTIFIER = "echoes identifier"
    WOULD_DUPLICATE = "would duplicate"


@dataclasses.dataclass(frozen=True)
class RoiNameDecision:
    """The automatic tier's decision on one ROI Name.

    Attributes
    ----------
    reason : Reason
    value : str or None
        The vocabulary's spelling where the reason is ``MATCHED``, ``""``
        where it is ``EMPTY``, and None where the name goes to review.
    """

    reason: Reason
    value: str | None

    @property
    def renamed(self) -> bool:
        """Whether the name is written in the vocabulary's spelling."""
        return self.reason is Reason.MATCHED


class RoiNameVocabulary:
    """The names of a TG-263 vocabulary, indexed by their normalised forms.

    Both the primary and the reverse-order name of each structure are
    vocabulary names, and each is written in its own spelling. An entry with
    a character outside printable ASCII is never matched, so never written.

    Parameters
    ----------
    nomenclature : ~pymedphys._nomenclature.tg263.Nomenclature
        A published edition of the TG-263 Structure Spreadsheet.

    Raises
    ------
    TypeError
        If ``nomenclature`` is not a TG-263 Nomenclature.
    ValueError
        If it does not carry AAPM's TG-263 attribution, or its entries are
        not those of an edition in :data:`PUBLISHED_TG263`.
    """

    def __init__(self, nomenclature: tg263.Nomenclature):
        if not isinstance(nomenclature, tg263.Nomenclature):
            raise TypeError("the vocabulary must be a TG-263 Nomenclature")
        if nomenclature.attribution != tg263.ATTRIBUTION:
            raise ValueError(
                "the vocabulary does not carry the TG-263 attribution, so it was "
                "not converted from the AAPM TG-263 spreadsheet"
            )
        entries = [dataclasses.asdict(s) for s in nomenclature.structures]
        if tg263.content_sha256(entries) not in PUBLISHED_TG263.values():
            raise ValueError(
                "the vocabulary's entries are not those of a published edition of "
                "the TG-263 spreadsheet, so its names cannot be written without "
                "review"
            )
        spellings: dict[str, set[str]] = collections.defaultdict(set)
        for structure in nomenclature.structures:
            for name in (structure.primary_name, structure.reverse_order_name):
                key = _normalised(name, keep_hyphens="-" in name)
                if key:
                    spellings[key].add(name)
        self._spellings: Mapping[str, frozenset[str]] = {
            normalised: frozenset(names) for normalised, names in spellings.items()
        }
        self._names = frozenset().union(*self._spellings.values())

    @property
    def names(self) -> frozenset[str]:
        """Every vocabulary name that automatic cleaning can match."""
        return self._names

    def spellings(self, name: str) -> frozenset[str]:
        """Return the vocabulary names that a ROI Name, without padding, matches."""
        keys = {_normalised(name), _normalised(name, keep_hyphens=True)} - {""}
        return frozenset().union(
            *(self._spellings.get(key, frozenset()) for key in keys)
        )

    def __repr__(self) -> str:
        return f"RoiNameVocabulary(names={len(self.names)})"


def clean_roi_names(
    names: Sequence[str],
    vocabulary: RoiNameVocabulary,
    *,
    identifiers: Iterable[str],
) -> tuple[RoiNameDecision, ...]:
    """Decide which ROI Names of one structure set are renamed automatically.

    Parameters
    ----------
    names : sequence of str
        The decoded ROI Names of one structure set, in order, with or without
        their padding.
    vocabulary : RoiNameVocabulary
    identifiers : iterable of str
        The decoded values of the instance's patient and other person
        identifiers, such as Patient's Name and Patient ID, against which
        echoes are checked. Person names may be given whole, with their
        ``^`` and ``=`` delimiters.

    Returns
    -------
    tuple of RoiNameDecision
        One for each name, in the same order.

    Raises
    ------
    TypeError
        If ``names`` or ``identifiers`` is a single string, or holds anything
        but strings. The message holds no value.
    """
    names = _texts(names, "ROI Names")
    words, wholes = _identifier_words(_texts(identifiers, "identifiers"))
    stripped = [name.strip(_PADDING) for name in names]
    matches = [
        frozenset() if name.startswith(_PREFIXES) else vocabulary.spellings(name)
        for name in stripped
    ]
    sources: dict[str, set[str]] = collections.defaultdict(set)
    for name, spellings in zip(stripped, matches):
        if len(spellings) == 1:
            sources[next(iter(spellings))].add(name)
    decisions = []
    for name, spellings in zip(stripped, matches):
        decision = _decide(name, spellings, words, wholes)
        if decision.renamed and len(sources[decision.value or ""]) > 1:
            decision = RoiNameDecision(Reason.WOULD_DUPLICATE, None)
        decisions.append(decision)
    return tuple(decisions)


def _texts(values: Iterable[str], what: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{what} must be a sequence of strings, not one value")
    values = tuple(values)
    if not all(isinstance(value, str) for value in values):
        raise TypeError(f"{what} must all be strings")
    return values


def _normalised(name: str, *, keep_hyphens: bool = False) -> str:
    """Return the matching form of a name, or ``""`` if it cannot match.

    A vocabulary name with ``-`` is indexed with its hyphens kept, and a ROI
    Name is looked up in both forms, so a hyphen in a vocabulary name is
    matched only by a hyphen in the same place.
    """
    if not _PRINTABLE_ASCII.fullmatch(name):
        return ""
    pattern = _DISREGARDED_BESIDE_HYPHENS if keep_hyphens else _DISREGARDED
    return pattern.sub("", name).lower()


def _words(text: str) -> set[str]:
    """Return the casefolded words of text with more than one character."""
    return {word for word in _NOT_ALPHANUMERIC.split(text.casefold()) if len(word) > 1}


def _whole(text: str) -> str:
    return _NOT_ALPHANUMERIC.sub("", text.casefold())


def _identifier_words(identifiers: Sequence[str]) -> tuple[set[str], set[str]]:
    words: set[str] = set()
    wholes: set[str] = set()
    for identifier in identifiers:
        words |= _words(identifier)
        whole = _whole(identifier)
        if whole:
            wholes.add(whole)
    return words, wholes


def _decide(
    name: str, spellings: frozenset[str], words: set[str], wholes: set[str]
) -> RoiNameDecision:
    """Decide on one stripped name, before duplicates are considered."""
    if not name:
        return RoiNameDecision(Reason.EMPTY, "")
    if not spellings:
        return RoiNameDecision(Reason.UNMATCHED, None)
    if len(spellings) > 1:
        return RoiNameDecision(Reason.AMBIGUOUS, None)
    (spelling,) = spellings
    if (_words(name) | _words(spelling)) & words or _whole(name) in wholes:
        return RoiNameDecision(Reason.ECHOES_IDENTIFIER, None)
    return RoiNameDecision(Reason.MATCHED, spelling)
