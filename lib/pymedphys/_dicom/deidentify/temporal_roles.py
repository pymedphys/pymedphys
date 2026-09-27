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

"""The role of every date, time, and datetime attribute, a supplementary (L2) rule.

``temporal_roles.toml`` gives each DA, DT, and TM attribute of the pinned PS3.6
data dictionary one role, curated by hand against the attribute descriptions in
PS3.3, including attributes that Table E.1-1 omits. It also covers every
attribute of another VR that Table E.1-1 cleans under Retain Longitudinal
Temporal Information with Modified Dates, such as Timezone Offset From UTC
(0008,0201).

Where that option is selected, :attr:`TemporalRole.action` says what happens
to a value. Subject-event and radiation-source values move by the subject's
offset (:mod:`~pymedphys._dicom.deidentify.dates`), which keeps the intervals
between them, such as a brachytherapy source's decay from its reference date to
treatment. Device, vocabulary-version, and other values are replaced by a fixed
dummy value: shifting a date whose original may be known, such as a published
version or a calibration date, would disclose the offset. An instance with a
time zone offset is sequestered: the option cleans the offset, but no
replacement is yet defined that keeps the intervals between local times and
DT values with their own offsets and does not reveal the season of the
original date. Without the option, Table E.1-1 decides. The file's format and
loader are shared with the other roles files
(:mod:`~pymedphys._dicom.deidentify.attribute_roles`).
"""

from __future__ import annotations

import enum
import pathlib

from .attribute_roles import AttributeRoles, RoleFormat, load_attribute_roles

SCHEMA = "pymedphys-deid-temporal-roles/1"
TEMPORAL_ROLES_PATH = pathlib.Path(__file__).resolve().parent / "temporal_roles.toml"


class TemporalAction(enum.Enum):
    """What Modified Dates does to a value.

    ``SEQUESTER`` means the instance is not exported under the option, because
    no conforming treatment of the value is defined yet.
    """

    SHIFT = "shift"
    DUMMY = "dummy"
    SEQUESTER = "sequester"


class TemporalRole(enum.Enum):
    """What a date, time, or datetime attribute records."""

    SUBJECT_EVENT = "subject-event"
    RADIATION_SOURCE = "radiation-source"
    DEVICE = "device"
    VOCABULARY_VERSION = "vocabulary-version"
    TIME_ZONE = "time-zone"
    OTHER = "other"

    @property
    def action(self) -> TemporalAction:
        """What Modified Dates does to a value with this role.

        Subject events and radiation sources move by the subject's offset, an
        instance with a time zone offset is sequestered, and every other role
        takes a fixed dummy value.
        """
        if self in (TemporalRole.SUBJECT_EVENT, TemporalRole.RADIATION_SOURCE):
            return TemporalAction.SHIFT
        if self is TemporalRole.TIME_ZONE:
            return TemporalAction.SEQUESTER
        return TemporalAction.DUMMY


_FORMAT = RoleFormat(
    schema=SCHEMA,
    vrs=frozenset({"DA", "DT", "TM"}),
    role=TemporalRole,
    cleaned_under="retain_longitudinal_modified_dates",
)


def load_temporal_roles(
    path: pathlib.Path | None = None,
) -> AttributeRoles[TemporalRole]:
    """Load the role of every date, time, and datetime attribute.

    The roles also cover every attribute of another VR that Table E.1-1 cleans
    under Retain Longitudinal Temporal Information with Modified Dates.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The roles file. Defaults to the one shipped with PyMedPhys.

    Raises
    ------
    ~pymedphys._dicom.deidentify.attribute_roles.RoleError
        If the file cannot be read; has another schema; covers another
        edition than the data dictionary or lacks its acknowledgement; does
        not give its rules as an array of tables; has a rule without exactly
        the fields tag, keyword, role, and an optional non-empty note; has a
        rule for an attribute that is neither a DA, DT, or TM attribute of
        the data dictionary nor one that Table E.1-1 cleans under Modified
        Dates, or with another keyword; has a role that :class:`TemporalRole`
        does not define; repeats a tag; or has no role for an attribute it
        covers.
    """
    return load_attribute_roles(_FORMAT, path or TEMPORAL_ROLES_PATH)
