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

"""Record a reviewed region rule for Clean Pixel Data from an attested QC pack.

Run as ``python -m pymedphys._dicom.deidentify.pixel_region_rules_command
STORE PACK POSITION --region TOP LEFT BOTTOM RIGHT``, with ``--region``
repeatable. It is not registered with the ``pymedphys`` command: nothing
de-identification related joins the public command line before the first
supported release.

A first run under the Clean Pixel Data Option holds each image that it
cleans for review, and its QC pack lists the image's regions by frame and
previews every frame. A reviewer who sees text that the image's equipment
burns in at a fixed place, such as a header band, accepts the image's
regions, or revises them with a region of their own over the text, and
attests the pack (:mod:`.attestation_command`). This command then records
the regions given with ``--region`` as the rule for the image's kind in the
custodian's store (:mod:`.pixel_region_rules`, D-037), so that later runs
black them out in every frame of every image of that kind, beside the
regions that the text finder finds.

``PACK`` is the directory of the attested QC pack, and ``POSITION`` the
image's run position in it. Each region is given in pixels from the frame's
top left corner, with the bottom row and right column excluded, as the pack
writes it, and must be one that the reviewer approved for the image: a
region that the pack lists in one of its frames, for an accepted verdict,
or that or one that the verdict adds, for a revised one. A rule therefore
holds only regions that a reviewer has seen on a preview, and a region
misread from the pack, such as one with its coordinates transposed, is
refused rather than recorded (D-048).

The rule's key, the image's SOP Class UID, Manufacturer, Manufacturer's
Model Name, Rows, and Columns, is read from the image's source file, which
the pack names, or from a copy of it given with ``--source``; either must
have the SHA-256 that the pack records for it, so the key is that of the
file that the reviewer saw. A key that the store already holds with other
regions is refused, unless ``--replace`` makes the given regions the
rule's, or ``--add`` adds them to the rule's own.

The store is created at ``STORE`` on first use, readable only by its owner,
as :meth:`~.pixel_region_rules.PixelRegionRules.save` writes it, and never
inside the PyMedPhys configuration directory, the QC pack, or a directory
given with ``--protect``, such as a run's source and release directories.

Recording is all or nothing: the store is written only once the pack, its
attestation, the verdict, each region, and the source file have been
checked. The store holds Manufacturer and Manufacturer's Model Name
verbatim, and the pack holds source paths, so neither the summary nor any
message quotes a value or a path; the summary gives the pack's opaque
reference, the run position, what became of the rule, the rule's regions,
and how many rules the store holds.

Exit statuses:

- :data:`EXIT_RECORDED`, 0: the rule was recorded, or the store already
  held it;
- :data:`EXIT_NOT_RECORDED`, 1: nothing was recorded, and the store is as it
  was;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, and the message
  quotes none of them.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import json
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

from pymedphys._imports import pydicom

from . import command
from .command import _Parser, _print
from .pixel_region_rules import PixelRegionRules, PixelRegionRulesError, key_of
from .qc_attestation import attested_pack, previewed_redactions
from .qc_pack import QcPackError
from .redaction_review import redaction_review_of
from .source import SourceRefused, read_source
from .text_detection import TextBox

EXIT_RECORDED = 0
EXIT_NOT_RECORDED = 1
EXIT_USAGE = command.EXIT_USAGE


class Existing(enum.Enum):
    """What to do where the store already holds other regions for the key."""

    REFUSE = "refuse"
    REPLACE = "replace"
    ADD = "add"


class Change(enum.Enum):
    """What became of the rule for the image's kind."""

    NEW = "new"
    REPLACED = "replaced"
    ADDED = "added to"
    UNCHANGED = "unchanged"


@dataclasses.dataclass(frozen=True)
class Recorded:
    """What :func:`record_rule` recorded, without a value or a path.

    Attributes
    ----------
    created : bool
        Whether the store was started by this call.
    reference : str
        The attested QC pack's opaque reference.
    position : int
        The image's run position in the pack.
    change : Change
    regions : tuple of TextBox
        The rule's regions afterwards, sorted, each once.
    rules : int
        How many rules the store holds afterwards.
    """

    created: bool
    reference: str
    position: int
    change: Change
    regions: tuple[TextBox, ...]
    rules: int

    def summary_lines(self) -> list[str]:
        """Return the summary that the command prints."""
        lines = ["started a new region rules store"] if self.created else []
        lines += [
            f"QC pack: {self.reference}",
            f"instance: {self.position}",
            f"rule: {self.change.value}",
            f"regions in the rule: {len(self.regions)}",
            *(
                f"  [{box.top}, {box.left}, {box.bottom}, {box.right}]"
                for box in self.regions
            ),
            f"rules in the store: {self.rules}",
        ]
        return lines


def record_rule(
    store_path: str | os.PathLike,
    pack_directory: str | os.PathLike,
    position: int,
    regions: tuple[TextBox, ...],
    *,
    source: str | os.PathLike | None = None,
    existing: Existing = Existing.REFUSE,
    protected_dirs: Iterable[str | os.PathLike] = (),
) -> Recorded:
    """Record reviewed regions of an image as the rule for its kind.

    Parameters
    ----------
    store_path : str or os.PathLike
        The custodian's store, which is started if it does not exist.
    pack_directory : str or os.PathLike
        The directory of an attested QC pack of a run under the Clean Pixel
        Data Option.
    position : int
        The image's run position in the pack.
    regions : tuple of TextBox
        The regions to record, each one that the reviewer approved for the
        image in one of its frames, as the module describes.
    source : str or os.PathLike, optional
        A copy of the image's source file, in place of the file that the
        pack names.
    existing : Existing, optional
        What to do where the store holds other regions for the image's
        kind: refuse, the default, replace them, or add to them.
    protected_dirs : iterable of str or os.PathLike, optional
        Directories the store must not be inside, as for
        :meth:`~.pixel_region_rules.PixelRegionRules.open`, beside the QC
        pack, which is always protected.

    Returns
    -------
    Recorded

    Raises
    ------
    PixelRegionRulesError
        If ``regions`` is not a tuple of at least one TextBox, or
        ``position`` not a run position; if the store cannot be kept at
        ``store_path``, or cannot be read or written; if the pack has not
        been attested, its attestation rejected it, or either cannot be
        read or changed after the attestation; if the pack does not list the
        image as cleaned and previewed, with its source's SHA-256; if no
        verdict accepts or revises the image, or an identical copy of it; if
        a region is not one that the verdict approved; if the source file
        cannot be read as DICOM or has another SHA-256 than the pack's; if
        the image has no key; or if the store holds other regions for the
        key and ``existing`` is :attr:`Existing.REFUSE`. The store is then
        as it was, and the message quotes no value or path.
    """
    if not isinstance(existing, Existing):
        raise TypeError("existing must be an Existing")
    if not (
        isinstance(regions, tuple)
        and regions
        and all(isinstance(box, TextBox) for box in regions)
    ):
        raise PixelRegionRulesError("a rule needs a tuple of at least one TextBox")
    if not isinstance(position, int) or isinstance(position, bool) or position < 0:
        raise PixelRegionRulesError("the run position must be a whole number from 0")
    created = not os.path.lexists(store_path)
    rules = PixelRegionRules.open(
        store_path, protected_dirs=[*protected_dirs, pack_directory]
    )
    try:
        attestation, data = attested_pack(pack_directory)
        review = redaction_review_of(attestation, data)
        shapes = previewed_redactions(data)
    except QcPackError as error:
        raise PixelRegionRulesError(str(error)) from None
    named, digest = _instance(data, position)
    if position not in shapes or digest is None:
        raise PixelRegionRulesError(
            "the QC pack does not list the instance at that run position as "
            "cleaned and previewed, with its source file's SHA-256"
        )
    if digest in review.rejected:
        raise PixelRegionRulesError("the reviewer rejected the instance")
    approved = review.approved.get(digest)
    if approved is None:
        raise PixelRegionRulesError(
            "the attestation gives the instance no verdict that accepts or "
            "revises its regions"
        )
    seen = {box for _, boxes in approved for box in boxes}
    for number, box in enumerate(regions, start=1):
        if box not in seen:
            raise PixelRegionRulesError(
                f"region {number} is not among the regions that the reviewer "
                "approved for the instance in any of its frames"
            )
    key = key_of(_source_dataset(named if source is None else source, digest))
    if key is None:
        raise PixelRegionRulesError(
            "the instance's SOP Class UID, Manufacturer, Manufacturer's Model "
            "Name, Rows, or Columns is absent or not one value, so no rule can "
            "match it"
        )
    shape = shapes[position]
    if (key.rows, key.columns) != (shape.rows, shape.columns):
        raise PixelRegionRulesError(
            "the source file's Rows and Columns differ from those that the QC "
            "pack records for the instance"
        )
    held = set(rules.get(key))
    given = set(regions)
    if not held:
        change, recorded = Change.NEW, given
    elif held == given or (existing is Existing.ADD and given <= held):
        change, recorded = Change.UNCHANGED, held
    elif existing is Existing.REPLACE:
        change, recorded = Change.REPLACED, given
    elif existing is Existing.ADD:
        change, recorded = Change.ADDED, held | given
    else:
        raise PixelRegionRulesError(
            "the store already holds other regions for the instance's kind; "
            "give --replace to replace them, or --add to add to them"
        )
    rules.record(key, recorded, replace=True)
    try:
        rules.save()
    except OSError:
        raise PixelRegionRulesError(
            "the region rules store could not be written; its path is not "
            "shown because it can name a site"
        ) from None
    return Recorded(
        created=created,
        reference=attestation.reference,
        position=position,
        change=change,
        regions=rules.get(key),
        rules=len(rules),
    )


def _instance(data: bytes, position: int) -> tuple[str, bytes | None]:
    """Return the source path that the pack ``data`` names for the instance
    at ``position``, and its SHA-256, or None for either it does not hold."""
    document = json.loads(data.decode("ascii"))  # attested_pack has parsed it
    instances = document.get("instances")
    if not isinstance(instances, list):
        raise PixelRegionRulesError("the QC pack is not of its format")
    for entry in instances:
        if isinstance(entry, dict) and entry.get("position") == position:
            named, digest = entry.get("source"), entry.get("source_sha256")
            if not isinstance(named, str) or not named:
                raise PixelRegionRulesError("the QC pack is not of its format")
            try:
                return named, None if digest is None else bytes.fromhex(digest)
            except (TypeError, ValueError):
                raise PixelRegionRulesError(
                    "the QC pack is not of its format"
                ) from None
    return "", None


def _source_dataset(path: str | os.PathLike, digest: bytes) -> pydicom.Dataset:
    """Return the data set of the source file at ``path``, which must have
    the SHA-256 ``digest``."""
    try:
        content = Path(path).read_bytes()
    except OSError:
        raise PixelRegionRulesError(
            "the instance's source file could not be read; give a copy of it "
            "with --source"
        ) from None
    if hashlib.sha256(content).digest() != digest:
        raise PixelRegionRulesError(
            "the source file is not the file that the QC pack's run read"
        )
    try:
        return read_source(content).dataset()
    except SourceRefused:
        raise PixelRegionRulesError(
            "the instance's source file could not be read as DICOM"
        ) from None


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.pixel_region_rules_command",
        stderr=stderr,
        description=(
            "Record regions that a reviewer approved for an image in an "
            "attested QC pack as the region rule for the image's kind in the "
            "custodian's store, which is started if it does not exist. For "
            "use before the first supported release."
        ),
    )
    parser.add_argument(
        "store",
        metavar="STORE",
        help="the region rules store, kept by the custodian with the key",
    )
    parser.add_argument(
        "pack",
        metavar="PACK",
        help="the directory of the attested QC pack",
    )
    parser.add_argument(
        "position",
        metavar="POSITION",
        type=int,
        help="the image's run position in the QC pack",
    )
    parser.add_argument(
        "--region",
        action="append",
        nargs=4,
        type=int,
        required=True,
        metavar=("TOP", "LEFT", "BOTTOM", "RIGHT"),
        help=(
            "a region to record, as the QC pack writes it, in pixels from the "
            "frame's top left corner with the bottom row and right column "
            "excluded, which the reviewer approved for the image; may be "
            "given more than once"
        ),
    )
    parser.add_argument(
        "--source",
        metavar="FILE",
        help=(
            "a copy of the image's source file, in place of the file that the "
            "QC pack names; it must have the SHA-256 that the pack records"
        ),
    )
    existing = parser.add_mutually_exclusive_group()
    existing.add_argument(
        "--replace",
        action="store_true",
        help="replace the regions that the store holds for the image's kind",
    )
    existing.add_argument(
        "--add",
        action="store_true",
        help="add the regions to those that the store holds for the image's kind",
    )
    parser.add_argument(
        "--protect",
        action="append",
        default=[],
        metavar="DIRECTORY",
        help=(
            "a directory that STORE must not be inside, such as a run's source "
            "or release; may be given more than once"
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the arguments, record the rule, and print a summary.

    Returns
    -------
    int
        The exit status, as the module describes.

    Raises
    ------
    SystemExit
        With :data:`EXIT_USAGE` if the arguments cannot be parsed, or 0 for
        ``--help``, as :mod:`argparse` does.
    """
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    arguments = build_parser(stderr=stderr).parse_args(argv)
    existing = (
        Existing.REPLACE
        if arguments.replace
        else Existing.ADD
        if arguments.add
        else Existing.REFUSE
    )
    try:
        regions = []
        for number, sides in enumerate(arguments.region, start=1):
            try:
                regions.append(TextBox(*sides))
            except ValueError:
                raise PixelRegionRulesError(
                    f"region {number} must have rows and columns, with TOP "
                    "below BOTTOM and LEFT below RIGHT"
                ) from None
        recorded = record_rule(
            Path(arguments.store),
            Path(arguments.pack),
            arguments.position,
            tuple(regions),
            source=None if arguments.source is None else Path(arguments.source),
            existing=existing,
            protected_dirs=arguments.protect,
        )
    except PixelRegionRulesError as error:
        _print(f"error: {error}; nothing was recorded", stderr)
        return EXIT_NOT_RECORDED
    _print("\n".join(recorded.summary_lines()), stdout)
    return EXIT_RECORDED


if __name__ == "__main__":
    sys.exit(main())
