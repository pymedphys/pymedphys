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

"""The attribution that each file drawn from the DICOM Standard carries.

Every table that ``pymedphys dev deid-tables`` generates, and every rule file
curated by hand for one edition of a part of the standard, carries three
fields: its acknowledgement, such as "DICOM PS3.15 2026d, © NEMA", which
names its part and edition; a link to the DICOM Standard; and NEMA's
trademark notice, which also says that NEMA does not endorse, sponsor, or
certify PyMedPhys. Each file's loader rejects a file without them (D-001).

The generator also writes the tables' notice file, :data:`NOTICE_FILE`, which
names each table's attribution, and which the package lists among its
licence files.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping

# The notice file of the generated tables, which the generator writes beside
# them.
NOTICE_FILE = "NOTICE-DICOM.txt"
NOTICE_PATH = pathlib.Path(__file__).resolve().parent / "_standard" / NOTICE_FILE

# The home page of the DICOM Standard.
LINK = "https://www.dicomstandard.org/"

# NEMA's trademark notice, and that NEMA does not endorse PyMedPhys.
NOTICE = (
    "DICOM® is the registered trademark of the National Electrical "
    "Manufacturers Association (NEMA) for its standards publications relating "
    "to digital communications of medical information. NEMA does not endorse, "
    "sponsor, or certify PyMedPhys."
)

# That the tables are extracted automatically, and that the published
# standard prevails over them.
DISCLAIMER = (
    "The tables were extracted automatically from the published DICOM "
    "Standard and may contain errors. The published Standard is authoritative."
)


def acknowledgement(part: str, edition: str) -> str:
    """Return the acknowledgement of a part and edition of the standard.

    Parameters
    ----------
    part : str
        The part, such as ``"PS3.15"``.
    edition : str
        The edition, such as ``"2026d"``.

    Returns
    -------
    str
        Such as ``"DICOM PS3.15 2026d, © NEMA"``.
    """
    return f"DICOM {part} {edition}, © NEMA"


def fields(part: str, edition: str) -> dict[str, str]:
    """Return the attribution fields of a file drawn from a part and edition.

    Returns
    -------
    dict of str to str
        The ``acknowledgement``, ``link``, and ``notice``, in that order.
    """
    return {
        "acknowledgement": acknowledgement(part, edition),
        "link": LINK,
        "notice": NOTICE,
    }


def missing(document: Mapping[str, object]) -> str | None:
    """Return what a document lacks of the link and notice, or None.

    The acknowledgement names the part and edition, which each loader checks
    against its own, so it is not checked here.

    Returns
    -------
    str or None
        ``"the link to the DICOM Standard"`` or ``"NEMA's trademark
        notice"`` for the first that is missing or altered, or None if both
        are present.
    """
    if document.get("link") != LINK:
        return "the link to the DICOM Standard"
    if document.get("notice") != NOTICE:
        return "NEMA's trademark notice"
    return None
