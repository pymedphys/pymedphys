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

"""Synthetic birth dates for the ``tps-import`` preset (D-008).

Patient's Birth Date (0010,0030) is Z in the Basic Profile, and no option
retains or cleans it, so a synthetic value is a permitted dummy value.
Planning systems may reject a record without one, so under ``tps-import``
the attribute takes the subject's synthetic birth date at the top level of
the data set wherever Z or D applies to it (:func:`with_birth_date`).

A subject's birth date is chosen once, from the instances of the run that
first exports it, and kept in its profile
(:class:`~pymedphys._dicom.deidentify.profiles.ProfileStore`), from which
every later run under the same key reads it back:

- Each study of the subject in the run, by Study Instance UID, gives an
  **observation** where its instances hold, at the top level, exactly one
  distinct Study Date (0008,0020) that is a valid date, and exactly one
  distinct Patient's Age (0010,1010) in years (``nnnY``), padding aside. An
  instance without either value adds nothing; an age in months, weeks, or
  days is not in completed years, so its study gives no observation.
- The subject's dates and ages are **consistent** where no study's
  instances hold two different values of either attribute, and some birth date gives every
  observation its age, in completed years, on its date.
- The **reference study** is the observation with the earliest Study Date,
  and of those on that date, the one with the least replacement Study
  Instance UID, so the choice does not depend on the order of the run.
- The synthetic birth date is the reference study's shifted date
  (:func:`~pymedphys._dicom.deidentify.dates.shift_date`) minus the age in
  calendar years (:func:`synthetic_birth_date`). It gives the subject that
  age, in completed years, on the shifted date, and so expresses the
  approximate age at the reference study, not the true birthday.
- Where the ages are not consistent, or no study gives an observation whose
  date can be shifted and synthesised, the subject's choice is no birth
  date: the attribute is emptied, as Z empties it, in this run and every
  later one.

The profile records the choice, with the reference study by its replacement
Study Instance UID, its shifted date, and the age. A later run never changes
it, whatever studies it holds, but where its instances contradict the
recorded reference, it sequesters every instance of the subject for review
(:attr:`~pymedphys._dicom.deidentify.reasons.TransformReason.BIRTH_DATE_CONFLICT`):
where the subject's ages in the run are not consistent with each other and
with the reference study's age on its source date, or the run holds the
reference study with another Study Date or Patient's Age than the profile
records. A recorded choice of no birth date is kept without such checks.

An instance without a subject's identity has no birth date, so its edit
stays pending, as its pseudonyms do, and it is sequestered. Nothing here
logs, reports, or raises with a value.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from collections.abc import Callable, Iterable, Mapping

from .dates import shift_date
from .edits import Edit, EditKind, InstanceEdits
from .file_layout import ElementPath
from .keys import DeidKey
from .profiles import NO_BIRTH_DATE, BirthDate, ProfileStore, ReferenceStudy
from .pseudonyms import SubjectIdentity
from .references import InstanceRecord
from .source import SourceEvidence, SourceRefused, read_source
from .uids import replacement_uid

# The preset whose Z writes synthetic birth dates.
BIRTH_DATE_PRESET = "tps-import"
PATIENTS_BIRTH_DATE = ElementPath((), "(0010,0030)")
STUDY_DATE = ElementPath((), "(0008,0020)")
PATIENTS_AGE = ElementPath((), "(0010,1010)")
_DA = re.compile("[0-9]{8}")
_AGE_IN_YEARS = re.compile("([0-9]{3})Y")
# Trailing padding that a DA or AS value may carry.
_PADDING = " \x00"


def _years_before(day: datetime.date, years: int) -> datetime.date:
    """Return the same day ``years`` calendar years earlier.

    29 February becomes 28 February in a year without one.

    Raises
    ------
    ValueError
        If the date would be before year 1.
    """
    year = day.year - years
    if year < datetime.MINYEAR:
        raise ValueError("the date would be before year 1")
    try:
        return day.replace(year=year)
    except ValueError:  # 29 February in a common year
        return day.replace(year=year, day=28)


def _text(day: datetime.date) -> str:
    # strftime("%Y") does not zero-pad years before 1000 on every platform.
    return f"{day.year:04d}{day.month:02d}{day.day:02d}"


def _date(value: str) -> datetime.date:
    """Return the date of a DA value without padding; ValueError if none."""
    if not _DA.fullmatch(value):
        raise ValueError("the value is not a DA value")
    return datetime.datetime.strptime(value, "%Y%m%d").date()


def synthetic_birth_date(shifted_date: str, age_years: int) -> str:
    """Return the birth date that gives ``age_years`` on ``shifted_date``.

    The date is ``shifted_date`` moved back by ``age_years`` calendar years,
    with 29 February mapped to 28 February in a year without one, so that
    the subject is ``age_years`` old, in completed years, on that date.

    Parameters
    ----------
    shifted_date : str
        The reference study's shifted Study Date, ``YYYYMMDD``.
    age_years : int
        Patient's Age at the reference study, in completed years.

    Raises
    ------
    ValueError
        If ``shifted_date`` is not a valid DA value, ``age_years`` is
        negative, or the birth date would be before year 1.

    Examples
    --------
    >>> synthetic_birth_date("20240229", 45)
    '19790228'
    >>> synthetic_birth_date("20240229", 44)
    '19800229'
    """
    if age_years < 0:
        raise ValueError("an age cannot be negative")
    return _text(_years_before(_date(shifted_date), age_years))


@dataclasses.dataclass(frozen=True)
class _Observation:
    """A study's date and age, as a consistent study of the run gives them."""

    study: str  # the replacement Study Instance UID
    day: datetime.date  # the source Study Date
    age_years: int


def _interval(
    day: datetime.date, age_years: int
) -> tuple[datetime.date, datetime.date]:
    """Return the first and last birth dates that give the age on ``day``.

    Each is a birth date on which someone is ``age_years`` old, in completed
    years, on ``day``, counting a 29 February birthday as passed on 1 March
    of a common year. The first is ``datetime.date.min`` where it would be
    before year 1.
    """
    last = _years_before(day, age_years)
    try:
        first = _years_before(day, age_years + 1) + datetime.timedelta(days=1)
    except ValueError:
        first = datetime.date.min
    return first, last


def ages_agree(observations: Iterable[tuple[datetime.date, int]]) -> bool:
    """Return whether one birth date gives every observation its age.

    Each observation is a date and an age in completed years on it, and
    gives the interval of birth dates that give it that age; they agree
    where the intervals meet.

    Raises
    ------
    ValueError
        If an observation's birth dates would be before year 1.
    """
    intervals = [_interval(day, age) for day, age in observations]
    return max(first for first, _ in intervals) <= min(last for _, last in intervals)


def _values(data: bytes | None) -> tuple[str | None, str | None]:
    """Return a file's top-level Study Date and Patient's Age, unpadded.

    Either is ``None`` where the file has no such value, or none that can be
    read: one that is empty, of undefined length, or in a file that is not
    a source file, which the transform sequesters.
    """
    if data is None:
        return None, None
    try:
        source = read_source(data)
    except SourceRefused:
        return None, None
    return _value(source, STUDY_DATE), _value(source, PATIENTS_AGE)


def _value(source: SourceEvidence, path: ElementPath) -> str | None:
    if path not in source:
        return None
    try:
        field = source.value_field(path)
    except ValueError:
        return None
    # DA and AS are of the default repertoire, so any other byte makes the
    # value invalid rather than another character.
    return field.decode("latin-1").rstrip(_PADDING) or None


@dataclasses.dataclass
class _Study:
    """The distinct values that a run's instances of one study hold."""

    dates: set[str] = dataclasses.field(default_factory=set)
    ages: set[str] = dataclasses.field(default_factory=set)

    @property
    def consistent(self) -> bool:
        return len(self.dates) <= 1 and len(self.ages) <= 1

    def observed(self) -> tuple[datetime.date, int] | None:
        """Return the study's date and age in years, if it gives an observation."""
        if len(self.dates) != 1 or len(self.ages) != 1:
            return None
        (date,), (age,) = self.dates, self.ages
        match = _AGE_IN_YEARS.fullmatch(age)
        if match is None:
            return None
        try:
            return _date(date), int(match.group(1))
        except ValueError:
            return None


class BirthDates:
    """The synthetic birth date of each subject of a ``tps-import`` run.

    Parameters
    ----------
    key : DeidKey
        The run's key, for the replacement Study Instance UIDs that name
        each reference study.
    profiles : ProfileStore
        The subject profiles of ``key``, from which each subject's date
        offset and recorded birth date are read, and in which a new
        subject's choice is recorded.
    """

    def __init__(self, key: DeidKey, profiles: ProfileStore) -> None:
        self._key = key
        self._profiles = profiles
        # Each prepared subject's birth date, or None for one whose
        # instances contradict its recorded reference.
        self._chosen: dict[SubjectIdentity, BirthDate | None] = {}

    def __repr__(self) -> str:
        return f"BirthDates(subjects={len(self._chosen)})"

    def prepare(
        self,
        records: Mapping[int, InstanceRecord],
        read: Callable[[int], bytes | None],
    ) -> None:
        """Choose, or read back, the birth date of each subject of a run.

        Parameters
        ----------
        records : mapping of int to InstanceRecord
            The records of the instances that the run will transform, by run
            position. One without a subject's identity or Study Instance UID
            gives nothing.
        read : callable
            Gives the file at a run position as the run's first pass read
            it, or None if it has changed.
        """
        subjects: dict[SubjectIdentity, dict[str, _Study]] = {}
        for position, record in records.items():
            if record.patient is None or record.study is None:
                continue
            study = subjects.setdefault(record.patient, {}).setdefault(
                record.study, _Study()
            )
            date, age = _values(read(position))
            if date is not None:
                study.dates.add(date)
            if age is not None:
                study.ages.add(age)
        for identity, studies in subjects.items():
            self._chosen[identity] = self._choose(identity, studies)

    def conflicted(self, identity: SubjectIdentity | None) -> bool:
        """Return whether the subject's instances contradict its recorded reference."""
        return identity in self._chosen and self._chosen[identity] is None

    def value(self, identity: SubjectIdentity | None) -> str | None:
        """Return what Patient's Birth Date takes for the subject.

        A date as ``YYYYMMDD``, or ``""`` for a subject whose choice is no
        birth date; ``None`` without a prepared subject whose instances
        agree with its profile, such as an instance without a subject's
        identity.
        """
        chosen = self._chosen.get(identity) if identity is not None else None
        return None if chosen is None else chosen.value

    def _observations(self, studies: Mapping[str, _Study]) -> list[_Observation]:
        found = []
        for uid, study in studies.items():
            observed = study.observed()
            if observed is not None:
                found.append(_Observation(replacement_uid(self._key, uid), *observed))
        return found

    def _choose(
        self, identity: SubjectIdentity, studies: Mapping[str, _Study]
    ) -> BirthDate | None:
        profile = self._profiles.profile(identity)
        consistent = all(study.consistent for study in studies.values())
        observations = self._observations(studies)
        if profile.birth_date is None:
            chosen = self._first(consistent, observations, profile.date_offset_weeks)
            self._profiles.record_birth_date(identity, chosen)
            return chosen
        reference = profile.birth_date.reference
        if reference is None:
            return profile.birth_date
        agrees = consistent and self._agrees(
            reference, studies, observations, profile.date_offset_weeks
        )
        return profile.birth_date if agrees else None

    @staticmethod
    def _first(
        consistent: bool, observations: list[_Observation], weeks: int
    ) -> BirthDate:
        """Return a new subject's birth date, from the run's observations."""
        synthesised = []
        for each in observations:
            try:
                shifted = shift_date(_text(each.day), weeks)
                value = synthetic_birth_date(shifted, each.age_years)
            except ValueError:
                # A date that cannot be shifted or synthesised, such as one
                # that would be before year 1, is not a valid reference.
                continue
            synthesised.append(
                (each, ReferenceStudy(each.study, shifted, each.age_years), value)
            )
        if not (
            consistent
            and synthesised
            and ages_agree((each.day, each.age_years) for each, _, _ in synthesised)
        ):
            return NO_BIRTH_DATE
        _, reference, value = min(
            synthesised, key=lambda found: (found[0].day, found[0].study)
        )
        return BirthDate(value, reference)

    def _agrees(
        self,
        reference: ReferenceStudy,
        studies: Mapping[str, _Study],
        observations: list[_Observation],
        weeks: int,
    ) -> bool:
        """Return whether a run's studies agree with a recorded reference."""
        try:
            source_day = _date(reference.date) + datetime.timedelta(weeks=weeks)
        except (ValueError, OverflowError):
            return False
        for uid, study in studies.items():
            if replacement_uid(self._key, uid) != reference.study:
                continue
            if study.dates - {_text(source_day)} or study.ages - {
                f"{reference.age_years:03d}Y"
            }:
                return False
        try:
            return ages_agree(
                [
                    (source_day, reference.age_years),
                    *((each.day, each.age_years) for each in observations),
                ]
            )
        except ValueError:
            return False


def with_birth_date(edits: InstanceEdits, value: str | None) -> InstanceEdits:
    """Return the edits with Patient's Birth Date taking the subject's birth date.

    Only at the top level of the data set, wherever Z or D applies to it. A
    date replaces the value; ``""``, the choice of no birth date, leaves the
    edit as Z or D gives it; and ``None``, for an instance without a
    prepared subject, leaves it pending, so that the instance is
    sequestered.
    """
    found = []
    for edit in edits.edits:
        if (
            edit.path == PATIENTS_BIRTH_DATE
            and edit.removed_with is None
            and edit.action in ("Z", "D")
        ):
            if value is None:
                edit = Edit(edit.path, edit.action, EditKind.PENDING)
            elif value:
                edit = Edit(edit.path, edit.action, EditKind.REPLACE, (value,))
        found.append(edit)
    return dataclasses.replace(edits, edits=tuple(found))
