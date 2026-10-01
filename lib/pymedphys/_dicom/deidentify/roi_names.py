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
``LUNG-L``, and ``Lung L`` all become ``Lung_L``. Every other name goes to
the second tier, human review, which is not part of this module.

A name goes to review, rather than being renamed, where:

- it matches no vocabulary name, including where it holds a character
  outside printable ASCII, since TG-263 names are ASCII and Unicode case
  folding and compatibility forms would match look-alike characters;
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

Only a vocabulary converted from the AAPM TG-263 spreadsheet, whose entries
are published, generic names, is used: :class:`RoiNameVocabulary` accepts a
:class:`~pymedphys._nomenclature.tg263.Nomenclature` that carries AAPM's
attribution, which :func:`~pymedphys._nomenclature.tg263.load_json` requires.
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
_PRINTABLE_ASCII = re.compile(r"[\x20-\x7e]*")
_NOT_ALPHANUMERIC = re.compile(r"[\W_]+")


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
        Converted from the AAPM TG-263 spreadsheet, as its attribution
        states.

    Raises
    ------
    TypeError
        If ``nomenclature`` is not a TG-263 Nomenclature.
    ValueError
        If it does not carry AAPM's TG-263 attribution.
    """

    def __init__(self, nomenclature: tg263.Nomenclature):
        if not isinstance(nomenclature, tg263.Nomenclature):
            raise TypeError("the vocabulary must be a TG-263 Nomenclature")
        if nomenclature.attribution != tg263.ATTRIBUTION:
            raise ValueError(
                "the vocabulary does not carry the TG-263 attribution, so it was "
                "not converted from the AAPM TG-263 spreadsheet"
            )
        spellings: dict[str, set[str]] = collections.defaultdict(set)
        for structure in nomenclature.structures:
            for name in (structure.primary_name, structure.reverse_order_name):
                normalised = _normalised(name)
                if normalised:
                    spellings[normalised].add(name)
        self._spellings: Mapping[str, frozenset[str]] = {
            normalised: frozenset(names) for normalised, names in spellings.items()
        }

    @property
    def names(self) -> frozenset[str]:
        """Every vocabulary name that automatic cleaning can match."""
        return frozenset().union(*self._spellings.values())

    def spellings(self, normalised: str) -> frozenset[str]:
        """Return the vocabulary names with this normalised form."""
        return self._spellings.get(normalised, frozenset())

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
    spellings = [_spelling(name, vocabulary) for name in stripped]
    sources: dict[str, set[str]] = collections.defaultdict(set)
    for name, spelling in zip(stripped, spellings):
        if spelling is not None:
            sources[spelling].add(name)
    decisions = []
    for name, spelling in zip(stripped, spellings):
        decision = _decide(name, vocabulary, words, wholes)
        if decision.renamed and spelling is not None and len(sources[spelling]) > 1:
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


def _normalised(name: str) -> str:
    """Return the matching form of a name, or ``""`` if it cannot match."""
    if not _PRINTABLE_ASCII.fullmatch(name):
        return ""
    return _DISREGARDED.sub("", name).lower()


def _spelling(name: str, vocabulary: RoiNameVocabulary) -> str | None:
    """Return the one vocabulary name a stripped name matches, or None."""
    normalised = _normalised(name)
    spellings = vocabulary.spellings(normalised) if normalised else frozenset()
    if len(spellings) == 1:
        (spelling,) = spellings
        return spelling
    return None


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
    name: str, vocabulary: RoiNameVocabulary, words: set[str], wholes: set[str]
) -> RoiNameDecision:
    """Decide on one stripped name, before duplicates are considered."""
    if not name:
        return RoiNameDecision(Reason.EMPTY, "")
    normalised = _normalised(name)
    spellings = vocabulary.spellings(normalised) if normalised else frozenset()
    if not spellings:
        return RoiNameDecision(Reason.UNMATCHED, None)
    if len(spellings) > 1:
        return RoiNameDecision(Reason.AMBIGUOUS, None)
    (spelling,) = spellings
    if (_words(name) | _words(spelling)) & words or _whole(name) in wholes:
        return RoiNameDecision(Reason.ECHOES_IDENTIFIER, None)
    return RoiNameDecision(Reason.MATCHED, spelling)
