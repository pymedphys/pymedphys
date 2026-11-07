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

"""A reviewer's clearing of residual findings that held instances for review.

A run's release gate holds a written file for review where the residual
search finds source text in it that nothing explains, under
``residual-text``, or a source person name in standard text that a
selected option keeps, under ``residual-person-name-in-kept-text`` (D-027,
D-042). The run's QC pack lists each finding with an excerpt of the bytes
around it and the SHA-256 of the value that holds it, and the SHA-256 of
each source file. A reviewer who finds that the values holding an
instance's findings are not identifying, such as an Institution Name that
is the institution's own name and only shares a word with a removed
physician's name, clears the instance's findings by its run position in
the pack's attestation (:mod:`~pymedphys._dicom.deidentify.qc_attestation`).

A later run of the same files is given that pack
(:func:`read_residual_review`), and an attestation whose outcome is
rejected is refused. Each finding that would hold a file for review, and
that the pack showed for a cleared instance with the same source file, by
its SHA-256, in a value with the same SHA-256, is then exempted rather than
a reason for review (:func:`~.release_gate.release_condition`). A finding
that the pack did not show, as in a source file changed since the review,
or in a value written otherwise, still holds the file, and a finding that
withholds a file is never cleared.

The clearings are read by digest, never by path or run position, so the
later run may discover the files in another order, or among others, which
have none. Cleared instances with one source file, such as identical
copies, have their shown findings pooled.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import types
from collections.abc import Mapping

from .qc_attestation import Attestation, Outcome, attested_pack, shown_residuals
from .qc_pack import QcPackError
from .residuals import ReviewedFinding

_SHA256 = re.compile(r"[0-9a-f]{64}")
_REFERENCE = re.compile(r"A-[0-9a-f]{32}")


@dataclasses.dataclass(frozen=True, repr=False)
class ResidualReview:
    """The residual findings that a reviewer cleared, by source file.

    Its ``repr`` shows only the pack's reference and the counts.

    Attributes
    ----------
    reference : str
        The reviewed QC pack's opaque reference, ``A-`` and 32 hex digits,
        which the release report records.
    cleared : mapping of bytes to frozenset of ReviewedFinding
        The findings cleared in each source file, by its SHA-256.
    """

    reference: str
    cleared: Mapping[bytes, frozenset[ReviewedFinding]] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("a residual review needs the reviewed pack's reference")
        if not isinstance(self.cleared, Mapping) or not all(
            isinstance(digest, bytes)
            and len(digest) == 32
            and isinstance(findings, frozenset)
            and findings
            and all(isinstance(each, ReviewedFinding) for each in findings)
            for digest, findings in self.cleared.items()
        ):
            raise QcPackError(
                "a residual review gives the cleared findings of source files "
                "by their SHA-256"
            )
        object.__setattr__(self, "cleared", types.MappingProxyType(dict(self.cleared)))

    def __repr__(self) -> str:
        return (
            f"ResidualReview(reference={self.reference!r}, "
            f"files={len(self.cleared)}, "
            f"findings={sum(map(len, self.cleared.values()))})"
        )

    def of(self, digest: bytes) -> frozenset[ReviewedFinding]:
        """Return the findings cleared in the source file of SHA-256 ``digest``."""
        return self.cleared.get(digest, frozenset())


def read_residual_review(pack_directory: os.PathLike | str) -> ResidualReview:
    """Read the residual clearings of an attested QC pack.

    Parameters
    ----------
    pack_directory : path-like
        The directory of an earlier run's QC pack, which a reviewer has
        attested.

    Returns
    -------
    ResidualReview
        Empty of files where the attestation clears no instance's findings.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, or the pack has not been
        attested, or its attestation's outcome is rejected; if either is not
        of its format, or the attestation is for another pack; if the pack
        or a preview changed after it was attested; or if a clearing names
        an instance for which the pack shows no finding, or that it lists
        without its source's SHA-256. The message names no path and no
        value.
    """
    return residual_review_of(*attested_pack(pack_directory))


def residual_review_of(attestation: Attestation, data: bytes) -> ResidualReview:
    """Return the residual clearings of an attestation of a QC pack.

    Parameters
    ----------
    attestation : ~pymedphys._dicom.deidentify.qc_attestation.Attestation
    data : bytes
        The bytes of the pack that ``attestation`` attests, as
        :func:`~pymedphys._dicom.deidentify.qc_attestation.attested_pack`
        returns them with it.

    Returns
    -------
    ResidualReview
        As :func:`read_residual_review` returns it.

    Raises
    ------
    QcPackError
        As :func:`read_residual_review` raises it, other than for reading
        the pack and its attestation.
    """
    if attestation.outcome is not Outcome.ATTESTED:
        raise QcPackError(
            "the QC pack's attestation rejected it, so its clearings release nothing"
        )
    shown = shown_residuals(data)
    digests = _source_digests(data)
    cleared: dict[bytes, set[ReviewedFinding]] = {}
    for position in attestation.cleared_residuals:
        if not shown.get(position) or position not in digests:
            raise QcPackError(
                "a clearing names an instance for which the QC pack shows no "
                "finding, or whose source file's SHA-256 it does not give"
            )
        cleared.setdefault(digests[position], set()).update(shown[position])
    return ResidualReview(
        attestation.reference,
        {digest: frozenset(findings) for digest, findings in cleared.items()},
    )


def _source_digests(data: bytes) -> dict[int, bytes]:
    """Return the SHA-256 of each instance's source file, by run position."""
    malformed = QcPackError("the QC pack is not of its format")
    document = json.loads(data.decode("ascii"))  # attested_pack has parsed it
    instances = document.get("instances")
    if not isinstance(instances, list):
        raise malformed
    digests: dict[int, bytes] = {}
    for instance in instances:
        if not isinstance(instance, dict):
            raise malformed
        position, digest = instance.get("position"), instance.get("source_sha256")
        if isinstance(position, int) and isinstance(digest, str):
            if not _SHA256.fullmatch(digest):
                raise malformed
            digests[position] = bytes.fromhex(digest)
    return digests
