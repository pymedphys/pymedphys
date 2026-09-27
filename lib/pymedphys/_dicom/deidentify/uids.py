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

"""Keyed replacement UIDs (design decision D-003).

A UID that must be replaced is replaced by a ``2.25.`` UID (PS3.5 B.2) built
from a name-based version 5 UUID (ITU-T X.667 clause 14.3). The UUID's name is
the 32-byte HMAC-SHA256 of the unpadded source UID under the run's key
(D-004), and its namespace is :data:`UID_NAMESPACE`. The same key always gives
the same replacement, so every occurrence of a UID, in any file or run under
that key, is replaced consistently without a stored map. Without the key,
knowing a source UID does not reveal its replacement.

Which UIDs are replaced and which, such as SOP Class UIDs and well-known
coding-scheme UIDs, are retained is decided by the rule layers before this
module is used (D-003).
"""

from __future__ import annotations

import hashlib
import uuid

from .keys import DeidKey

UID_ROOT = "2.25."
# The namespace of every replacement UUID. It is the version 5 UUID of
# "https://docs.pymedphys.com/deidentify/uid-namespace" in the URL namespace,
# and must never change: a new namespace would change every replacement.
UID_NAMESPACE = uuid.UUID("6f71d76c-0573-58b6-bfda-7c5b4ee304f1")
# Trailing padding that a UI value may carry: NUL, and space from some writers.
_PADDING = "\x00 "


def normalise_uid(value: str) -> str:
    """Return ``value`` without its trailing NUL and space padding."""
    return value.rstrip(_PADDING)


def uuid5(namespace: uuid.UUID, name: bytes) -> uuid.UUID:
    """Return the name-based version 5 UUID of ``name`` in ``namespace``.

    This is the construction of ITU-T X.667 clause 14.3, which
    :func:`uuid.uuid5` implements for text names only before Python 3.12.
    SHA-1 is used as X.667 specifies, not for its collision resistance: the
    names are keyed tokens that nobody without the key can choose.
    """
    digest = hashlib.sha1(namespace.bytes + name, usedforsecurity=False).digest()
    return uuid.UUID(bytes=digest[:16], version=5)


def replacement_uid(key: DeidKey, uid: str) -> str:
    """Return the replacement for ``uid`` under ``key``.

    Trailing NUL and space padding is removed first, so padded and unpadded
    forms of a UID have the same replacement. An invalid source UID is
    replaced like any other.

    Parameters
    ----------
    key : DeidKey
        The run's key.
    uid : str
        The source UID.

    Returns
    -------
    str
        A ``2.25.`` UID of at most 44 characters.

    Raises
    ------
    ValueError
        If ``uid`` is empty once its padding is removed.

    Examples
    --------
    >>> key = DeidKey(bytes(32))
    >>> replacement_uid(key, "1.2.3") == replacement_uid(key, "1.2.3\\x00")
    True
    """
    normalised = normalise_uid(uid)
    if not normalised:
        raise ValueError("an empty UID has no replacement")
    token = key.derive("uid", normalised)
    return f"{UID_ROOT}{uuid5(UID_NAMESPACE, token).int}"
