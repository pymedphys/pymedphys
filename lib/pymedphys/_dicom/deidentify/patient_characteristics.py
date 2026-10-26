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

"""Settle the free text of Retain Patient Characteristics: pending unless empty.

Under the Retain Patient Characteristics Option, Table E.1-1 keeps fourteen
attributes, such as Patient's Age (0010,1010), Patient's Sex (0010,0040),
and Patient's Weight (0010,1030), and gives C to five of free text that
describe the patient: Allergies (0010,2110), Pre-Medication (0040,0012),
Special Needs (0038,0050), Patient State (0038,0500), and Sex Parameters
for Clinical Use Category Comment (0010,0042). C replaces a value "with
values of similar meaning known not to contain identifying information and
consistent with the VR" (Table E.1-1a), and PS3.15 E.3.7 requires the
manner of cleaning retained attributes to be described in the conformance
statement.

No method cleans such text automatically: a clinician's note can hold a
name, a date, or a place, and D-009 retains no free-text value without
pooled human review. :func:`held_unless_empty`, the Option's cleaner of the
whole instance, writes none of their values itself (D-038). It leaves out an
attribute with a value, which stays pending: removing the value would
contradict the Option, which retains it (D-011), and writing the instance
without the Option's code would claim that the Basic Profile removed the
characteristics that the Option keeps (D-012). Under Clean Descriptors as
well, descriptor cleaning gives each value left pending the decision of the
custodian's reviewed descriptors list, and holds the instance for review
where the list does not clean one
(:mod:`~pymedphys._dicom.deidentify.descriptor_cleaning`); otherwise the
pending attribute sequesters its instance. An attribute with no value, or
whose values hold nothing but padding, discloses nothing, so it is written
with no value, which the Type 2C of Sex Parameters for Clinical Use
Category Comment allows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .dates import DateOffsets
from .file_layout import ElementPath
from .keys import DeidKey
from .pseudonyms import SubjectIdentity
from .residuals import SourceValue

# The attributes that Retain Patient Characteristics gives C in Table E.1-1
# of PS3.15 2026d, all free text.
TAGS = frozenset(
    {
        "(0010,0042)",  # Sex Parameters for Clinical Use Category Comment, UT
        "(0010,2110)",  # Allergies, LO
        "(0038,0050)",  # Special Needs, LO
        "(0038,0500)",  # Patient State, LO
        "(0040,0012)",  # Pre-Medication, LO
    }
)
VRS = frozenset({"LO", "UT"})
# The characters that pad a text value: spaces (PS3.5 Section 6.2), and the
# NUL that some writers pad with instead.
_PADDING = " \x00"


def is_empty(value: str) -> bool:
    """Whether a decoded value holds nothing but padding and separators.

    In UT, a backslash is a character of the text, not a separator, but it
    is treated as one here, since each of these attributes is either LO, in
    which it separates values, or UT, of which a value of backslashes and
    padding alone describes nothing.

    Examples
    --------
    >>> is_empty(""), is_empty(" \\\\ "), is_empty("NONE KNOWN")
    (True, True, False)
    """
    return all(not part.strip(_PADDING) for part in value.split("\\"))


def held_unless_empty(
    values: Iterable[SourceValue],
    key: DeidKey,
    identity: SubjectIdentity | None,
    offsets: DateOffsets | None = None,
) -> Mapping[ElementPath, tuple[tuple[str | bytes, ...], bool]]:
    """Settle each attribute with no value, and leave out each with one.

    Parameters
    ----------
    values : iterable of SourceValue
        The source value of each attribute of one instance to settle.
    key : DeidKey
        The run's key, which is not used: nothing is derived from a value.
    identity : SubjectIdentity or None
        The instance's subject, which is not used.
    offsets : callable, optional
        What gives a subject's date offset, which is not used.

    Returns
    -------
    Mapping of ElementPath to tuple
        For each attribute whose decoded values are empty (:func:`is_empty`),
        ``((), False)``: written with no value, which is not the source's
        own. Every other attribute, with a value or with one that could not
        be decoded, is left out, so that it stays pending, for the reviewed
        descriptors list to decide on under Clean Descriptors, and otherwise
        to sequester its instance.
    """
    del key, identity, offsets
    return {
        value.source: ((), False)
        for value in values
        if isinstance(value.value, str) and is_empty(value.value)
    }
