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

"""The LOINC codes that the Clean Structured Content Option looks up, with their names.

Table E.3.4-1 of PS3.15 codes seven of its concept names in LOINC, and three
supplementary rows code patient height, weight, and body surface area in
LOINC as PS3.16's templates do (:mod:`.supplementary_concepts`). PyMedPhys
includes those LOINC codes under LOINC's licence, whose notice
``_loinc/LICENSE-LOINC.txt`` holds, and which has each code that a product
includes carry one of LOINC's own names for it. ``_loinc/loinc_terms.toml``,
curated by hand from one LOINC release, gives each code with its long common
name and status, unchanged, under the LOINC Table's own field names (D-001).

The engine looks up concepts by their codes alone, so nothing reads the names
when de-identifying. The table generator refuses a LOINC row of Table E.3.4-1
whose code the file does not give, and a test checks that the file gives
exactly the codes of the generated table and the supplementary rows.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import re
import types
from collections.abc import Mapping

from pymedphys._imports import tomlkit

SCHEMA = "pymedphys-deid-loinc-terms/1"
LOINC_DIR = pathlib.Path(__file__).resolve().parent / "_loinc"
LOINC_TERMS_PATH = LOINC_DIR / "loinc_terms.toml"
NOTICE_PATH = LOINC_DIR / "LICENSE-LOINC.txt"
# The notice that LOINC's licence (Section 10.1) has a product that includes
# LOINC content carry.
NOTICE = (
    "This material contains content from LOINC (http://loinc.org). LOINC is "
    "copyright © Regenstrief Institute, Inc. and the Logical Observation "
    "Identifiers Names and Codes (LOINC) Committee and is available at no "
    "cost under the license at http://loinc.org/license. LOINC® is a "
    "registered United States trademark of Regenstrief Institute, Inc."
)
# The values of the LOINC Table's STATUS field.
STATUSES = frozenset({"ACTIVE", "TRIAL", "DISCOURAGED", "DEPRECATED"})
# A LOINC code: up to seven digits, a hyphen, and a check digit.
_LOINC_NUM = re.compile(r"[1-9][0-9]{0,6}-[0-9]")
_VERSION = re.compile(r"[0-9]+\.[0-9]+")
_FIELDS = frozenset({"LOINC_NUM", "LONG_COMMON_NAME", "STATUS"})
# LONG_COMMON_NAME holds at most 255 characters.
_NAME_MAX_LENGTH = 255


class LoincTermsError(ValueError):
    """A LOINC terms file that cannot be used."""


@dataclasses.dataclass(frozen=True)
class LoincTerm:
    """One LOINC code, with the fields of the LOINC Table that PyMedPhys keeps.

    Attributes
    ----------
    loinc_num : str
        The code, from the LOINC_NUM field, such as ``"29463-7"``.
    long_common_name : str
        From the LONG_COMMON_NAME field, such as ``"Body weight"``.
    status : str
        From the STATUS field, one of :data:`STATUSES`.
    """

    loinc_num: str
    long_common_name: str
    status: str


@dataclasses.dataclass(frozen=True)
class LoincTerms:
    """The LOINC codes that PyMedPhys includes.

    Attributes
    ----------
    loinc_version : str
        The LOINC release that the names and statuses come from, such as
        ``"2.83"``.
    terms : Mapping of str to LoincTerm
        By code, in the file's order. Read-only.
    """

    loinc_version: str
    terms: Mapping[str, LoincTerm]


def is_loinc_num(value: object) -> bool:
    """Return whether ``value`` is a LOINC code with a valid check digit.

    LOINC's check digit is the Luhn (mod 10) check digit of the digits
    before the hyphen.

    Examples
    --------
    >>> is_loinc_num("29463-7")
    True
    >>> is_loinc_num("29463-6")
    False
    """
    if not isinstance(value, str) or not _LOINC_NUM.fullmatch(value):
        return False
    digits, check = value.split("-")
    total = 0
    for position, digit in enumerate(reversed(digits)):
        doubled = int(digit) * (2 if position % 2 == 0 else 1)
        total += doubled - 9 if doubled > 9 else doubled
    return (10 - total % 10) % 10 == int(check)


def _is_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= _NAME_MAX_LENGTH
        and value == value.strip()
        and value.isprintable()
    )


def _term_problem(entry: object) -> str | None:
    """Return what is wrong with a term, or None if it is valid."""
    if not isinstance(entry, dict) or entry.keys() != _FIELDS:
        return (
            "does not have exactly the fields LOINC_NUM, LONG_COMMON_NAME, and STATUS"
        )
    if not is_loinc_num(entry["LOINC_NUM"]):
        return "does not have a LOINC code with a valid check digit"
    if not _is_text(entry["LONG_COMMON_NAME"]):
        return "does not have a long common name of at most 255 characters"
    if not isinstance(entry["STATUS"], str) or entry["STATUS"] not in STATUSES:
        return f"does not have a status of {', '.join(sorted(STATUSES))}"
    return None


def load_loinc_terms(path: pathlib.Path | None = None) -> LoincTerms:
    """Load the LOINC codes that PyMedPhys includes, with their names.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The terms file. Defaults to the one shipped with PyMedPhys.

    Raises
    ------
    LoincTermsError
        If the file cannot be read; has another schema; does not give a
        LOINC version such as ``"2.83"``; does not give its terms as a
        non-empty array of tables; has a term without exactly the fields
        LOINC_NUM, LONG_COMMON_NAME, and STATUS, with a code whose check
        digit is valid, a name of at most 255 printable characters without
        leading or trailing spaces, and a status in :data:`STATUSES`; or
        repeats a code.
    """
    return _load((path or LOINC_TERMS_PATH).resolve())


@functools.lru_cache(maxsize=None)
def _load(path: pathlib.Path) -> LoincTerms:
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except (OSError, ValueError, tomlkit.exceptions.TOMLKitError) as error:
        raise LoincTermsError(f"{path.name} could not be read") from error
    if document.get("schema") != SCHEMA:
        raise LoincTermsError(f"{path.name} is not a {SCHEMA} file (schema)")
    version = document.get("loinc_version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise LoincTermsError(f"{path.name} does not give a LOINC version")
    entries = document.get("term")
    if not isinstance(entries, list) or not entries:
        raise LoincTermsError(f"{path.name} terms are not an array of tables")
    terms: dict[str, LoincTerm] = {}
    for number, entry in enumerate(entries, start=1):
        problem = _term_problem(entry)
        if problem:
            raise LoincTermsError(f"{path.name} term {number} {problem}")
        if entry["LOINC_NUM"] in terms:
            raise LoincTermsError(
                f"{path.name} term {number} repeats {entry['LOINC_NUM']}"
            )
        terms[entry["LOINC_NUM"]] = LoincTerm(
            loinc_num=entry["LOINC_NUM"],
            long_common_name=entry["LONG_COMMON_NAME"],
            status=entry["STATUS"],
        )
    return LoincTerms(loinc_version=version, terms=types.MappingProxyType(terms))
