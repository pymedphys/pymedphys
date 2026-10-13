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

"""The automatic tier of free-text Clean Descriptors: technique descriptors.

A value of a technique descriptor, such as Series Description ``AX T1 POST
GAD`` or Protocol Name ``CT CHEST W CONTRAST``, is kept without review where
every word of it is in the reviewed vocabulary of
``technique_vocabulary.toml`` and it echoes no identifier of the instance.
Every other value of a descriptor is decided on by a reviewer
(:mod:`.reviewed_descriptors`), whose decision takes precedence over this
tier. Study Description, comments, and diagnoses are never kept by it.

:meth:`TechniqueVocabulary.rejection` reads a value as words, the runs of
letters and digits between other characters, with any decimal places, and
keeps it only where no rule rejects it:

- it is printable ISO 646 (ASCII), without control characters, and holds no
  ``^``, which separates the components of a person's name;
- it holds no date or time, such as ``2026-10-12``, ``12_10_26``, or
  ``14:30``, no run of five or more digits, and no digits that run together
  across separators from one word to the next to five or more, such as a
  record number split into groups;
- it has at most one bare number, a word of only digits, which has at most
  three digits before its decimal point and at most three after, and is not
  two digits, a point, and two digits from ``10.00`` up, which could be a
  time;
- every other word is a reviewed reconstruction kernel, such as ``B70f`` or
  ``Br40``, or is made of letter runs that are each a vocabulary word, or
  two or three vocabulary words of at least three letters joined, as in
  ``FATSAT``, and digit runs that each have at most four digits before any
  decimal point and three after, and are not a year from 1900 to 2099, as in
  ``T2``, ``B1000``, ``120KV``, and ``0.625MM``; no word holds two digit
  runs with one letter between them, as ``14H30`` and ``512X512`` do;
- a single letter after digits, in a word or as the next word, is a unit,
  as in ``3T``, or the ``D`` of ``2D``, ``3D``, or ``4D``, since another,
  such as the ``F`` of ``45F``, could give an age or sex; and no two
  single-letter words are next to each other, as initials are;
- no letter run is a common personal name that is not a reviewed exception,
  and no title (``MR``, ``MRS``, or ``MS``) comes before a word that is an
  exception and also a common name, such as ``MRS HAND``; and
- it has at least one vocabulary word of at least two letters.

The rules hold a value rather than keep it wherever they are unsure, so a
false rejection costs review effort, not privacy. A value made only of
vocabulary words can still be a person's name, such as ``HAND``; that
residual risk is what the maintainer accepted with this tier, and the echo
check holds such a value where it names a person of the instance.

The vocabulary changes what the engine writes, so the method digest covers
it through :attr:`TechniqueVocabulary.sha256`, which is computed over
the effective attributes, words, units, kernels, and names after every term,
name, and exclusion is applied.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import hashlib
import json
import pathlib
import re
import tomllib
from collections.abc import Iterable, Mapping

from .common_names import load_common_names
from .residual_exemptions import BODY_PART_EXAMINED, defined_terms
from .reviewed_descriptors import descriptor_attributes

SCHEMA = "pymedphys-deid-technique-vocabulary/1"
VOCABULARY_FILE = pathlib.Path(__file__).with_name("technique_vocabulary.toml")

_TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")
_WORD = re.compile(r"[A-Z0-9]+")
_PRINTABLE = re.compile(r"[\x20-\x7e]*")
# A word of a value: a run of letters and digits, with any decimal places.
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:\.[0-9]+)*")
_RUN = re.compile(r"[A-Z]+|[0-9]+(?:\.[0-9]+)*")
_BARE_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)*")
# A reconstruction kernel: a reviewed prefix of one or two letters, two
# digits, and at most one of the reviewed suffixes.
_KERNEL = re.compile(r"([A-Z]{1,2})([0-9]{2})([A-Z]?)")
_KERNEL_SUFFIXES = frozenset({"", "D", "F", "H", "S", "U"})
_SEPARATOR = r"[^A-Za-z0-9]+"
_DATE = re.compile(
    rf"(?<![0-9])[0-9]{{1,4}}{_SEPARATOR}[0-9]{{1,2}}{_SEPARATOR}[0-9]{{1,4}}(?![0-9])"
)
_TIME = re.compile(r"(?<![0-9])[0-9]{1,2}:[0-9]{2}")
_CLOCK = re.compile(r"[1-9][0-9]\.[0-9]{2}")
_LONG_NUMBER = re.compile(r"[0-9]{5,}")
# Digits that run on across separators from one word into the next.
_SPLIT_NUMBER = re.compile(rf"[0-9]+(?:{_SEPARATOR}[0-9]+)+")
# A clock time written with an hour unit: hours, the unit, and minutes, as
# in 14H30, 14HR30MIN, 14HR 30MIN, or 9H 5MIN, or four or three digits of a 24-hour
# time and the unit, as in 1430HRS or 830H.
_HOUR_UNIT = r"(?:H|HRS?|HOURS?)"
_CLOCK_WITH_UNIT = re.compile(
    rf"(?<![0-9.])(?:[0-9]{{1,2}}(?:{_SEPARATOR})?{_HOUR_UNIT}(?:{_SEPARATOR})?[0-5]?[0-9](?![0-9])"
    rf"|(?:[01]?[0-9]|2[0-3])[0-5][0-9](?:{_SEPARATOR})?{_HOUR_UNIT}(?![A-Z]))",
    re.IGNORECASE,
)
_DIMENSIONS = frozenset({"1", "2", "3", "4"})
_TITLES = frozenset({"MR", "MRS", "MS"})
MAX_DIGITS = 4
MAX_BARE_DIGITS = 3
MAX_DECIMALS = 3
MIN_SPLIT_DIGITS = 5
MIN_COMPOUND_PART = 3
MIN_WORD = 2
MAX_COMPOUND_PARTS = 3
_YEARS = range(1900, 2100)


class TechniqueVocabularyError(ValueError):
    """The vocabulary file is not a valid reviewed technique vocabulary."""


class Rejection(enum.Enum):
    """Why the automatic tier does not keep a value."""

    NOT_AUTOMATIC = "not a technique descriptor"
    NOT_PRINTABLE = "not printable ASCII"
    DATE_OR_TIME = "date or time"
    NUMBER = "number"
    NAME = "personal name"
    INITIALS_AGE_OR_SEX = "initials, age, or sex"
    UNKNOWN_WORD = "word outside the vocabulary"
    NO_VOCABULARY_WORD = "no vocabulary word"


@dataclasses.dataclass(frozen=True)
class TechniqueVocabulary:
    """The effective technique vocabulary.

    Attributes
    ----------
    attributes : frozenset of str
        The tags of the attributes whose values the tier may keep.
    words : frozenset of str
        The vocabulary words, in capitals.
    units : frozenset of str
        The units, in capitals, which are also words.
    kernels : frozenset of str
        The reviewed prefixes of reconstruction kernels, in capitals.
    names : frozenset of str
        The common personal names that are not exceptions, which no letter
        run of a kept value may be.
    named_exceptions : frozenset of str
        The exceptions, which are common names kept in the vocabulary, and
        which no title may come before.
    """

    attributes: frozenset[str]
    words: frozenset[str] = dataclasses.field(repr=False)
    units: frozenset[str] = dataclasses.field(repr=False)
    kernels: frozenset[str] = dataclasses.field(repr=False)
    names: frozenset[str] = dataclasses.field(repr=False)
    named_exceptions: frozenset[str] = dataclasses.field(repr=False)

    def __repr__(self) -> str:
        return (
            f"TechniqueVocabulary(attributes={len(self.attributes)}, "
            f"words={len(self.words)})"
        )

    @functools.cached_property
    def sha256(self) -> str:
        """The SHA-256 of the canonical form of the effective vocabulary."""
        canonical = json.dumps(
            {
                "schema": SCHEMA,
                "attributes": sorted(self.attributes),
                "words": sorted(self.words),
                "units": sorted(self.units),
                "kernels": sorted(self.kernels),
                "names": sorted(self.names),
                "named_exceptions": sorted(self.named_exceptions),
            },
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    def rejection(self, tag: str, value: str) -> Rejection | None:
        """Return why the tier does not keep ``value``, or None if it keeps it.

        Parameters
        ----------
        tag : str
            The attribute's tag.
        value : str
            One value, without padding. The echo check is the caller's.
        """
        if tag not in self.attributes:
            return Rejection.NOT_AUTOMATIC
        return _text_rejection(value) or self._word_rejection(value)

    def keeps(self, tag: str, value: str) -> bool:
        """Return whether the tier keeps ``value``, before the echo check."""
        return self.rejection(tag, value) is None

    def _word_rejection(self, value: str) -> Rejection | None:
        found_word = False
        bare_numbers = 0
        previous = ""
        for token in _TOKEN.findall(value.upper()):
            if _BARE_NUMBER.fullmatch(token):
                bare_numbers += 1
                rejection = _bare_number_rejection(token, bare_numbers)
            elif self._is_kernel(token):
                rejection = None
            else:
                rejection = self._token_rejection(token, previous)
                found_word = found_word or any(
                    run.isalpha() and len(run) >= MIN_WORD
                    for run in _RUN.findall(token)
                )
            if rejection:
                return rejection
            previous = token
        return None if found_word else Rejection.NO_VOCABULARY_WORD

    def _token_rejection(self, token: str, previous: str) -> Rejection | None:
        runs = _RUN.findall(token)
        # Two numbers in one word, as in 512X512 or 14MIN30, could be a
        # clock time or part of an identifier.
        if sum(run[0].isdigit() for run in runs) > 1:
            return Rejection.NUMBER
        return self._context_rejection(token, runs[0], previous) or next(
            filter(None, (self._run_rejection(runs, i) for i in range(len(runs)))),
            None,
        )

    def _context_rejection(
        self, token: str, first: str, previous: str
    ) -> Rejection | None:
        # What the word before rejects: initials, an age, or a title.
        if len(token) == 1 and (
            (len(previous) == 1 and previous.isalpha())
            or (_BARE_NUMBER.fullmatch(previous) and token not in self.units)
        ):
            return Rejection.INITIALS_AGE_OR_SEX
        if previous in _TITLES and first in self.named_exceptions:
            return Rejection.NAME
        return None

    def _run_rejection(self, runs: list[str], index: int) -> Rejection | None:
        run = runs[index]
        if run[0].isdigit():
            return Rejection.NUMBER if _number_problem(run) else None
        if run in self.names:
            return Rejection.NAME
        if not self._is_vocabulary(run):
            return Rejection.UNKNOWN_WORD
        # A letter run after the first follows digits.
        if (
            index > 0
            and len(run) == 1
            and run not in self.units
            and not (run == "D" and runs[index - 1] in _DIMENSIONS)
        ):
            return Rejection.INITIALS_AGE_OR_SEX
        return None

    def _is_kernel(self, token: str) -> bool:
        match = _KERNEL.fullmatch(token)
        return bool(match and match[1] in self.kernels and match[3] in _KERNEL_SUFFIXES)

    def _is_vocabulary(self, run: str) -> bool:
        return run in self.words or self._is_compound(run, MAX_COMPOUND_PARTS)

    def _is_compound(self, run: str, parts: int) -> bool:
        # Whether ``run`` is two to ``parts`` vocabulary words joined, each
        # of at least three letters.
        if parts < 2:
            return False
        for cut in range(MIN_COMPOUND_PART, len(run) - MIN_COMPOUND_PART + 1):
            head, rest = run[:cut], run[cut:]
            if head in self.words and (
                rest in self.words or self._is_compound(rest, parts - 1)
            ):
                return True
        return False


def _text_rejection(value: str) -> Rejection | None:
    # What rejects the value as a whole, before it is read word by word.
    if not _PRINTABLE.fullmatch(value):
        return Rejection.NOT_PRINTABLE
    if "^" in value:
        return Rejection.NAME
    if _DATE.search(value) or _TIME.search(value) or _CLOCK_WITH_UNIT.search(value):
        return Rejection.DATE_OR_TIME
    if _LONG_NUMBER.search(value) or any(
        len(re.sub(r"[^0-9]", "", match[0])) >= MIN_SPLIT_DIGITS
        for match in _SPLIT_NUMBER.finditer(value)
    ):
        return Rejection.NUMBER
    return None


def _bare_number_rejection(token: str, count: int) -> Rejection | None:
    if count > 1:
        return Rejection.NUMBER
    if _CLOCK.fullmatch(token):
        return Rejection.DATE_OR_TIME
    whole = token.split(".", 1)[0]
    if len(whole) > MAX_BARE_DIGITS or _number_problem(token):
        return Rejection.NUMBER
    return None


def _number_problem(run: str) -> bool:
    # Whether a digit run, with any decimal places, could be part of an
    # identifier or a date: more than one point, too many digits, or a year.
    parts = run.split(".")
    if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) > MAX_DECIMALS):
        return True
    whole = parts[0]
    return len(whole) > MAX_DIGITS or (len(whole) == 4 and int(whole) in _YEARS)


def _words(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(word, str) and _WORD.fullmatch(word) for word in value
    ):
        raise TechniqueVocabularyError(
            f"{where} must be a list of words of capital letters and digits"
        )
    if len(set(value)) != len(value):
        raise TechniqueVocabularyError(f"{where} repeats a word")
    return value


def _tags(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(tag, str) and _TAG.fullmatch(tag) for tag in value
    ):
        raise TechniqueVocabularyError(f"{where} must be a list of tags")
    if len(set(value)) != len(value):
        raise TechniqueVocabularyError(f"{where} repeats a tag")
    return value


def _term_words(tags: Iterable[str], terms: Mapping[str, frozenset[str]]) -> set[str]:
    words: set[str] = set()
    for tag in (*tags, BODY_PART_EXAMINED):
        for term in terms.get(tag, ()):
            words.update(word for word in re.split(r"[_ ]+", term) if word)
    return words


def read_vocabulary(
    document: Mapping[str, object],
    *,
    names: frozenset[str],
    terms: Mapping[str, frozenset[str]],
) -> TechniqueVocabulary:
    """Return the effective vocabulary of a parsed vocabulary file.

    Parameters
    ----------
    document : mapping
        The parsed TOML document.
    names : frozenset of str
        The common personal names, in capitals.
    terms : mapping of str to frozenset of str
        The Enumerated Values and Defined Terms of each CS attribute, by tag,
        with the body part terms under Body Part Examined.

    Raises
    ------
    TechniqueVocabularyError
        If the document is not a valid :data:`SCHEMA` document, or a group or
        the units hold an excluded word or a common name that is not an
        exception, or an exception is not a common name of the vocabulary.
    """
    if document.get("schema") != SCHEMA:
        raise TechniqueVocabularyError(f"the file is not a {SCHEMA} file")
    attributes = _tags(document.get("attributes"), "attributes")
    not_descriptors = set(attributes) - set(descriptor_attributes())
    if not_descriptors:
        raise TechniqueVocabularyError(
            f"attributes holds {len(not_descriptors)} that are not descriptors"
        )
    term_attributes = _tags(document.get("term_attributes"), "term_attributes")
    if set(term_attributes) - set(terms):
        raise TechniqueVocabularyError("term_attributes holds a tag with no terms")
    excluded = set(_words(document.get("excluded"), "excluded"))
    units = set(_words(document.get("units"), "units"))
    kernels = set(_words(document.get("kernels"), "kernels"))
    if any(not kernel.isalpha() or len(kernel) > 2 for kernel in kernels):
        raise TechniqueVocabularyError("a kernel prefix is not one or two letters")
    exceptions = document.get("exceptions")
    if not isinstance(exceptions, dict) or not all(
        isinstance(basis, str) and basis for basis in exceptions.values()
    ):
        raise TechniqueVocabularyError("each exception needs its basis")
    _words(list(exceptions), "exceptions")
    groups = document.get("group")
    if not isinstance(groups, list) or not groups:
        raise TechniqueVocabularyError("the file holds no groups")
    grouped = set(units)
    for number, group in enumerate(groups, start=1):
        if not isinstance(group, dict) or not all(
            isinstance(group.get(key), str) and group.get(key)
            for key in ("name", "basis")
        ):
            raise TechniqueVocabularyError(f"group {number} needs a name and a basis")
        grouped.update(_words(group.get("words"), f"group {number}"))
    checked = grouped | kernels
    if checked & excluded:
        raise TechniqueVocabularyError(
            f"the groups, units, and kernels hold {len(checked & excluded)} "
            "excluded words"
        )
    unreviewed = (checked & names) - set(exceptions)
    if unreviewed:
        raise TechniqueVocabularyError(
            f"the groups, units, and kernels hold {len(unreviewed)} common names "
            "that are "
            "not exceptions"
        )
    vocabulary = grouped | _term_words(term_attributes, terms)
    if not set(exceptions) <= vocabulary & names:
        raise TechniqueVocabularyError(
            "an exception is not a common name of the vocabulary"
        )
    kept_names = names - set(exceptions)
    return TechniqueVocabulary(
        attributes=frozenset(attributes),
        words=frozenset(vocabulary - excluded - kept_names),
        units=frozenset(units),
        kernels=frozenset(kernels),
        names=frozenset(kept_names),
        named_exceptions=frozenset(exceptions),
    )


@functools.cache
def load_technique_vocabulary(
    path: pathlib.Path = VOCABULARY_FILE,
) -> TechniqueVocabulary:
    """Load the reviewed technique vocabulary shipped with PyMedPhys.

    Raises
    ------
    TechniqueVocabularyError
        If the file cannot be read, or as :func:`read_vocabulary` does.
    """
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise TechniqueVocabularyError("the vocabulary file cannot be read") from None
    return read_vocabulary(document, names=load_common_names(), terms=defined_terms())
