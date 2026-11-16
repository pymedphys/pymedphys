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

"""A reviewer's redaction verdicts in progress, for the attestation (D-059).

The redaction review app
(:mod:`~pymedphys._dicom.deidentify.redaction_review_app`) saves the
reviewer's work on a QC pack's cleaned instances, as they go, to
:data:`VERDICTS_FILE` in the pack's directory, labelled with its format,
:data:`FORMAT`, so that a review can stop and resume. It is bound to the
pack by the pack's opaque reference and the SHA-256 of its file. Each entry
is an instance, by run position, with the pack's regions that the reviewer
dropped, the regions that they drew, the frames that they were shown, and
their verdict, or none while they are still working on it.

The attestation command reads the file
(:func:`read_redaction_verdicts`) and gives each entry with a verdict to
:func:`~.qc_attestation.attest`, which checks it against the pack; an entry
without one gives no verdict, so its instance stays held, as one that the
reviewer never opened does. The run that applies the verdicts never reads
this file, only the attestation.

The file is confidential with the pack, though it names no one and holds no
value: it lies inside the pack's directory, which a release refuses (D-016).
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path

from . import qc_store
from .qc_attestation import Redaction, RedactionVerdict
from .qc_pack import QcPackError
from .text_detection import TextBox

# The format of the verdicts file. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-redaction-verdicts/1"
VERDICTS_FILE = "redaction-verdicts.json"

_REFERENCE = re.compile(r"A-[0-9a-f]{32}")
_DIGEST = re.compile(r"[0-9a-f]{64}")

Regions = tuple[tuple[int, tuple[TextBox, ...]], ...]


@dataclasses.dataclass(frozen=True)
class Draft:
    """The reviewer's work on one cleaned instance.

    Attributes
    ----------
    position : int
        The instance's run position.
    redaction : Redaction or None
        The verdict, or None while the reviewer is still working on it.
    drawn, dropped : tuple of (int, tuple of TextBox)
        As :class:`~.qc_attestation.RedactionVerdict` has ``regions`` and
        ``dropped``, kept while the instance has no verdict, or is accepted
        or rejected, so that the reviewer's work is not lost if they change
        the verdict back; only a revised verdict takes them.
    seen : tuple of int
        The frames that the reviewer was shown, sorted, each once.
    """

    position: int
    redaction: Redaction | None = None
    drawn: Regions = ()
    dropped: Regions = ()
    seen: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.redaction is not None and not isinstance(self.redaction, Redaction):
            raise QcPackError("a draft's verdict is a Redaction or None")
        # A verdict that holds every field checks each of them.
        if self.drawn or self.dropped:
            RedactionVerdict(
                self.position, Redaction.REVISED, self.drawn, self.dropped, self.seen
            )
        else:
            RedactionVerdict(self.position, Redaction.ACCEPTED, seen=self.seen)

    def verdict(self) -> RedactionVerdict | None:
        """Return the verdict that the draft gives, or None.

        A revised verdict that neither draws nor drops a region is refused,
        as :class:`~.qc_attestation.RedactionVerdict` refuses it.
        """
        if self.redaction is None:
            return None
        if self.redaction is Redaction.REVISED:
            return RedactionVerdict(
                self.position, self.redaction, self.drawn, self.dropped, self.seen
            )
        return RedactionVerdict(self.position, self.redaction, seen=self.seen)


@dataclasses.dataclass(frozen=True)
class Verdicts:
    """A pack's drafts, bound to the pack.

    Attributes
    ----------
    reference : str
        The pack's opaque reference.
    pack_digest : str
        The SHA-256 of the pack's file, in lower-case hexadecimal.
    drafts : tuple of Draft
        By run position, each once.
    """

    reference: str
    pack_digest: str
    drafts: tuple[Draft, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("redaction verdicts need the pack's reference")
        if not isinstance(self.pack_digest, str) or not _DIGEST.fullmatch(
            self.pack_digest
        ):
            raise QcPackError("redaction verdicts need the SHA-256 of the pack")
        if not isinstance(self.drafts, tuple) or not all(
            isinstance(draft, Draft) for draft in self.drafts
        ):
            raise QcPackError("redaction verdicts' drafts must be Drafts")
        positions = [draft.position for draft in self.drafts]
        if positions != sorted(set(positions)):
            raise QcPackError(
                "redaction verdicts give each instance at most one draft, in order"
            )

    def verdicts(self) -> tuple[RedactionVerdict, ...]:
        """Return the verdicts that the drafts give, by run position."""
        return tuple(
            verdict
            for verdict in (draft.verdict() for draft in self.drafts)
            if verdict is not None
        )


def verdicts_document(verdicts: Verdicts) -> dict:
    """Return the drafts as JSON values, labelled with :data:`FORMAT`."""
    if not isinstance(verdicts, Verdicts):
        raise TypeError("verdicts must be Verdicts")
    return {
        "format": FORMAT,
        "reference": verdicts.reference,
        "pack_digest": verdicts.pack_digest,
        "drafts": [
            {
                "position": draft.position,
                "redaction": None if draft.redaction is None else draft.redaction.value,
                "drawn": _regions_document(draft.drawn),
                "dropped": _regions_document(draft.dropped),
                "seen": list(draft.seen),
            }
            for draft in verdicts.drafts
        ],
    }


def verdicts_from(document: object) -> Verdicts:
    """Rebuild drafts from JSON values, so that they meet every check again.

    Raises
    ------
    QcPackError
        If the document is not of :data:`FORMAT`. The message quotes nothing
        from it.
    """
    try:
        if isinstance(document, dict) and document.get("format") == FORMAT:
            if set(document) != {"format", "reference", "pack_digest", "drafts"}:
                raise QcPackError("the redaction verdicts are not of their format")
            drafts = document["drafts"]
            if isinstance(drafts, list):
                return Verdicts(
                    document["reference"],
                    document["pack_digest"],
                    tuple(map(_draft_from, drafts)),
                )
    except (ValueError, KeyError, TypeError):
        pass
    raise QcPackError("the redaction verdicts are not of their format")


def _draft_from(entry: dict) -> Draft:
    if set(entry) != {"position", "redaction", "drawn", "dropped", "seen"}:
        raise QcPackError("the redaction verdicts are not of their format")
    redaction = entry["redaction"]
    seen = entry["seen"]
    if not isinstance(seen, list):
        raise QcPackError("the redaction verdicts are not of their format")
    return Draft(
        entry["position"],
        None if redaction is None else Redaction(redaction),
        _regions_from(entry["drawn"]),
        _regions_from(entry["dropped"]),
        tuple(seen),
    )


def _regions_document(regions: Regions) -> list[dict]:
    return [
        {
            "frame": index,
            "boxes": [[box.top, box.left, box.bottom, box.right] for box in boxes],
        }
        for index, boxes in regions
    ]


def _regions_from(regions: object) -> Regions:
    if not isinstance(regions, list):
        raise QcPackError("the redaction verdicts are not of their format")
    built = []
    for entry in regions:
        if not isinstance(entry, dict) or set(entry) != {"frame", "boxes"}:
            raise QcPackError("the redaction verdicts are not of their format")
        boxes = entry["boxes"]
        if not isinstance(boxes, list) or not all(
            isinstance(box, list) and len(box) == 4 for box in boxes
        ):
            raise QcPackError("the redaction verdicts are not of their format")
        built.append((entry["frame"], tuple(TextBox(*box) for box in boxes)))
    return tuple(built)


def regions_of(boxes: Iterable[tuple[int, TextBox]]) -> Regions:
    """Return boxes, each given with its frame index, laid out by frame, in
    order, each frame's boxes sorted and distinct."""
    by_frame: dict[int, set[TextBox]] = {}
    for index, box in boxes:
        by_frame.setdefault(index, set()).add(box)
    return tuple((index, tuple(sorted(by_frame[index]))) for index in sorted(by_frame))


def read_redaction_verdicts(
    path: os.PathLike | str, *, reference: str, pack_digest: str
) -> Verdicts:
    """Read a verdicts file, and check that it is bound to the given pack.

    Parameters
    ----------
    path : path-like
    reference, pack_digest : str
        The pack's opaque reference and the SHA-256 of its file.

    Raises
    ------
    QcPackError
        If the file cannot be read, is not of :data:`FORMAT`, or is bound to
        another pack, or to this pack as it was before it changed. The
        message names no path.
    """
    try:
        content = Path(path).read_bytes()
    except OSError as error:
        raise qc_store.os_error(
            "the redaction verdicts could not be read", error
        ) from None
    try:
        document = json.loads(content.decode("ascii"))
    except ValueError:
        raise QcPackError("the redaction verdicts are not of their format") from None
    verdicts = verdicts_from(document)
    if verdicts.reference != reference or verdicts.pack_digest != pack_digest:
        raise QcPackError(
            "the redaction verdicts are for another QC pack, or for this pack "
            "before it changed"
        )
    return verdicts


def save_redaction_verdicts(directory: os.PathLike | str, verdicts: Verdicts) -> None:
    """Write the drafts to :data:`VERDICTS_FILE` in the pack's directory,
    replacing any earlier copy at once, so that a reader never sees a part
    of one, with mode 0o600 on POSIX.

    Raises
    ------
    QcPackError
        If the file cannot be written. The message names no path.
    """
    text = json.dumps(verdicts_document(verdicts), indent=2, ensure_ascii=True)
    target = Path(directory) / VERDICTS_FILE
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".redaction-verdicts-", suffix=".tmp", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write((text + "\n").encode("ascii"))
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    except OSError as error:
        raise qc_store.os_error(
            "the redaction verdicts could not be written", error
        ) from None
