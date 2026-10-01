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

"""The File Meta Information and preamble written in place of the source's.

DICOM PS3.15 E.1.1 requires a de-identified file's File Meta Information,
including its 128-byte preamble, to be replaced with a description of the
de-identifying application, because the source file's can name the systems
that created, sent, and received it. Nothing in either is copied from the
source file. :func:`file_meta_information` builds the File Meta Information
of PS3.10 Table 7.1-1 for one output instance, holding exactly these
elements, in this order:

- File Meta Information Group Length (0002,0000);
- File Meta Information Version (0002,0001), the bytes 00H and 01H;
- Media Storage SOP Class UID (0002,0002), the instance's SOP Class UID;
- Media Storage SOP Instance UID (0002,0003), its replacement SOP Instance
  UID;
- Transfer Syntax UID (0002,0010), one the engine supports;
- Implementation Class UID (0002,0012), :data:`IMPLEMENTATION_CLASS_UID`;
- Implementation Version Name (0002,0013), :data:`IMPLEMENTATION_VERSION_NAME`.

Application Entity Titles, Presentation Addresses, private information, and
every other File Meta element are left out. The preamble, :data:`PREAMBLE`,
is 128 zero bytes, which PS3.10 Section 7.1 sets for a preamble that is not
used. :func:`write_file` writes a data set with both.

The Implementation Class UID identifies the de-identifier, whatever its
version. It is the first UID of the arc ``1.2.826.0.1.3680043.10.188.1``,
which PyMedPhys reserves for UIDs that it fixes in its design, under the root
issued to PyMedPhys, ``PYMEDPHYS_ROOT_UID`` in ``pymedphys._dicom.uid``. It
never changes.
"""

from __future__ import annotations

import os
import re
from typing import BinaryIO

from pymedphys._imports import pydicom

from pymedphys._dicom.uid import PYMEDPHYS_FIXED_UID_ARC
from pymedphys._version import __version__

from . import scope, values

# The first UID of the arc 1.2.826.0.1.3680043.10.188.1, which PyMedPhys
# reserves for UIDs that it fixes in its design, under the root issued to
# PyMedPhys (PYMEDPHYS_ROOT_UID in pymedphys._dicom.uid). It must never
# change, as it names the writer of every file the engine has written.
IMPLEMENTATION_CLASS_UID = "1.2.826.0.1.3680043.10.188.1.1"
assert IMPLEMENTATION_CLASS_UID == f"{PYMEDPHYS_FIXED_UID_ARC}.1"
FILE_META_INFORMATION_VERSION = b"\x00\x01"
PREAMBLE = bytes(128)

_NAME = "PYMEDPHYS"
_SH_LENGTH = 16
# A version that may follow the name: characters of the default repertoire
# (ISO 646) other than space, which SH ignores at either end, and the
# backslash, which SH excludes.
_VERSION = re.compile(r"[\x21-\x5b\x5d-\x7e]+")


def implementation_version_name(version: str) -> str:
    """Return the Implementation Version Name for a version of PyMedPhys.

    The name is ``PYMEDPHYS``, a space, and the version, where that fits the
    16 characters of SH; otherwise it is ``PYMEDPHYS`` alone. Most
    development, pre-release, and local versions, such as ``0.42.0.dev1``,
    do not fit. PS3.10 limits the name to the default character repertoire,
    so a version holding any other character, a space, or a backslash is left
    out too. The Implementation Class UID, not this name, identifies the
    de-identifier.

    Parameters
    ----------
    version : str
        A version of PyMedPhys, such as ``"0.42.0"``.

    Returns
    -------
    str
        A valid SH value of at most 16 characters.

    Examples
    --------
    >>> implementation_version_name("0.42.0")
    'PYMEDPHYS 0.42.0'
    >>> implementation_version_name("0.42.0.dev1")
    'PYMEDPHYS'
    """
    name = f"{_NAME} {version}"
    if _VERSION.fullmatch(version) and len(name) <= _SH_LENGTH:
        return name
    return _NAME


# The Implementation Version Name of the installed version.
IMPLEMENTATION_VERSION_NAME = implementation_version_name(__version__)


def _checked_uid(value: object, name: str) -> str:
    # These elements are Type 1, so an empty value, valid in UI, is not.
    if not isinstance(value, str) or not value:
        raise ValueError(f"the {name} is empty or not a single text value")
    problem = values.value_problem("UI", value)
    if problem:
        raise ValueError(f"the {name} {problem}")
    return value


def _encoded_length(vr: str, value: str | bytes) -> int:
    # In Explicit VR Little Endian (PS3.5 Section 7.1.2), an element has a
    # 4-byte tag and a 2-byte VR, then a 2-byte length, or for OB 2 reserved
    # bytes and a 4-byte length, then its value padded to an even length.
    # Each value here is ASCII, so it has one byte per character.
    header = 12 if vr == "OB" else 8
    return header + len(value) + len(value) % 2


def file_meta_information(
    *, sop_class_uid: str, sop_instance_uid: str, transfer_syntax_uid: str
) -> pydicom.dataset.FileMetaDataset:
    """Return the File Meta Information for one output instance.

    Each UID is written as given, so it must be a valid UI value without
    trailing padding; encoding adds the padding byte that an odd length
    needs.

    Parameters
    ----------
    sop_class_uid : str
        The instance's SOP Class UID (0008,0016).
    sop_instance_uid : str
        The instance's replacement SOP Instance UID (0008,0018).
    transfer_syntax_uid : str
        The transfer syntax that the instance's data set is written in, one
        of :data:`~pymedphys._dicom.deidentify.scope.SUPPORTED_TRANSFER_SYNTAXES`:
        Implicit VR Little Endian or Explicit VR Little Endian.

    Returns
    -------
    pydicom.dataset.FileMetaDataset
        A new data set holding, in this order, File Meta Information Group
        Length, File Meta Information Version, the three given UIDs as Media
        Storage SOP Class UID, Media Storage SOP Instance UID, and Transfer
        Syntax UID, Implementation Class UID, and Implementation Version Name.
        The group length counts the bytes of the six elements after it, as
        they are encoded in the file.

    Raises
    ------
    ValueError
        If a UID is empty, not text, or not a valid UI value, or the transfer
        syntax is not one the engine supports. The message names the
        attribute, never the value.

    Examples
    --------
    >>> meta = file_meta_information(
    ...     sop_class_uid="1.2.840.10008.5.1.4.1.1.481.5",
    ...     sop_instance_uid="2.25.45880388381039869122547204841297202992",
    ...     transfer_syntax_uid="1.2.840.10008.1.2.1",
    ... )
    >>> len(meta), meta.TransferSyntaxUID.name
    (7, 'Explicit VR Little Endian')
    """
    sop_class_uid = _checked_uid(sop_class_uid, "SOP Class UID")
    sop_instance_uid = _checked_uid(sop_instance_uid, "SOP Instance UID")
    transfer_syntax_uid = _checked_uid(transfer_syntax_uid, "Transfer Syntax UID")
    if transfer_syntax_uid not in scope.SUPPORTED_TRANSFER_SYNTAXES:
        raise ValueError("the Transfer Syntax UID is not one the engine supports")
    elements = (
        ("FileMetaInformationVersion", "OB", FILE_META_INFORMATION_VERSION),
        ("MediaStorageSOPClassUID", "UI", sop_class_uid),
        ("MediaStorageSOPInstanceUID", "UI", sop_instance_uid),
        ("TransferSyntaxUID", "UI", transfer_syntax_uid),
        ("ImplementationClassUID", "UI", IMPLEMENTATION_CLASS_UID),
        ("ImplementationVersionName", "SH", IMPLEMENTATION_VERSION_NAME),
    )
    meta = pydicom.dataset.FileMetaDataset()
    meta.add_new(
        "FileMetaInformationGroupLength",
        "UL",
        sum(_encoded_length(vr, value) for _, vr, value in elements),
    )
    for keyword, vr, value in elements:
        meta.add_new(keyword, vr, value)
    return meta


def write_file(
    destination: str | os.PathLike[str] | BinaryIO,
    dataset: pydicom.dataset.Dataset,
    *,
    transfer_syntax_uid: str,
) -> None:
    """Write a data set as a DICOM file with new File Meta Information.

    The file has :data:`PREAMBLE` and the File Meta Information that
    :func:`file_meta_information` builds from the data set's own SOP Class
    UID and SOP Instance UID, whatever ``dataset.file_meta`` and
    ``dataset.preamble`` hold. pydicom's ``dcmwrite(...,
    enforce_file_format=True)``, which writes it, would otherwise keep the
    source file's preamble and File Meta elements. The data set's
    ``file_meta`` and ``preamble`` are not changed, but, as in any pydicom
    write, its ambiguous VRs may be resolved and its raw elements decoded in
    place.

    Parameters
    ----------
    destination : str, os.PathLike, or binary file
        Where to write the file, as :func:`pydicom.dcmwrite` takes it. An
        existing file is overwritten.
    dataset : pydicom.dataset.Dataset
        The de-identified data set, which holds its replacement SOP Instance
        UID.
    transfer_syntax_uid : str
        The transfer syntax to write the data set in, as for
        :func:`file_meta_information`.

    Raises
    ------
    ValueError
        As :func:`file_meta_information` does, naming the data set's SOP
        Class UID or SOP Instance UID if either is missing or not valid.
        Nothing is written then.
    """
    meta = file_meta_information(
        sop_class_uid=dataset.get("SOPClassUID"),
        sop_instance_uid=dataset.get("SOPInstanceUID"),
        transfer_syntax_uid=transfer_syntax_uid,
    )
    # A shallow copy shares the data set's elements but has its own File Meta
    # Information and preamble.
    output = dataset.copy()
    output.file_meta = meta
    output.preamble = PREAMBLE
    pydicom.dcmwrite(destination, output, enforce_file_format=True)
