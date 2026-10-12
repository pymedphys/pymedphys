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

"""Keyed patient pseudonyms.

Every preset replaces Patient ID (0010,0020) and Patient's Name (0010,0010)
with values derived from the subject's identity under the key, rather than
emptying them, so subjects stay separate within a collection and, under a
project key, consistent across runs. The values are conspicuously synthetic,
so a research copy is not mistaken for a clinical record, and they do not
contain the source identifier.
"""

from __future__ import annotations

import base64
import dataclasses

from .keys import DeidKey

PATIENT_ID_PREFIX = "DEID-"
FAMILY_NAME = "DEIDENTIFIED"
# 80 bits of the keyed derivation, written as 16 base32 characters. Among a
# million subjects the chance of any two sharing a code is below 1e-12.
CODE_BYTES = 10
# LO values may be padded with spaces (PS3.5 Section 6.2); some writers pad
# with NUL instead.
_PADDING = " \x00"


def _normalised(value: str, what: str) -> str:
    stripped = value.strip(_PADDING)
    if not stripped:
        raise ValueError(f"an empty {what} cannot identify a subject")
    return stripped


@dataclasses.dataclass(frozen=True, repr=False)
class SubjectIdentity:
    """Who a subject is, as de-identification resolves it.

    Build one with :meth:`from_patient_id` or :meth:`curated`. Its ``repr``
    shows only which kind it is, so identifiers do not reach logs.

    Attributes
    ----------
    kind : str
        ``"patient-id"`` or ``"curated"``.
    identifier : str
        The Patient ID or the curator's subject identifier, without padding.
    issuer : str
        The issuer of the Patient ID without padding, or ``""``.
    """

    kind: str
    identifier: str
    issuer: str = ""

    @classmethod
    def from_patient_id(cls, patient_id: str, issuer: str = "") -> SubjectIdentity:
        """Return the identity that a Patient ID and its issuer name.

        The same identifier from another issuer, or from none, is another
        subject. Leading and trailing spaces are not significant.

        Raises
        ------
        ValueError
            If ``patient_id`` is empty once its padding is removed; such
            subjects need a curated identity.
        """
        return cls(
            "patient-id", _normalised(patient_id, "Patient ID"), issuer.strip(_PADDING)
        )

    @classmethod
    def curated(cls, subject_id: str) -> SubjectIdentity:
        """Return a curator-supplied identity, for example after merging records.

        A curated identity is never equal to a Patient ID identity with the
        same text.

        Raises
        ------
        ValueError
            If ``subject_id`` is empty once its padding is removed.
        """
        return cls("curated", _normalised(subject_id, "subject identifier"))

    @property
    def parts(self) -> tuple[str, ...]:
        """The identity's parts, in the order derivations frame them."""
        if self.kind == "curated":
            return (self.kind, self.identifier)
        return (self.kind, self.issuer, self.identifier)

    def __repr__(self) -> str:
        return f"SubjectIdentity(kind={self.kind!r})"


@dataclasses.dataclass(frozen=True)
class PatientPseudonym:
    """The values that replace a subject's Patient ID and Patient's Name.

    Attributes
    ----------
    patient_id : str
        ``"DEID-"`` and the subject's code, 21 characters (LO).
    patients_name : str
        ``"DEIDENTIFIED^"`` and the code as the given name (PN).
    """

    patient_id: str
    patients_name: str


def patient_pseudonym(key: DeidKey, identity: SubjectIdentity) -> PatientPseudonym:
    """Return the pseudonym of the subject with ``identity`` under ``key``.

    The subject's code is the base32 form (RFC 4648) of the first 10 bytes of
    the key's ``"patient"`` derivation of the identity's parts. The same key
    and identity always give the same pseudonym; another key gives an
    unrelated one.

    Examples
    --------
    >>> key = DeidKey(bytes(32))
    >>> pseudonym = patient_pseudonym(key, SubjectIdentity.from_patient_id("123"))
    >>> pseudonym.patient_id.startswith("DEID-"), len(pseudonym.patient_id)
    (True, 21)
    """
    token = key.derive("patient", *identity.parts)
    code = base64.b32encode(token[:CODE_BYTES]).decode("ascii")
    return PatientPseudonym(
        patient_id=f"{PATIENT_ID_PREFIX}{code}",
        patients_name=f"{FAMILY_NAME}^{code}",
    )
