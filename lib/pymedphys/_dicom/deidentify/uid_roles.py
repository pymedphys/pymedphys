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

"""The role of every UI attribute, a supplementary (L2) rule.

``uid_roles.toml`` gives each UI attribute of the pinned PS3.6 data dictionary
one role, curated by hand. An ``instance`` attribute identifies an instance,
event, entity, device, or organisation; a ``definition`` attribute identifies
something a standard or vendor publishes, such as a SOP Class or transfer
syntax. :func:`~pymedphys._dicom.deidentify.uids.transform_uid` applies the
role to a value. A UI attribute without a role is rejected, never replaced
merely because of its VR. The file's format and loader are shared with the
other roles files (:mod:`~pymedphys._dicom.deidentify.attribute_roles`).
"""

from __future__ import annotations

import enum
import pathlib

from .attribute_roles import AttributeRoles, RoleFormat, load_attribute_roles

SCHEMA = "pymedphys-deid-uid-roles/1"
UID_ROLES_PATH = pathlib.Path(__file__).resolve().parent / "uid_roles.toml"


class UIDRole(enum.Enum):
    """What a UI attribute identifies."""

    INSTANCE = "instance"
    DEFINITION = "definition"


_FORMAT = RoleFormat(schema=SCHEMA, vrs=frozenset({"UI"}), role=UIDRole)


def load_uid_roles(path: pathlib.Path | None = None) -> AttributeRoles[UIDRole]:
    """Load the role of every UI attribute.

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
        rule for an attribute that is not a UI attribute of the data
        dictionary, or with another keyword; has a role other than
        ``instance`` or ``definition``; repeats a tag; or has no role for a
        UI attribute of the data dictionary.
    """
    return load_attribute_roles(_FORMAT, path or UID_ROLES_PATH)
