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

"""Find the IOD of an instance's SOP Class, from DICOM PS3.4 Table B.5-1.

An instance names its SOP Class in SOP Class UID (0008,0016), not the IOD
that defines its attributes. Table B.5-1 of PS3.4 lists the Standard Storage
SOP Classes, each with its IOD in PS3.3, such as the CT Image IOD for both CT
Image Storage and CT Image Storage - For Processing. ``pymedphys dev
deid-tables`` generates the whole table from the pinned edition as
``sop_classes.json``, and the loader here checks it as
:func:`~pymedphys._dicom.deidentify.uid_registry.load_registry_table` checks
the tables of PS3.6 Annex A.

:func:`iod_for_sop_class` returns the IOD, with the attribute Types that
:mod:`~pymedphys._dicom.deidentify.iods` generates, for the SOP Classes of
those IODs, which in 2026d include every SOP Class of Table B.5-1. Any other
SOP Class, whether a Standard SOP Class of an IOD whose Types are not
generated, a retired or Private SOP Class, or one from a later edition, has
none, and is outside the supported scope. Having Types does not make an IOD
supported: :mod:`~pymedphys._dicom.deidentify.scope` decides that.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
from collections.abc import Callable

from .iods import IOD, IODTables, load_iod_tables
from .standard import StandardTableError, _is_text
from .uid_registry import (
    RegistryTable,
    RegistryTableSpec,
    _matches,
    is_uid,
    load_registry_table,
)
from .uids import normalise_uid

# The IOD Specification column: an IOD's name followed by "IOD", as in
# "CT Image IOD".
IOD_SPECIFICATION_PATTERN = re.compile(r"\S(?:.*\S)? IOD")
# The Specialization column: the sections of PS3.4 Annex B that specialise a
# SOP Class, separated by spaces, as in "B.5.1.7 B.5.1.23 B.5.1.26".
SPECIALIZATION_PATTERN = re.compile(r"B(?:\.[0-9]+)+(?: B(?:\.[0-9]+)+)*")


@dataclasses.dataclass(frozen=True)
class StorageSOPClass:
    """One row of DICOM PS3.4 Table B.5-1, the Standard Storage SOP Classes.

    Attributes
    ----------
    name : str
        As published, such as ``"CT Image Storage"``. One name, "Macular Grid
        Thickness and Volume Report", lacks the "Storage" that PS3.6 gives it.
    uid : str
        The SOP Class UID, such as ``"1.2.840.10008.5.1.4.1.1.2"``.
    iod : str
        The IOD that PS3.3 defines for the SOP Class, as published, such as
        ``"CT Image IOD"``. SOP Classes can share an IOD.
    specialization : str
        The sections of PS3.4 that specialise the SOP Class, separated by
        spaces, such as ``"B.5.1.7 B.5.1.23 B.5.1.26"``, or ``""``.
    """

    name: str
    uid: str
    iod: str
    specialization: str

    @property
    def iod_name(self) -> str:
        """The IOD's name as :class:`~pymedphys._dicom.deidentify.iods.IOD` gives it.

        That is :attr:`iod` without its final "IOD", such as ``"CT Image"``.
        """
        return self.iod.removesuffix(" IOD")


_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    (lambda row: _is_text(row["name"]), "has a name that is not non-empty text"),
    (
        lambda row: is_uid(row["uid"]),
        "has a UID that is not numeric components without leading zeros, in at "
        "most 64 characters",
    ),
    (
        lambda row: _matches(IOD_SPECIFICATION_PATTERN, row["iod"]),
        "has an IOD that is not a name followed by IOD",
    ),
    (
        lambda row: (
            row["specialization"] == ""
            or _matches(SPECIALIZATION_PATTERN, row["specialization"])
        ),
        "has a specialization that is not empty or section numbers of PS3.4 "
        "Annex B separated by single spaces",
    ),
)

# PS3.4 Table B.5-1, as generated and loaded.
STORAGE_SOP_CLASS_TABLE = RegistryTableSpec(
    "PS3.4 Table B.5-1",
    "sop_classes.json",
    StorageSOPClass,
    _CHECKS,
    (("uid",), ("name",)),
)


def load_storage_sop_classes(
    path: pathlib.Path | None = None,
) -> RegistryTable[StorageSOPClass]:
    """Load Table B.5-1 of DICOM PS3.4, the Standard Storage SOP Classes.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    RegistryTable of StorageSOPClass

    Raises
    ------
    StandardTableError
        For any of the file-level problems
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1` rejects,
        with the acknowledgement "DICOM PS3.4 <edition>, © NEMA"; if a row
        does not have exactly the fields of :class:`StorageSOPClass`, or has
        an empty name, a UID that
        :func:`~pymedphys._dicom.deidentify.uid_registry.is_uid` rejects, an
        IOD that is not a name followed by "IOD", or a specialization that is
        neither empty nor section numbers of PS3.4 Annex B separated by single
        spaces; or if a UID or name repeats.
    """
    return load_registry_table(STORAGE_SOP_CLASS_TABLE, path)


def iod_for_sop_class(
    sop_class_uid: str,
    sop_classes: RegistryTable[StorageSOPClass] | None = None,
    iod_tables: IODTables | None = None,
) -> IOD | None:
    """Return the IOD of a Storage SOP Class, if its attribute Types are generated.

    Parameters
    ----------
    sop_class_uid : str
        The instance's SOP Class UID (0008,0016). Trailing NUL and space
        padding is removed first: PS3.5 Section 9.1 pads a UID of odd length,
        such as RT Plan Storage's, with a NUL.
    sop_classes : RegistryTable of StorageSOPClass, optional
        Table B.5-1. Defaults to :func:`load_storage_sop_classes`.
    iod_tables : IODTables, optional
        The IODs whose Types are generated. Defaults to
        :func:`~pymedphys._dicom.deidentify.iods.load_iod_tables`.

    Returns
    -------
    IOD or None
        The IOD that Table B.5-1 gives for the SOP Class, with its modules,
        Functional Group Macros, and attribute Types. None if Table B.5-1 does
        not list the UID, as for a retired or Private SOP Class or a SOP Class
        that another part of PS3.4 defines; or if the IOD's Types are not
        generated.

    Raises
    ------
    StandardTableError
        If either table cannot be loaded, as
        :func:`load_storage_sop_classes` and
        :func:`~pymedphys._dicom.deidentify.iods.load_iod_tables` describe, or
        if the two were generated from different editions.

    Examples
    --------
    >>> iod_for_sop_class("1.2.840.10008.5.1.4.1.1.481.5").name  # RT Plan Storage
    'RT Plan'
    >>> iod_for_sop_class("1.2.840.10008.5.1.4.1.1.4").name  # MR Image Storage
    'MR Image'
    >>> iod_for_sop_class("1.2.840.10008.5.1.4.1.1.2.1").name  # Enhanced CT Image
    'Enhanced CT Image'
    >>> iod_for_sop_class("1.2.840.10008.5.1.4.1.1.5") is None  # retired NM Image
    True
    """
    if sop_classes is None:
        sop_classes = load_storage_sop_classes()
    if iod_tables is None:
        iod_tables = load_iod_tables()
    if sop_classes.edition != iod_tables.edition:
        raise StandardTableError(
            "the SOP Class and IOD tables were generated from different editions"
        )
    uid = normalise_uid(sop_class_uid)
    row = next((row for row in sop_classes.rows if row.uid == uid), None)
    if row is None:
        return None
    return iod_tables.iods.get(row.iod_name)
