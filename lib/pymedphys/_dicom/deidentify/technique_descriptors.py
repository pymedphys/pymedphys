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

:meth:`TechniqueVocabulary.rejection` reads a value as follows, and keeps it
only where no rule rejects it:

- it is printable ISO 646 (ASCII), without control characters;
- it holds no date or time, such as ``2026-10-12``, ``12/10/26``, or
  ``14:30``, no run of five or more digits, and no numbers that run together
  across spaces, hyphens, or slashes to five or more digits, such as a
  record number split into groups;
- each of its words, the runs of letters and digits between other
  characters, is made of letter runs that are each a vocabulary word, or two
  or three vocabulary words of at least three letters joined, as in
  ``FATSAT``, and digit runs of at most four digits that are not a year from
  1900 to 2099, as in ``T2``, ``B1000``, ``120KV``, and ``0.625MM``, or is
  a reconstruction kernel of one or two letters, two digits, and at most one
  letter, as in ``B70f`` and ``Br40``, apart from a lone M, F, or Y;
- no letter run of it is a common personal name that is not a reviewed
  exception; and
- it has at least one vocabulary word of at least two letters.

The rules hold a value rather than keep it wherever they are unsure, so a
false rejection costs review effort, not privacy. A value made only of
vocabulary words can still be a person's name, such as ``HAND``; that
residual risk is what the maintainer accepted with this tier, and the echo
check holds such a value where it names a person of the instance.

The vocabulary changes what the engine writes, so the method digest is to
cover it through :attr:`TechniqueVocabulary.sha256`, which is computed over
the effective attributes and words after every term, name, and exclusion is
applied.
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
# A reconstruction kernel, such as B70f, Br40, Hr38, or FC13: one or two
# letters, two digits, and at most one letter. A lone M, F, or Y before the
# digits is left out, since it could give a patient's sex or age, as in M45.
_KERNEL = re.compile(r"(?![MFY][0-9])[A-Z]{1,2}[0-9]{2}[A-Z]?")
_DATE = re.compile(r"(?<![0-9])[0-9]{1,4}[-/.][0-9]{1,2}[-/.][0-9]{1,4}(?![0-9])")
_TIME = re.compile(r"(?<![0-9])[0-9]{1,2}:[0-9]{2}")
_LONG_NUMBER = re.compile(r"[0-9]{5,}")
# Numbers that run together across separators, such as a split record number.
_SPLIT_NUMBER = re.compile(r"[0-9]+(?:[ /-]+[0-9]+)+")
MAX_DIGITS = 4
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
    LONG_NUMBER = "long number"
    NAME = "common personal name"
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
    names : frozenset of str
        The common personal names that are not exceptions, which no letter
        run of a kept value may be.
    """

    attributes: frozenset[str]
    words: frozenset[str] = dataclasses.field(repr=False)
    units: frozenset[str] = dataclasses.field(repr=False)
    names: frozenset[str] = dataclasses.field(repr=False)

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
                "names": sorted(self.names),
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
        for token in _TOKEN.findall(value.upper()):
            if _KERNEL.fullmatch(token):
                continue
            for run in _RUN.findall(token):
                if run[0].isdigit():
                    if _number_problem(run):
                        return Rejection.LONG_NUMBER
                    continue
                if run in self.names:
                    return Rejection.NAME
                if not self._is_vocabulary(run):
                    return Rejection.UNKNOWN_WORD
                found_word = found_word or len(run) >= MIN_WORD
        return None if found_word else Rejection.NO_VOCABULARY_WORD

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
    if _DATE.search(value) or _TIME.search(value):
        return Rejection.DATE_OR_TIME
    if _LONG_NUMBER.search(value) or any(
        sum(c.isdigit() for c in match[0]) >= MIN_SPLIT_DIGITS
        for match in _SPLIT_NUMBER.finditer(value)
    ):
        return Rejection.LONG_NUMBER
    return None


def _number_problem(run: str) -> bool:
    whole = run.split(".", 1)[0]
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
    if grouped & excluded:
        raise TechniqueVocabularyError(
            f"the groups and units hold {len(grouped & excluded)} excluded words"
        )
    unreviewed = (grouped & names) - set(exceptions)
    if unreviewed:
        raise TechniqueVocabularyError(
            f"the groups and units hold {len(unreviewed)} common names that are "
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
        names=frozenset(kept_names),
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
