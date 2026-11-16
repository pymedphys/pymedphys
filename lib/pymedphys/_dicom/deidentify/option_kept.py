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

"""Name the residual findings that a value a selected option keeps explains.

A Retain option keeps values that the Basic Profile removes, such as Station
Name (0008,1010) under Retain Device Identity or Study Date (0008,0020)
under Retain Longitudinal Temporal Information with Full Dates. The residual
search still finds removed values inside them: a station's AE title
in its kept Station Name, a vendor's private copy of an institution's name
in its kept Institution Name, or a removed Patient's Birth Date equal to a
kept Study Date. Such a finding shows only that removed text is inside a
value that the run's policy releases anyway, so it reveals nothing that the
kept value does not, wherever the option explains it:

- :func:`retained_text`: a text finding in a text attribute that a selected
  option keeps, whose source is a private data element or an attribute that
  the same option keeps or cleans;
- :func:`retained_value`: a finding, of text, a date, or a datetime, that
  equals a whole value of a date, time, or datetime attribute that a
  selected option keeps, from any other source, where each other pooled
  value of the source that the search could find there does too; in a
  kept date, a datetime counts as equal where its date does, since the
  search also looks for a datetime by its date, and the text it then finds
  is the whole kept date, which holds no time; and in a kept datetime, a
  date, or a datetime's date, counts as equal where it is the first eight
  characters of a whole kept value, which are that value's date, since the
  text found there is then the kept date, and the source's time is not in
  it.

An attribute is kept under a set of options where one of them gives it K
and the Basic Profile does not, and no other gives it an action of its own
other than K (:func:`kept_by`), so that the eleven device dates that
``tps-import`` modifies are not kept. The rules read the run's
options, which the transform records in each instance's coverage, because
the same attributes hold received values only under the options that keep
them: under Modified Dates the dates that Full Dates keeps are shifted, and
a shifted date equal to its own source would mean that the shift failed.
Values that an option writes by C, such as shifted dates and AE-title
tokens, are therefore never explained, nor are person names and direct
identifiers, which the release gate never exempts, although it sends a
person name found in text that an option keeps (:func:`kept_text`) to QC
review rather than withholding the file, or a kept value outside
ISO 646, which :class:`~.residual_exemptions.KeptValues` does not read. A
UID is explained only where instances that the run does not write alone
held it (:func:`~.residual_exemptions.unwritten_uid`), or where its source is
a private data element that every instance which held it removed, by the
same whole-value rule (:func:`whole_values`,
:func:`~.residual_exemptions.removed_uid`).
"""

from __future__ import annotations

import functools
import types
from collections.abc import Iterator, Mapping
from typing import Literal

from .file_layout import ElementPath
from .policy import compose_custom_policy
from .residuals import _DATES, _KINDS, MAX_CHARACTERS, MIN_CHARACTERS, Form
from .residuals import SourceValue, ValueKind
from .residuals import _folded, _forms, _is_date, _length
from .standard import dictionary_attribute

# The VRs of text, coded text, and AE titles, in which kept text is read.
TEXT_VRS = frozenset({"AE", "CS", "LO", "LT", "SH", "ST", "UC", "UT"})
# The VRs of dates, times, and datetimes.
TEMPORAL_VRS = frozenset({"DA", "DT", "TM"})
# The kinds of value that a kept date or time can explain.
_EXPLICABLE = frozenset({ValueKind.DATE, ValueKind.DATETIME, ValueKind.TEXT})
# The kind of value that a kept UID can explain.
UID_KINDS = frozenset({ValueKind.UID})
# The characters of a DT value that are its date, as YYYYMMDD (PS3.5 6.2).
_DATE_CHARACTERS = 8

KeptVR = Literal["DA", "DT"]


@functools.cache
def option_actions(option: str) -> Mapping[str, str]:
    """Return the actions that ``option`` gives in place of the Basic Profile's.

    By tag, for the attributes of Table E.1-1 and of the reviewed
    supplementary rules to which the option alone, added to the
    Basic Profile, gives another action than the Basic Profile does.
    """
    basic = compose_custom_policy(())
    selected = compose_custom_policy((option,))
    actions = {}
    for profile, chosen in (
        (basic.actions, selected.actions),
        (basic.supplementary_actions, selected.supplementary_actions),
    ):
        actions.update(
            (tag, action)
            for tag, action in chosen.items()
            if action != profile.get(tag)
        )
    return types.MappingProxyType(actions)


@functools.cache
def kept_by(options: tuple[str, ...]) -> Mapping[str, frozenset[str]]:
    """Return the options that keep each attribute under ``options``, by tag.

    An option keeps an attribute where it gives K and the Basic Profile does
    not, and each other selected option either gives the attribute no action
    of its own or gives it K too.
    """
    kept: dict[str, set[str]] = {}
    for option in options:
        for tag, action in option_actions(option).items():
            if action == "K" and all(
                option_actions(other).get(tag, "K") == "K" for other in options
            ):
                kept.setdefault(tag, set()).add(option)
    return types.MappingProxyType(
        {tag: frozenset(keepers) for tag, keepers in kept.items()}
    )


def _vrs(tag: str) -> frozenset[str]:
    attribute = dictionary_attribute(tag)
    return frozenset(attribute.vrs) if attribute is not None else frozenset()


def _private_data(source: ElementPath) -> bool:
    group, element = int(source.tag[1:5], 16), int(source.tag[6:10], 16)
    return group % 2 == 1 and element >= 0x1000


def retained_text(tag: str, source: ElementPath, options: tuple[str, ...]) -> bool:
    """Return whether a kept text attribute explains a text finding of ``source``.

    Parameters
    ----------
    tag : str
        The attribute that the finding is in, such as ``"(0008,1010)"``.
    source : ElementPath
        The finding's source.
    options : tuple of str
        The run's options.

    Returns
    -------
    bool
        Whether a selected option keeps ``tag``, which the pinned dictionary
        gives only VRs of text, and ``source`` is a private data element or
        an attribute to which that option gives an action of its own, such
        as an AE title that Retain Device Identity cleans. Any other source,
        such as Institution Name (0008,0080) found in a kept Station Name
        under Retain Device Identity, is not explained.
    """
    if not kept_text(tag, options):
        return False
    return _private_data(source) or any(
        source.tag in option_actions(option) for option in kept_by(options)[tag]
    )


def kept_text(tag: str, options: tuple[str, ...]) -> bool:
    """Return whether a selected option keeps ``tag`` as text.

    Parameters
    ----------
    tag : str
        A standard attribute, such as ``"(0008,0080)"``.
    options : tuple of str
        The run's options.

    Returns
    -------
    bool
        Whether a selected option keeps ``tag`` (:func:`kept_by`), which the
        pinned dictionary gives only VRs of text (:data:`TEXT_VRS`), such as
        Institution Name (0008,0080) under Retain Institution Identity or
        Ethnic Group (0010,2160) under Retain Patient Characteristics. A
        private tag, to which the dictionary gives no VR, and an attribute
        that the Basic Profile keeps, such as Beam Name (300A,00C2), are not.
    """
    vrs = _vrs(tag)
    return tag in kept_by(options) and bool(vrs) and vrs <= TEXT_VRS


def retained_value(
    location: ElementPath,
    values: tuple[str, ...],
    text: str,
    source: ElementPath,
    found: tuple[SourceValue, ...],
    options: tuple[str, ...],
) -> bool:
    """Return whether a kept date or time explains a finding by equalling it.

    Parameters
    ----------
    location : ElementPath
        The element that the finding is in.
    values : tuple of str
        That element's values, as written, without padding.
    text : str
        That element's whole value, as written, values and separators.
    source : ElementPath
        The finding's source.
    found : tuple of SourceValue
        The source's collected values, pooled across the subject.
    options : tuple of str
        The run's options.

    Returns
    -------
    bool
        Whether a selected option keeps the element's attribute, which the
        pinned dictionary gives only VRs of dates, times, and datetimes,
        ``source`` is another element, one of the source's values is a
        whole value of the element, and each other value of the source that
        the search could have found in the element is one too. In an
        element of an attribute that the dictionary gives only VR DA, a
        value collected as DT whose date, as YYYYMMDD, is a whole value of
        the element counts as one, such as a vendor's private scan time
        found by its date in a kept Study Date. In an element of an
        attribute that the dictionary gives only VR DT, a value collected
        as DA or DT that is a date as YYYYMMDD, or a value collected as DT
        whose date, as YYYYMMDD, is, counts as one where that date is the
        first eight characters of a whole value of the element, which are
        its date, such as a vendor's private scan time found by its date in
        a kept Radiopharmaceutical Start DateTime (0018,1078) of the same
        day. A date or datetime found by its date in another spelling, such
        as YYYY-MM-DD or ACR-NEMA's YYYY.MM.DD, is not explained, nor is a
        datetime with a time found whole at the start of a longer kept
        datetime, or a date found after a kept value's start. Values are
        read as the search reads them, by the VR collected with each: a
        backslash separates the values of a multi-valued VR, but is a
        character of a single-valued one, such as ST. They are found as the
        search encodes them, in each of its codecs, so a value whose
        UTF-16LE bytes are in the element can be found there whatever the
        source's character set. A source value found
        inside a longer kept value, across two kept values, or in a value
        that no option keeps, is not explained. The search records one
        finding of a source in each element, for whichever of its pooled
        values it found there in the widest form, so a finding is explained
        only where every value of the source that could be in the element
        is.
    """
    vrs = _vrs(location.tag)
    if (
        location.tag not in kept_by(options)
        or not vrs
        or not vrs <= TEMPORAL_VRS
        or source == location
    ):
        return False
    kept_vr: KeptVR | None = "DA" if vrs == {"DA"} else "DT" if vrs == {"DT"} else None
    return whole_values(found, values, text, _EXPLICABLE, kept_vr=kept_vr)


def whole_values(
    found: tuple[SourceValue, ...],
    values: tuple[str, ...],
    text: str,
    kinds: frozenset[ValueKind],
    *,
    kept_vr: KeptVR | None = None,
) -> bool:
    """Return whether a kept element's whole values explain a source's finding.

    Parameters
    ----------
    found : tuple of SourceValue
        The source's collected values, pooled across the subject.
    values : tuple of str
        The kept element's values, as written, without padding.
    text : str
        The kept element's whole value, as written, values and separators.
    kinds : frozenset of ValueKind
        The kinds of source value that a whole kept value can explain, such
        as dates, datetimes, and text for a kept date (:func:`retained_value`)
        or :data:`UID_KINDS` for a kept UID.
    kept_vr : {"DA", "DT"}, optional
        The kept element's only VR, where it is DA or DT. In a kept DA, a
        datetime whose YYYYMMDD date is a whole kept value can explain a
        date finding; in a kept DT, a date, or a datetime's YYYYMMDD date,
        that is the first eight characters of a whole kept value can, as
        :func:`retained_value` describes. UID matching leaves it ``None``.

    Returns
    -------
    bool
        Whether one of the source's values, of one of ``kinds``, is a whole
        value of the element, and each other value of the source that the
        search could have found in the element is one too, as
        :func:`retained_value` reads them.
    """
    explained = False
    for value in found:
        for whole in _values_in(
            value, values, text.encode("ascii").lower(), kinds, kept_vr=kept_vr
        ):
            if whole is None:
                return False
            explained = explained or whole
    return explained


def _values_in(
    value: SourceValue,
    kept: tuple[str, ...],
    written: bytes,
    kinds: frozenset[ValueKind],
    *,
    kept_vr: KeptVR | None,
) -> Iterator[bool | None]:
    """Yield, for each value of ``value``, whether ``kept`` explains it.

    True for a value equal to a whole kept value; where ``kept_vr`` is DA,
    for a datetime whose YYYYMMDD date is one; where it is DT, for a date
    or datetime that is a date as YYYYMMDD, or a datetime whose YYYYMMDD
    date is, the first eight characters of a whole kept value;
    None for one that is not
    but that the search could find in ``written``, the kept element's whole
    value with ASCII letters in lower case; nothing for one that it could
    not. A value of a kind other than ``kinds`` is never explained. Each
    form that the search derives, of at least its shortest length and cut to
    its longest, is looked for as the search encodes it, in each codec and
    case, but ignoring the characters around it, which finds at least what
    the search does.
    """
    kind = _KINDS.get(value.vr)
    if not isinstance(value.value, str) or kind is None:
        return
    # The date that begins each kept datetime, which holds no time.
    dates = {whole[:_DATE_CHARACTERS] for whole in kept} if kept_vr == "DT" else set()
    whole = False
    for form, text in _forms(value.value, value.vr, kind):
        if form is Form.VALUE:
            whole = (
                kind in kinds
                and bool(text)
                and (
                    text in kept
                    or (kind in _DATES and _is_date(text) and text in dates)
                )
            )
            if whole:
                yield True
        elif (
            form is Form.DATE_DICOM
            and kind is ValueKind.DATETIME
            and text in (kept if kept_vr == "DA" else dates)
        ):
            # The found text is the whole kept date, or the date that begins
            # a kept datetime, neither of which holds the source's time.
            yield True
            continue
        if not whole and _length(text) >= MIN_CHARACTERS:
            # The search looks for a long form by its first characters.
            for _, folded, run in _folded(text[:MAX_CHARACTERS], value.codecs):
                if folded in written or (run is not None and run in written):
                    yield None
