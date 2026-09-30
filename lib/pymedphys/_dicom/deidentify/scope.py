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

"""Tell an instance the engine de-identifies from one it sequesters.

The first supported release de-identifies uncompressed instances of the CT
Image, RT Structure Set, RT Plan, and RT Dose IODs. Every other instance is
sequestered: neither de-identified nor written, and listed in the run report
by opaque identifiers only. That includes Structured Reports, Key Object
Selection documents, Presentation States, and instances of Private SOP
Classes, which the design always sequesters.

:func:`classify` decides from the instance's SOP Class UID (0008,0016), which
PS3.4 Table B.5-1 maps to its IOD, and from the transfer syntax of its file.
The result names the IOD of a Standard Storage SOP Class, a name from the
standard that identifies no one, so the report can say which IOD was
sequestered; it never names a UID.
"""

from __future__ import annotations

import dataclasses
import enum
import functools

from .sop_classes import StorageSOPClass, load_storage_sop_classes
from .uid_registry import RegistryTable
from .uids import normalise_uid

# The IODs of the first supported release, by the names Table B.5-1 gives
# them without "IOD".
SUPPORTED_IODS = frozenset({"CT Image", "RT Dose", "RT Plan", "RT Structure Set"})
# The uncompressed transfer syntaxes the first release reads: Implicit VR
# Little Endian and Explicit VR Little Endian.
SUPPORTED_TRANSFER_SYNTAXES = frozenset({"1.2.840.10008.1.2", "1.2.840.10008.1.2.1"})


class Disposition(enum.Enum):
    """Whether an instance is de-identified, and why not if it is sequestered."""

    SUPPORTED = "supported"
    # The instance has no SOP Class UID, or one that is not text.
    NO_SOP_CLASS = "no-sop-class"
    # The SOP Class is not a Standard Storage SOP Class of Table B.5-1: a
    # Private or retired SOP Class, one of another service class, or not a
    # UID.
    UNLISTED_SOP_CLASS = "unlisted-sop-class"
    # A Standard Storage SOP Class of an IOD the release does not support.
    UNSUPPORTED_IOD = "unsupported-iod"
    # A supported IOD in a transfer syntax the release does not read.
    UNSUPPORTED_TRANSFER_SYNTAX = "unsupported-transfer-syntax"


@dataclasses.dataclass(frozen=True)
class Classification:
    """How an instance is handled.

    Attributes
    ----------
    disposition : Disposition
    iod : str or None
        The IOD of the instance's Standard Storage SOP Class, as Table B.5-1
        names it without "IOD", such as ``"Comprehensive SR"``; ``None``
        when the table does not list the SOP Class.
    """

    disposition: Disposition
    iod: str | None

    @property
    def sequestered(self) -> bool:
        """Whether the instance is sequestered rather than de-identified."""
        return self.disposition is not Disposition.SUPPORTED


@functools.lru_cache(maxsize=None)
def _by_uid(
    table: RegistryTable[StorageSOPClass],
) -> dict[str, StorageSOPClass]:
    return {row.uid: row for row in table.rows}


def classify(
    sop_class_uid: object,
    transfer_syntax_uid: object,
    sop_classes: RegistryTable[StorageSOPClass] | None = None,
) -> Classification:
    """Classify an instance as de-identified or sequestered.

    Parameters
    ----------
    sop_class_uid : str
        The instance's SOP Class UID (0008,0016), as read, with any trailing
        NUL or space padding.
    transfer_syntax_uid : str
        The Transfer Syntax UID (0002,0010) of the instance's file, as read.
    sop_classes : RegistryTable of StorageSOPClass, optional
        PS3.4 Table B.5-1. Defaults to
        :func:`~pymedphys._dicom.deidentify.sop_classes.load_storage_sop_classes`.

    Returns
    -------
    Classification
        The SOP Class decides first: an instance with no SOP Class UID, one
        that Table B.5-1 does not list, or one of an unsupported IOD is
        sequestered whatever its transfer syntax. An instance of a supported
        IOD is sequestered unless its transfer syntax is supported.

    Examples
    --------
    >>> classify("1.2.840.10008.5.1.4.1.1.481.5", "1.2.840.10008.1.2.1")
    Classification(disposition=<Disposition.SUPPORTED: 'supported'>, iod='RT Plan')
    >>> classify("1.2.840.10008.5.1.4.1.1.88.33", "1.2.840.10008.1.2.1").sequestered
    True
    """
    if not isinstance(sop_class_uid, str) or not normalise_uid(sop_class_uid):
        return Classification(Disposition.NO_SOP_CLASS, None)
    if sop_classes is None:
        sop_classes = load_storage_sop_classes()
    row = _by_uid(sop_classes).get(normalise_uid(sop_class_uid))
    if row is None:
        return Classification(Disposition.UNLISTED_SOP_CLASS, None)
    if row.iod_name not in SUPPORTED_IODS:
        return Classification(Disposition.UNSUPPORTED_IOD, row.iod_name)
    if (
        not isinstance(transfer_syntax_uid, str)
        or normalise_uid(transfer_syntax_uid) not in SUPPORTED_TRANSFER_SYNTAXES
    ):
        return Classification(Disposition.UNSUPPORTED_TRANSFER_SYNTAX, row.iod_name)
    return Classification(Disposition.SUPPORTED, row.iod_name)
