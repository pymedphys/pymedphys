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

"""Renumber each study's series by their order.

Series Number (0020,0011) can hold any number, such as a date written as
eight digits. Wherever Z or D applies to it, it takes its rank among the
Series Numbers of its study instead, so the order of the series survives
and nothing else does:

- the run's first pass records the Series Numbers that each instance holds
  where its IOD defines them
  (:attr:`~pymedphys._dicom.deidentify.references.InstanceRecord.series_numbering`),
  and :func:`number_studies` gives every instance of a study the numbering
  of all the study's values;
- each distinct number takes its rank among them in ascending order, from
  1, so equal numbers, such as those of the instances of one series, share
  a rank, and the ranks have no gaps;
- an instance outside a run, whose record is built alone, ranks only its
  own values.

A value counts only if it is one Integer String (PS3.5 Section 6.2): an
optional sign and at least one digit, at most 12 bytes with any leading or
trailing spaces, from -2^31 to 2^31 - 1. A value that is empty, is not such
a number, or is not in the numbering takes no rank:
:func:`~pymedphys._dicom.deidentify.edits.edit_instance` then empties it
under Z and gives it D's dummy value under D.

The numbering spans one run, as the values that a run's ephemeral key
generates do: a study de-identified in two runs can number its series
differently. A key whose values stay consistent across runs would need the
study's numbering kept with it, or every series of the study in each run,
for a series to keep its number.
"""

from __future__ import annotations

import bisect
import collections
import dataclasses
import re
from collections.abc import Iterable, Mapping

SERIES_NUMBER = "(0020,0011)"
# An Integer String's characters, without its padding (PS3.5 Section 6.2).
_INTEGER_STRING = re.compile(r"[+-]?[0-9]+")
_MAX_LENGTH = 12
_RANGE = range(-(2**31), 2**31)


def series_number(value: object) -> int | None:
    """Return the number that one Series Number value gives, if it is valid.

    Parameters
    ----------
    value : object
        The value as pydicom or the edits read it, such as ``"0007"`` or an
        ``IS``. Only text, or an ``int`` that pydicom read from text, can
        give a number.

    Returns
    -------
    int or None
        ``None`` if the value is not one Integer String.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    # pydicom's IS keeps the text that it was read from.
    text = str(getattr(value, "original_string", value))
    if len(text) > _MAX_LENGTH:
        return None
    stripped = text.strip(" ")
    if not _INTEGER_STRING.fullmatch(stripped):
        return None
    number = int(stripped)
    return number if number in _RANGE else None


@dataclasses.dataclass(frozen=True, repr=False)
class SeriesNumbering:
    """The rank of each Series Number of a study.

    Build one with :meth:`of`. Its ``repr`` shows only how many numbers it
    ranks, since a number could be a date.

    Attributes
    ----------
    numbers : tuple of int
        The distinct numbers, in ascending order; each one's rank is its
        index plus 1.
    """

    numbers: tuple[int, ...] = ()

    @classmethod
    def of(cls, numbers: Iterable[int]) -> SeriesNumbering:
        """Return the numbering of ``numbers``, in any order, with repeats."""
        return cls(tuple(sorted(set(numbers))))

    def __repr__(self) -> str:
        return f"SeriesNumbering({len(self.numbers)} numbers)"

    def rank(self, number: int | None) -> int | None:
        """Return the rank of ``number``, or ``None`` if it is not ranked."""
        if number is None:
            return None
        index = bisect.bisect_left(self.numbers, number)
        if index < len(self.numbers) and self.numbers[index] == number:
            return index + 1
        return None


def number_studies(
    numberings: Mapping[int, SeriesNumbering], studies: Mapping[int, str | None]
) -> dict[int, SeriesNumbering]:
    """Give every instance of a study the numbering of all the study's values.

    Parameters
    ----------
    numberings : mapping of int to SeriesNumbering
        Each instance's own numbering, by its run position.
    studies : mapping of int to str or None
        Each instance's Study Instance UID, by the same positions, or
        ``None`` if it has none.

    Returns
    -------
    dict of int to SeriesNumbering
        By the same positions. An instance without a Study Instance UID
        keeps its own numbering, since no study holds it.
    """
    by_study: dict[str, set[int]] = collections.defaultdict(set)
    for position, numbering in numberings.items():
        study = studies.get(position)
        if study is not None:
            by_study[study].update(numbering.numbers)
    shared = {study: SeriesNumbering.of(numbers) for study, numbers in by_study.items()}
    return {
        position: numbering
        if (study := studies.get(position)) is None
        else shared[study]
        for position, numbering in numberings.items()
    }
