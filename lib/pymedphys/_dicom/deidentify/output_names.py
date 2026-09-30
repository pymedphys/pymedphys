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

"""Output file and directory names built only from replacement identifiers.

Each instance is written below the output directory to::

    <Patient ID>/<Study Instance UID>/<Series Instance UID>/<SOP Instance UID>.dcm

where each value is the replacement the instance carries: its keyed patient
pseudonym (:mod:`~pymedphys._dicom.deidentify.pseudonyms`) and its keyed
replacement UIDs (:mod:`~pymedphys._dicom.deidentify.uids`). The levels
follow the DICOM information model, so the instances of a series share a
directory. The names contain no source path, file name, or attribute value.
Under one key they are the same in every run, worker, and processing order,
and a new key gives unrelated names.

The names hold only ASCII digits, upper-case letters, ``.`` and ``-``, and
the ``.dcm`` suffix. They are therefore valid on Windows, macOS, and Linux,
are never a reserved Windows device name such as ``CON``, and never differ
only by case. A path below the output directory has at most
:data:`MAX_RELATIVE_PATH_LENGTH` characters.

This module writes nothing. :func:`find_collisions` reports instances that
would share a file name; they are never renamed.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from pathlib import PurePosixPath

from . import pseudonyms, uids

FILE_SUFFIX = ".dcm"
# The longest path below the output directory: a 21-character Patient ID,
# three UIDs of at most 44 characters ("2.25." and the 39 digits of the
# largest version 5 UUID), three separators, and the suffix. Without long
# path support, Windows limits a file's path to 259 characters (MAX_PATH less
# its terminating NUL), which leaves 98 for the output directory. Creating
# directories, which Windows limits to MAX_PATH less 12, allows more, since
# the deepest directory's path is 49 characters shorter than its files'.
MAX_RELATIVE_PATH_LENGTH = 160

# The Patient ID of a pseudonym: its prefix and its code in the RFC 4648
# base32 alphabet. The code's bytes are exactly 16 characters, unpadded.
_PATIENT_ID = re.compile(
    re.escape(pseudonyms.PATIENT_ID_PREFIX)
    + f"[A-Z2-7]{{{pseudonyms.CODE_BYTES * 8 // 5}}}"
)
# A "2.25." UID (PS3.5 B.2) of at most 39 digits, as many as 2**128 has.
_UID = re.compile(re.escape(uids.UID_ROOT) + "(?P<number>0|[1-9][0-9]{0,38})")
# Trailing padding that an LO value may carry: space, and NUL from some
# writers.
_PADDING = " \x00"


class OutputNameError(ValueError):
    """A value that is not a replacement identifier, so it cannot name output."""


def _is_name_based_sha1_uuid(number: int) -> bool:
    if number >= 1 << 128:
        return False
    as_uuid = uuid.UUID(int=number)
    return as_uuid.variant == uuid.RFC_4122 and as_uuid.version == 5


def _replacement_patient_id(value: object) -> str:
    if isinstance(value, str):
        unpadded = value.rstrip(_PADDING)
        if _PATIENT_ID.fullmatch(unpadded):
            return unpadded
    raise OutputNameError("the Patient ID is not a patient pseudonym")


def _replacement_uid(value: object, attribute: str) -> str:
    if isinstance(value, str):
        unpadded = uids.normalise_uid(value)
        match = _UID.fullmatch(unpadded)
        if match and _is_name_based_sha1_uuid(int(match["number"])):
            return unpadded
    raise OutputNameError(f"the {attribute} is not a replacement UID")


def instance_path(
    *,
    patient_id: str,
    study_instance_uid: str,
    series_instance_uid: str,
    sop_instance_uid: str,
) -> PurePosixPath:
    """Return the path of an instance's file below the output directory.

    Each argument is a replacement value that the instance carries. Trailing
    space and NUL padding is removed first. The path is the same on every
    platform: join it to the output directory with ``/``, or use
    ``str(path)`` as the name of an archive member.

    Parameters
    ----------
    patient_id : str
        The replacement Patient ID, ``"DEID-"`` and 16 base32 characters.
    study_instance_uid, series_instance_uid, sop_instance_uid : str
        The replacement UIDs, each a ``2.25.`` UID from a version 5 UUID.

    Returns
    -------
    pathlib.PurePosixPath
        ``<Patient ID>/<Study Instance UID>/<Series Instance UID>/<SOP
        Instance UID>.dcm``, of at most :data:`MAX_RELATIVE_PATH_LENGTH`
        characters.

    Raises
    ------
    OutputNameError
        If a value is not text in the form of a replacement. The message
        names the attribute, never the value. An instance whose Study,
        Series, or SOP Instance UID was retained rather than replaced
        therefore cannot be named, and must be sequestered.

    Notes
    -----
    The checks are of form only, so a source value already in the form of a
    replacement, such as a ``2.25.`` UID from a version 5 UUID, passes them.
    Every preset replaces all four values, so only a fault in the engine
    could pass one.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.keys import DeidKey
    >>> key = DeidKey(bytes(32))
    >>> identity = pseudonyms.SubjectIdentity.from_patient_id("123")
    >>> path = instance_path(
    ...     patient_id=pseudonyms.patient_pseudonym(key, identity).patient_id,
    ...     study_instance_uid=uids.replacement_uid(key, "1.2.3"),
    ...     series_instance_uid=uids.replacement_uid(key, "1.2.3.4"),
    ...     sop_instance_uid=uids.replacement_uid(key, "1.2.3.4.5"),
    ... )
    >>> len(path.parts), path.suffix
    (4, '.dcm')
    """
    return PurePosixPath(
        _replacement_patient_id(patient_id),
        _replacement_uid(study_instance_uid, "Study Instance UID"),
        _replacement_uid(series_instance_uid, "Series Instance UID"),
        _replacement_uid(sop_instance_uid, "SOP Instance UID") + FILE_SUFFIX,
    )


def find_collisions(
    paths: Iterable[PurePosixPath],
) -> tuple[tuple[int, ...], ...]:
    """Return the positions of the paths that share a file name.

    A file's name is its instance's replacement SOP Instance UID, so paths
    that share one belong to one instance given twice, or to two objects with
    one SOP Instance UID, possibly in different series. They are reported,
    never renamed: a name that depended on the other instances would change
    when an incremental export under a project key adds instances.

    Parameters
    ----------
    paths : iterable of pathlib.PurePosixPath
        Paths from :func:`instance_path`.

    Returns
    -------
    tuple of tuple of int
        One group for each file name shared by more than one path, holding
        the 0-based positions of those paths in ascending order. Groups are
        ordered by their first position, and hold no names or values. Empty
        when no two paths share a file name.
    """
    positions: dict[str, list[int]] = {}
    for position, path in enumerate(paths):
        positions.setdefault(path.name, []).append(position)
    # Dictionaries keep insertion order, so groups follow their first position.
    return tuple(tuple(group) for group in positions.values() if len(group) > 1)
