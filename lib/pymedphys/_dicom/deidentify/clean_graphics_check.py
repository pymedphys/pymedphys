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

"""A development check of the Clean Graphics Option on public human DICOM
that holds graphics, which writes only counts.

MIDI-B's instances hold no curve, overlay, or graphic annotation, so a
MIDI-B run cannot show what the option does. Of the open human DICOM under
CC0, CC BY, or CC BY-NC that was searched for graphics, two sources hold
them: the softcopy Presentation States of the iHEALTH 0.55 T MRI of
consented volunteers, on Zenodo, whose Graphic Annotation Sequences
(0070,0001) hold text and graphic objects, and the RT Images of the
BRAVEHeart trial's patients, in the University of Sydney's research data
store, which hold curve groups (50xx,xxxx). None holds Overlay Data
(60xx,3000), Overlay Comments (60xx,4000), or an overlay in unused bits of
Pixel Data, which only the synthetic tests exercise. :data:`MEMBERS` pins
eight of these instances by their archive, their place in its central
directory, their SHA-256, and their SOP Class, and :func:`read_members`
reads each over HTTP ranges, refusing any archive or member that is not the
pinned one.

:func:`check` runs each instance under Modified Dates, alone and with Clean
Graphics, with and without reviewed annotations lists, and tests the runs
against what Table E.1-1 and the design give the option, as
:mod:`.clean_graphics_runs` describes; :func:`main` fails unless every
expectation is met.

The instances are real people's data, and this repository's logs and
artefacts are public, so the summary, labelled :data:`FORMAT`, and its page
give only counts, codes, tag numbers, the SHA-256 of the pinned instances
as a whole, versions, and the data sets' public identifiers: no UID, name,
date, text, path, or value of any instance, and no digest of an annotation.
The instances are held in memory only.

Run as ``python -m pymedphys._dicom.deidentify.clean_graphics_check check
--out DIRECTORY``. It is not registered with the ``pymedphys`` command:
nothing de-identification related joins the public command line before the
first supported release.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import importlib.metadata
import io
import json
import pathlib
import platform
import re
import sys
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, BinaryIO

from pymedphys._imports import pydicom

from .clean_graphics_runs import (
    GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE,
    RUNS,
    InstanceRuns,
    evaluate,
    instance_summary,
    run_instance,
)
from .diagnostics import redacted_diagnostics
from .text_evaluation_archives import ARCHIVES, Archive, archive_index, http_opener
from .text_evaluation_frames import EvaluationRefused

FORMAT = "pymedphys-deid-clean-graphics-check/1"
RT_IMAGE = "1.2.840.10008.5.1.4.1.1.481.1"
# The archives that the members are read from, by the keys that
# text_evaluation_archives gives them: a Zenodo record and the MD5 of its
# file, and a path of the University of Sydney's data store.
CARDIAC_MR_COLLECTION = "zenodo_cardiac_mr_0p55t"
CARDIAC_MR = "23089164/aa60c0f515584b4214849cc7fa1382f5"
KNEE_MR_COLLECTION = "zenodo_knee_mr_0p55t"
KNEE_MR = "23964089/1dfe43da0e2feaa8a739998002630005"
BRAVEHEART_COLLECTION = "sydney_braveheart_rt_image"
BRAVEHEART = "32833_Byrne_2/P01-P05 (Anonymised).zip"
# Ranges of 1 MiB: an archive's central directory, then each member, take
# few requests and fetch little beyond them.
BLOCK = 1 << 20

JSON_NAME = "clean-graphics-check.json"
MARKDOWN_NAME = "clean-graphics-check.md"

_SHA256 = re.compile(r"[0-9a-f]{64}")


class CheckRefused(Exception):
    """An archive or member is not one that the check pins; the message
    quotes no value of it."""


@dataclasses.dataclass(frozen=True)
class PinnedMember:
    """One member of a pinned archive, which the check reads.

    It is named by its collection, its archive, and its place in the
    archive's central directory, never by its name in the archive, which
    may hold a person's identifier.

    Attributes
    ----------
    collection : str
        The archive's collection, as :mod:`~.text_evaluation_archives`
        names it.
    archive : str
        The archive's key, as :mod:`~.text_evaluation_archives` gives it.
    entry : int
        Its 0-based place in the archive's central directory.
    sha256 : str
        The SHA-256 of its bytes, as 64 lower-case hex digits.
    sop_class : str
        Its SOP Class UID.
    """

    collection: str
    archive: str
    entry: int
    sha256: str
    sop_class: str

    def __post_init__(self):
        if self.entry < 0:
            raise CheckRefused("A member's place must be in range.")
        if not _SHA256.fullmatch(self.sha256):
            raise CheckRefused("A member needs its digest.")

    @property
    def label(self) -> str:
        """The member's name in the summary: its collection and its place."""
        return f"{self.collection} #{self.entry}"


MEMBERS: tuple[PinnedMember, ...] = (
    PinnedMember(
        CARDIAC_MR_COLLECTION,
        CARDIAC_MR,
        382,
        "6121e7401a99d2e3237039db7655762b53434eb5c3222e5e10445286cc0ba62e",
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        CARDIAC_MR_COLLECTION,
        CARDIAC_MR,
        383,
        "75fd5e35e640b7654d1021d284ba1cdfbae8a0a602c5bf6f22dc2313544be230",
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        CARDIAC_MR_COLLECTION,
        CARDIAC_MR,
        385,
        "92885bc599b340b16a38d2f13bdeb4c66ee67115f1e5b95ba3ba9019d6159fce",
        PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        KNEE_MR_COLLECTION,
        KNEE_MR,
        12,
        "bff31065f8776a5e4cfd5a58eb7c8a17eb0922131718b9fccd72ff5e0bd191ee",
        PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11388,
        "a09abcba3ceda2562355647e4e4cb9fab8c183a7f78b58557ba5a01627b515c8",
        RT_IMAGE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11389,
        "7437e86804b202fac6415a914b69ae9b25a4aba798a235e3db8ae482197e1c53",
        RT_IMAGE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11390,
        "1f69579931a6e0b3e3342c31917b53b50796a2b865b13462fa1bf9efedc3bc12",
        RT_IMAGE,
    ),
    PinnedMember(
        BRAVEHEART_COLLECTION,
        BRAVEHEART,
        11391,
        "4b4ec440c720ae33431ef53424682a34b88744cbbf97c413c3993f707b5f395b",
        RT_IMAGE,
    ),
)


def _archive(key: str, archives: Iterable[Archive] = ARCHIVES) -> Archive:
    for each in archives:
        if each.key == key:
            return each
    raise CheckRefused("A member's archive is not a pinned one.")


def read_members(
    members: Sequence[PinnedMember] = MEMBERS,
    *,
    archives: Iterable[Archive] = ARCHIVES,
    opener: Callable[[Archive, int], BinaryIO] = http_opener,
) -> tuple[tuple[PinnedMember, bytes], ...]:
    """Read each member from its archive, in order.

    Each archive must be the pinned one: of its pinned size, with the
    pinned central directory (:func:`~.text_evaluation_archives.archive_index`).
    Each member must then match the CRC-32 that the directory gives it, as
    :mod:`zipfile` checks on reading, the SHA-256 that its pin gives it,
    and its pinned SOP Class.

    Raises
    ------
    CheckRefused
        Where an archive or a member is not the pinned one.
    """
    archives = tuple(archives)
    by_archive: dict[str, list[PinnedMember]] = {}
    for member in members:
        by_archive.setdefault(member.archive, []).append(member)
    found: dict[PinnedMember, bytes] = {}
    for key, pinned in by_archive.items():
        archive = _archive(key, archives)
        if {each.collection for each in pinned} != {archive.collection.name}:
            raise CheckRefused("A member's archive is not of its collection.")
        with opener(archive, BLOCK) as opened:
            try:
                archive_index(archive, opened)
            except EvaluationRefused:
                raise CheckRefused("An archive is not the pinned one.") from None
            with zipfile.ZipFile(opened) as index:
                entries = index.infolist()
                for member in pinned:
                    found[member] = _read(index, entries, member)
    return tuple((member, found[member]) for member in members)


def _read(
    index: zipfile.ZipFile, entries: Sequence[zipfile.ZipInfo], member: PinnedMember
) -> bytes:
    if member.entry >= len(entries) or entries[member.entry].is_dir():
        raise CheckRefused("A member is not in its archive.")
    try:
        data = index.read(entries[member.entry])
    except (zipfile.BadZipFile, OSError, NotImplementedError):
        raise CheckRefused("A member is not as its archive's index gives it.") from None
    if hashlib.sha256(data).hexdigest() != member.sha256:
        raise CheckRefused("A member is not the pinned one.")
    if sop_class_of(data) != member.sop_class:
        raise CheckRefused("A member is not of its pinned SOP Class.")
    return data


def sop_class_of(data: bytes) -> str | None:
    """A Part 10 file's SOP Class UID, from its file meta information or
    its data set, or None where neither gives one."""
    try:
        dataset = pydicom.dcmread(
            io.BytesIO(data), stop_before_pixels=True, specific_tags=[0x00080016]
        )
    # pydicom raises many types for a file it cannot read, and a message can
    # quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    meta = getattr(dataset, "file_meta", None)
    found = meta.get("MediaStorageSOPClassUID") if meta is not None else None
    found = dataset.get("SOPClassUID", found)
    return None if found is None else str(found)


def check(found: Sequence[tuple[PinnedMember, bytes]]) -> dict[str, Any]:
    """Run each member, as :mod:`.clean_graphics_runs` describes, and return
    the summary, whose ``met`` says whether every expectation is met."""
    members: list[InstanceRuns] = []
    crashed: collections.Counter[str] = collections.Counter()
    with redacted_diagnostics():
        for member, data in found:
            ran = run_instance(member.label, member.sop_class, data)
            members.append(ran)
            if ran.crashed is not None:
                crashed[ran.crashed] += 1
            for each in ran.runs.values():
                if each.outcome.startswith("raised: "):
                    crashed[each.outcome.removeprefix("raised: ")] += 1
    expectations = [
        {"expectation": text, "met": not unmet, "not_met_for": unmet}
        for text, unmet in evaluate(members)
    ]
    collections_by_name = {each.collection.name: each.collection for each in ARCHIVES}
    named = dict.fromkeys(member.collection for member, _ in found)
    digests = sorted(hashlib.sha256(data).hexdigest() for _, data in found)
    return {
        "format": FORMAT,
        "collections": [
            {
                "name": name,
                "host": collections_by_name[name].host,
                "licence": collections_by_name[name].licence,
                "doi": collections_by_name[name].doi,
            }
            for name in named
            if name in collections_by_name
        ],
        "instances": {
            "count": len(found),
            "bytes": sum(len(data) for _, data in found),
            "sha256": hashlib.sha256(
                "".join(f"{each}\n" for each in digests).encode("ascii")
            ).hexdigest(),
        },
        "software": _software(),
        "runs": dict(RUNS),
        "members": [instance_summary(each) for each in members],
        "expectations": expectations,
        "met": all(each["met"] for each in expectations),
        "crashed": _sorted(crashed),
    }


def _sorted(counter: Mapping[str, int]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _software() -> dict[str, str]:
    """The versions of Python and of the packages that the counts depend on."""
    versions = {"python": platform.python_version()}
    for package in ("pymedphys", "numpy", "pydicom"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    return versions


def markdown(summary: Mapping[str, Any]) -> str:
    """Render the summary's counts as a CommonMark page, and nothing else."""
    instances = summary["instances"]
    lines = [
        "# Clean Graphics on public data",
        "",
        "Public instances of real people that hold graphics, each given to "
        "de-identification transforms under Modified Dates, alone and with "
        "Clean Graphics, with reviewed annotations lists built from its own "
        "annotations, and each written file to a release gate. Only counts "
        "are shown: no value, text, image, or file of the instances.",
        "",
        "| About | |",
        "| --- | --- |",
        *(
            f"| Collection | `{each['name']}`, {each['host']}, "
            f"{each['licence']}, doi:{each['doi']} |"
            for each in summary["collections"]
        ),
        f"| Instances | {instances['count']}, {instances['bytes']} bytes, "
        f"SHA-256 of their SHA-256s `{instances['sha256']}` |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
        f"| Result | {'every expectation met' if summary['met'] else 'not met'} |",
        "",
        "## Expectations",
        "",
        "| Expectation | Met | Not met for |",
        "| --- | --- | --- |",
        *(
            f"| {each['expectation']} | {'yes' if each['met'] else 'no'} | "
            f"{', '.join(each['not_met_for']) or '-'} |"
            for each in summary["expectations"]
        ),
        "",
        "## Instances",
        "",
        "| Instance | SOP Class | Holds |",
        "| --- | --- | --- |",
        *(
            f"| {each['member']} | {each['sop_class']} | {_counts(each['holds'])} |"
            for each in summary["members"]
        ),
        "",
        "## Runs",
        "",
        "| Instance | Run | List | Outcome | Reasons | Annotations | Sets | Written |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for each in summary["members"]:
        for name, ran in each["runs"].items():
            lines.append(
                f"| {each['member']} | {summary['runs'][name]} | {_listed(ran)} | "
                f"{ran['outcome']} | {_reasons(ran.get('reasons', {}))} | "
                f"{_counts(ran.get('annotations', {}))} | "
                f"{_counts(ran.get('sets', {}))} | "
                f"{_counts(ran.get('written', {}))} |"
            )
    compared = [each for each in summary["members"] if "differences" in each]
    if compared:
        lines += [
            "",
            "## Images with and without Clean Graphics",
            "",
            "| Instance | Added | Removed | Differ |",
            "| --- | --- | --- | --- |",
            *(
                f"| {each['member']} | "
                + " | ".join(
                    ", ".join(each["differences"][kind]) or "-"
                    for kind in ("added", "removed", "differ")
                )
                + " |"
                for each in compared
            ),
        ]
    if summary["crashed"]:
        lines += [
            "",
            "## Runs that raised, by type and place",
            "",
            "| | Runs |",
            "| --- | ---: |",
            *(f"| {site} | {count} |" for site, count in summary["crashed"].items()),
        ]
    return "\n".join(lines) + "\n"


def _counts(counts: Mapping[str, Any]) -> str:
    """Counts as one table cell: each name and value, or a dash."""
    parts = []
    for name, value in counts.items():
        if isinstance(value, bool):
            value = "yes" if value else "no"
        elif isinstance(value, list):
            value = ", ".join(str(each).replace("_", " ") for each in value) or "none"
        parts.append(f"{name.replace('_', ' ')} {value}")
    return "; ".join(parts) or "-"


def _reasons(counts: Mapping[str, int]) -> str:
    """Reasons as one table cell, each with its count where it is not 1."""
    return (
        "; ".join(
            name if count == 1 else f"{name} ({count})"
            for name, count in counts.items()
        )
        or "-"
    )


def _listed(ran: Mapping[str, Any]) -> str:
    """A run's reviewed annotations list as one table cell: its decisions,
    and how many passes the run took, or a dash where it had no list."""
    if "list" not in ran:
        return "-"
    passes = ran["passes"]
    decisions = [f"{decision} {count}" for decision, count in ran["list"].items()]
    return "; ".join(
        [
            *(decisions or ["empty"]),
            f"{passes} pass" if passes == 1 else f"{passes} passes",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Read the pinned instances and check them, as the module describes.

    ``check`` takes ``--out``, a directory that must not exist, writes
    ``clean-graphics-check.json`` and ``clean-graphics-check.md``, prints
    the page, and returns 1 unless every expectation is met.

    Raises
    ------
    SystemExit
        With a refusal's message, which quotes no value, and no traceback.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.clean_graphics_check",
        description=(
            "Check the Clean Graphics Option on public instances that hold "
            "graphics, and write only counts. For development only."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    checking = commands.add_parser("check", help="Read and check the instances.")
    checking.add_argument("--out", required=True, type=pathlib.Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.out.exists():
            raise CheckRefused("--out must not exist.")
        summary = check(read_members())
    except CheckRefused as refusal:
        raise SystemExit(str(refusal)) from None
    page = markdown(summary)
    arguments.out.mkdir(parents=True)
    (arguments.out / JSON_NAME).write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (arguments.out / MARKDOWN_NAME).write_text(page, encoding="utf-8")
    sys.stdout.write(page)
    return 0 if summary["met"] else 1


if __name__ == "__main__":
    sys.exit(main())
