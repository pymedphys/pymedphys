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
Series Numbers of the study that holds the series it numbers instead, so
the order of the series survives and nothing else does:

- the run's first pass records each Series Number that an instance holds
  where its IOD defines one, with the Series Instance UID of the series it
  numbers: the instance's own at the top level, and the item's own in an
  item, such as one of an RT Structure Set's Source Series Information
  Sequence (3006,004C)
  (:attr:`~pymedphys._dicom.deidentify.references.InstanceRecord.series_numbers`);
- :func:`number_series` finds the study of each such series among the
  run's instances, and gives each Series Number the numbering of all the
  values that number a series of that study;
- each distinct number takes its rank among them in ascending order, from
  1, so equal numbers, such as those of the instances of one series, share
  a rank, and the ranks have no gaps.

A value counts only if it is one Integer String (PS3.5 Section 6.2): an
optional sign and at least one digit, at most 12 bytes with any leading or
trailing spaces, from -2^31 to 2^31 - 1. A value takes no rank if it is
empty or is not such a number, or if the series it numbers is in no study
of the run, or in several: an item can name a series that the run does not
hold, and its rank in another study's numbering would number that series
differently from its own instances.
:func:`~pymedphys._dicom.deidentify.edits.edit_instance` then empties such
a value under Z and gives it D's dummy value under D. An instance outside
a run, whose record is built alone, ranks only the values that number its
own series.

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
from collections.abc import Iterable, Mapping, Sequence

from .file_layout import ElementPath

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


@dataclasses.dataclass(frozen=True, repr=False)
class SeriesNumberUse:
    """A Series Number that an instance holds, and the series it numbers.

    Its ``repr`` shows only its path, since its number could be a date.

    Attributes
    ----------
    path : ElementPath
        Where the instance holds it.
    number : int or None
        Its number, or ``None`` if its value is not one Integer String.
    series : str or None
        The Series Instance UID of the series it numbers, without padding,
        or ``None`` if there is not one.
    """

    path: ElementPath
    number: int | None
    series: str | None

    def __repr__(self) -> str:
        return f"SeriesNumberUse({self.path})"


@dataclasses.dataclass(frozen=True, repr=False)
class SeriesNumberings:
    """The numbering in which each Series Number of an instance takes its rank.

    Build one with :meth:`of`. Its ``repr`` shows only how many places it
    numbers.

    Attributes
    ----------
    by_path : tuple of (ElementPath, SeriesNumbering)
        Each place's numbering. A place without one takes no rank.
    """

    by_path: tuple[tuple[ElementPath, SeriesNumbering], ...] = ()

    @classmethod
    def of(cls, numberings: Mapping[ElementPath, SeriesNumbering]) -> SeriesNumberings:
        """Return the numberings of the places in ``numberings``, in any order."""
        return cls(tuple(sorted(numberings.items(), key=lambda pair: str(pair[0]))))

    def __repr__(self) -> str:
        return f"SeriesNumberings({len(self.by_path)} places)"

    def numbering(self, path: ElementPath) -> SeriesNumbering | None:
        """Return the numbering of the Series Number at ``path``, if any."""
        return dict(self.by_path).get(path)


def number_series(
    uses: Mapping[int, Sequence[SeriesNumberUse]], studies: Mapping[str, str]
) -> dict[int, SeriesNumberings]:
    """Give each Series Number the numbering of the study of its series.

    Parameters
    ----------
    uses : mapping of int to sequence of SeriesNumberUse
        Each instance's Series Numbers, by its run position.
    studies : mapping of str to str
        The Study Instance UID of each series that one study of the run
        holds, by its Series Instance UID.

    Returns
    -------
    dict of int to SeriesNumberings
        By the same positions. A Series Number whose series is not in
        ``studies`` has no numbering.
    """
    by_study: dict[str, set[int]] = collections.defaultdict(set)
    for each in uses.values():
        for use in each:
            study = studies.get(use.series or "")
            if study is not None and use.number is not None:
                by_study[study].add(use.number)
    shared = {study: SeriesNumbering.of(numbers) for study, numbers in by_study.items()}
    return {
        position: SeriesNumberings.of(
            {
                use.path: shared[study]
                for use in each
                if (study := studies.get(use.series or "")) in shared
            }
        )
        for position, each in uses.items()
    }
