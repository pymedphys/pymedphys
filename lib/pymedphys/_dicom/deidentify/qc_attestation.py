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

"""A reviewer's attestation of a QC pack, and its record for the release report.

A reviewer who has worked through a run's QC pack
(:mod:`~pymedphys._dicom.deidentify.qc_pack`) attests to it with
:func:`attest`, which writes :data:`ATTESTATION_FILE` into the pack's
directory, labelled with its format, :data:`FORMAT`. The attestation names
the reviewer and when they attested, states whether they reviewed what D-017
requires (every distinct retained string, every series, and every instance in
high-risk categories), and gives the outcome. It is bound to the pack by the
SHA-256 of the pack's file, which records the SHA-256 of each of its image
previews, so a pack or preview changed after it was attested is detected. A pack is attested once: the file is never overwritten.

The attestation is confidential with the pack, since it names the reviewer
and sits beside the review material. The release report records only
:func:`attestation_record`: the pack's opaque reference and the outcome
(D-016). An outcome of attested needs every review that D-017 requires; a
reviewer who could not complete them records a rejection.

An attestation covers human review of the pack. It is one of the three gates
of a ``public-release`` run, with statistical disclosure control and pixel and
face review (D-017), and passing it does not pass the others.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import os
import re
import stat
from pathlib import Path

from . import qc_pack, qc_store
from .qc_pack import QcPackError

# The format of the attestation document. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-qc-attestation/1"
ATTESTATION_FILE = "attestation.json"

_DIGEST = re.compile(r"[0-9a-f]{64}")
_REFERENCE = re.compile(r"A-[0-9a-f]{32}")
_PREVIEW_FILE = re.compile(
    re.escape(qc_pack.PREVIEW_DIRECTORY) + "/" + qc_pack.PREVIEW_NAME.pattern
)


class Outcome(enum.Enum):
    """The outcome of human QC review, as the release report records it."""

    ATTESTED = "attested"  # the reviewer found the output fit for release
    REJECTED = "rejected"  # the reviewer did not
    NOT_ATTESTED = "not-attested"  # no reviewer has attested to the pack


@dataclasses.dataclass(frozen=True)
class Coverage:
    """Whether the reviewer reviewed what D-017 requires.

    Attributes
    ----------
    retained_strings : bool
        Every distinct retained string.
    series : bool
        Every series, by maximum intensity projection or cine strip.
    high_risk_instances : bool
        Every instance in high-risk categories.
    """

    retained_strings: bool
    series: bool
    high_risk_instances: bool

    def __post_init__(self) -> None:
        if not all(isinstance(value, bool) for value in dataclasses.astuple(self)):
            raise QcPackError("each part of the coverage must be True or False")

    @property
    def complete(self) -> bool:
        """Whether every review that D-017 requires was done."""
        return all(dataclasses.astuple(self))


@dataclasses.dataclass(frozen=True, repr=False)
class Attestation:
    """A reviewer's attestation of one QC pack.

    Its ``repr`` leaves out the reviewer.

    Attributes
    ----------
    reference : str
        The pack's opaque reference.
    pack_digest : str
        The SHA-256 of the pack's file, in lower-case hexadecimal.
    outcome : Outcome
        :attr:`Outcome.ATTESTED` or :attr:`Outcome.REJECTED`.
    coverage : Coverage
    reviewer : str
        Who attested, as they name themselves.
    attested_at : datetime.datetime
        When, in UTC.
    """

    reference: str
    pack_digest: str
    outcome: Outcome
    coverage: Coverage
    reviewer: str
    attested_at: datetime.datetime

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("an attestation needs the pack's reference")
        if not isinstance(self.pack_digest, str) or not _DIGEST.fullmatch(
            self.pack_digest
        ):
            raise QcPackError("an attestation needs the SHA-256 of the pack")
        if self.outcome not in (Outcome.ATTESTED, Outcome.REJECTED):
            raise QcPackError("an attestation's outcome is attested or rejected")
        if not isinstance(self.coverage, Coverage):
            raise QcPackError("an attestation needs its Coverage")
        if self.outcome is Outcome.ATTESTED and not self.coverage.complete:
            raise QcPackError(
                "an outcome of attested needs every review that D-017 requires"
            )
        if not isinstance(self.reviewer, str) or not self.reviewer.strip():
            raise QcPackError("an attestation needs its reviewer")
        if not isinstance(
            self.attested_at, datetime.datetime
        ) or self.attested_at.utcoffset() != datetime.timedelta(0):
            raise QcPackError("an attestation needs its time in UTC")

    def __repr__(self) -> str:
        return (
            f"Attestation(reference={self.reference!r}, outcome={self.outcome.value!r})"
        )


@dataclasses.dataclass(frozen=True)
class AttestationRecord:
    """What the release report records of human QC review (D-016).

    Attributes
    ----------
    reference : str
        The QC pack's opaque reference, ``A-`` and 32 hex digits.
    outcome : Outcome
    """

    reference: str
    outcome: Outcome

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("an attestation record needs the pack's reference")
        if not isinstance(self.outcome, Outcome):
            raise QcPackError("an attestation record needs an Outcome")


def attestation_document(attestation: Attestation) -> dict:
    """Return an attestation as JSON values, labelled with :data:`FORMAT`."""
    if not isinstance(attestation, Attestation):
        raise TypeError("attestation must be an Attestation")
    return {
        "format": FORMAT,
        "reference": attestation.reference,
        "pack_digest": attestation.pack_digest,
        "outcome": attestation.outcome.value,
        "coverage": dataclasses.asdict(attestation.coverage),
        "reviewer": attestation.reviewer,
        "attested_at": attestation.attested_at.isoformat(),
    }


def attest(
    pack_directory: os.PathLike | str,
    *,
    reviewer: str,
    outcome: Outcome,
    coverage: Coverage,
    attested_at: datetime.datetime | None = None,
) -> Attestation:
    """Attest to a QC pack, and write the attestation beside it.

    Parameters
    ----------
    pack_directory : path-like
        The directory that :func:`~.qc_store.write_qc_pack` wrote.
    reviewer : str
        Who attests, as they name themselves.
    outcome : Outcome
        :attr:`Outcome.ATTESTED` or :attr:`Outcome.REJECTED`.
    coverage : Coverage
        What the reviewer reviewed; complete for an outcome of attested.
    attested_at : datetime.datetime, optional
        When, in UTC; now if not given.

    Returns
    -------
    Attestation

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, the pack is not of its format, a
        preview that it lists is missing or changed, or it has already been
        attested; or for any reason that
        :class:`Attestation` gives.
    """
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    reference = _reference_of(data)
    if not _previews_intact(directory, data):
        raise QcPackError("a preview of the QC pack is missing or changed")
    attestation = Attestation(
        reference=reference,
        pack_digest=hashlib.sha256(data).hexdigest(),
        outcome=outcome,
        coverage=coverage,
        reviewer=reviewer,
        attested_at=(
            datetime.datetime.now(datetime.timezone.utc)
            if attested_at is None
            else attested_at
        ),
    )
    text = json.dumps(attestation_document(attestation), indent=2, ensure_ascii=True)
    try:
        qc_store.write_new(directory / ATTESTATION_FILE, text + "\n")
    except FileExistsError:
        raise QcPackError("the QC pack has already been attested") from None
    except OSError as error:
        raise qc_store.os_error("the attestation could not be written", error) from None
    return attestation


def attestation_record(pack_directory: os.PathLike | str) -> AttestationRecord:
    """Return the release report's record of a QC pack's attestation.

    Parameters
    ----------
    pack_directory : path-like
        The directory that :func:`~.qc_store.write_qc_pack` wrote.

    Returns
    -------
    AttestationRecord
        The pack's reference, with :attr:`Outcome.NOT_ATTESTED` if no
        attestation has been written, and otherwise its outcome.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack; if the attestation is not of its
        format or is for another pack; or if the pack, or a preview that it
        lists, changed after it was attested.
    """
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    reference = _reference_of(data)
    content = _read(directory / ATTESTATION_FILE, "the attestation")
    if content is None:
        return AttestationRecord(reference, Outcome.NOT_ATTESTED)
    attestation = _attestation_from(content)
    if attestation.reference != reference:
        raise QcPackError("the attestation is for another QC pack")
    if attestation.pack_digest != hashlib.sha256(
        data
    ).hexdigest() or not _previews_intact(directory, data):
        raise QcPackError("the QC pack changed after it was attested")
    return AttestationRecord(reference, attestation.outcome)


def _attestation_from(content: bytes) -> Attestation:
    """Rebuild a written attestation, so that it meets every check again."""
    try:
        document = json.loads(content.decode("ascii"))
        if isinstance(document, dict) and document.get("format") == FORMAT:
            coverage = document["coverage"]
            if isinstance(coverage, dict):
                return Attestation(
                    reference=document["reference"],
                    pack_digest=document["pack_digest"],
                    outcome=Outcome(document["outcome"]),
                    coverage=Coverage(**coverage),
                    reviewer=document["reviewer"],
                    attested_at=datetime.datetime.fromisoformat(
                        document["attested_at"]
                    ),
                )
    # UnicodeError and QcPackError are ValueErrors; TypeError covers wrong
    # types and Coverage's unknown or missing fields.
    except (ValueError, KeyError, TypeError):
        pass
    raise QcPackError("the attestation is not of its format")


def _pack_bytes(directory: Path) -> bytes:
    marker = qc_store.path_status(
        directory / qc_store.MARKER_FILE, "the QC pack could not be read"
    )
    if marker is None or not stat.S_ISREG(marker.st_mode):
        raise QcPackError("the directory holds no QC pack")
    data = _read(directory / qc_store.PACK_FILE, "the QC pack")
    if data is None:
        raise QcPackError("the directory holds no QC pack")
    return data


def _previews_intact(directory: Path, data: bytes) -> bool:
    """Whether every preview that the pack lists has the SHA-256 it records."""
    document = json.loads(data.decode("ascii"))  # _reference_of has parsed it
    previews = document.get("previews", [])
    if not isinstance(previews, list):
        return False
    for preview in previews:
        name = preview.get("file") if isinstance(preview, dict) else None
        digest = preview.get("sha256") if isinstance(preview, dict) else None
        if (
            not isinstance(name, str)
            or not _PREVIEW_FILE.fullmatch(name)
            or not isinstance(digest, str)
        ):
            return False
        content = _read(directory / name, "a preview of the QC pack")
        if content is None or hashlib.sha256(content).hexdigest() != digest:
            return False
    return True


def _read(path: Path, what: str) -> bytes | None:
    """Return a file's bytes, or None if it does not exist.

    Any other failure raises, naming ``what`` and the operating system's
    reason, but never the path.
    """
    try:
        return path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        raise qc_store.os_error(f"{what} could not be read", error) from None


def _reference_of(data: bytes) -> str:
    try:
        document = json.loads(data.decode("ascii"))
    except ValueError:  # UnicodeError and JSONDecodeError are ValueErrors
        document = None
    reference = document.get("reference") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("format") != qc_pack.FORMAT
        or not isinstance(reference, str)
        or not _REFERENCE.fullmatch(reference)
    ):
        raise QcPackError("the QC pack is not of its format")
    return reference
