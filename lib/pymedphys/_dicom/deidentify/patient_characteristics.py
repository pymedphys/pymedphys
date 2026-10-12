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

"""Settle the free text of Retain Patient Characteristics: held unless empty.

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

No method yet cleans such text automatically: a clinician's note can hold a
name, a date, or a place, and the reviewed lists that keep a ROI Name after
pooled human review do not yet cover these attributes (D-009). So none of
their values is written (D-038). :func:`held_unless_empty` leaves an
attribute with a value pending, which holds its instance, sequestered
rather than written: removing the value would contradict the Option, which
retains it (D-011), and writing the instance without the Option's code
would claim that the Basic Profile removed the characteristics that the
Option keeps (D-012). An attribute with no value, or whose values hold
nothing but padding, discloses nothing, so it is written with no value,
which the Type 2C of Sex Parameters for Clinical Use Category Comment
allows.
"""

from __future__ import annotations

from .keys import DeidKey

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


def held_unless_empty(source: str, key: DeidKey) -> tuple[str, ...] | None:
    """Return no values for an empty attribute, and None for one with a value.

    Parameters
    ----------
    source : str
        The attribute's decoded values, separated by backslashes; ``""`` for
        an attribute with no value. In UT, a backslash is a character of the
        text, so it is not a separator there, but it is treated as one here,
        since each of these attributes is either LO, in which it separates
        values, or UT, of which a value of backslashes and padding alone
        describes nothing.
    key : DeidKey
        The run's key, which is not used: nothing is derived from a value.

    Returns
    -------
    tuple of str or None
        ``()``, written as no value, where every value holds nothing but
        padding; otherwise None, which leaves the attribute pending, so that
        its instance is held.

    Examples
    --------
    >>> key = DeidKey(bytes(32))
    >>> held_unless_empty("", key), held_unless_empty(" \\\\ ", key)
    ((), ())
    >>> held_unless_empty("NONE KNOWN", key) is None
    True
    """
    del key
    if all(not value.strip(_PADDING) for value in source.split("\\")):
        return ()
    return None
