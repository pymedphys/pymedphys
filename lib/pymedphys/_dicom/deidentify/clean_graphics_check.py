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

"""A development check of the Clean Graphics Option on public DICOM that
holds graphics, which writes only counts.

MIDI-B's instances hold no curve, overlay, or graphic annotation, so a
MIDI-B run cannot show what the option does. Of the open human DICOM under
CC0, CC BY, or CC BY-NC that was searched for graphics, three sources hold
them: the softcopy Presentation States of the iHEALTH 0.55 T MRI of
consented volunteers, on Zenodo, whose Graphic Annotation Sequences
(0070,0001) hold text and graphic objects; the RT Images of the BRAVEHeart
trial's patients, in the University of Sydney's research data store, which
hold curve groups (50xx,xxxx); and the CT and PET images of the
ACRIN-FLT-Breast trial's patients, in NCI's Imaging Data Commons (IDC),
some of which hold an overlay group with Overlay Data (60xx,3000). None of
the instances read from them holds Overlay Comments (60xx,4000) or an
overlay in unused bits of Pixel Data. Of the public files searched for the
latter, only three of toolkits' test files hold one, and only one of those,
dcm4che's test pattern ovly_p01.dcm, a Secondary Capture of no patient,
holds one that the engine can clear: the other two hold theirs in
compressed Pixel Data, or in a file that the engine cannot read. Two of the
knee Presentation States hold no annotation, but an overlay group whose
only attribute is Overlay Activation Layer (60xx,1001), with which a
Presentation State shows an overlay of the image that it references: it
places no overlay in the state, so the option must keep it and release the
state. :data:`MEMBERS` pins ten of these instances by their archive, their
place in its central directory, their SHA-256, and their SOP Class, and
:func:`read_members` reads each over HTTP ranges, refusing any archive or
member that is not the pinned one. :data:`OBJECTS` pins three
ACRIN-FLT-Breast PET images, of three patients and two scanner models, by
IDC's identifiers of their series and of them, which name their objects in
IDC's public bucket, and dcm4che's test pattern at a commit of dcm4che's
repository, each by its size, its SHA-256, and its SOP Class, and
:func:`read_objects` reads each whole, refusing any object that is not the
pinned one.

:func:`check` runs each instance under Modified Dates, alone and with Clean
Graphics, with and without reviewed annotations lists, and an image with an
overlay in unused bits of Pixel Data also with Clean Graphics and Clean
Pixel Data, whose text finder is the text detector, and tests the runs
against what Table E.1-1 and the design give the option, as
:mod:`.clean_graphics_runs` describes; :func:`main` fails unless every
expectation is met.

The instances are real people's data, but for dcm4che's test pattern, and
this repository's logs and artefacts are public, so the summary, labelled
:data:`FORMAT`, and its page give only counts, codes, tag numbers, the
SHA-256 of the pinned instances as a whole, versions, the text finder's
method, and the data sets' public identifiers: no UID, name, date, text,
path, or value of any instance, and no digest of an annotation. The
instances are held in memory only.

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
from types import MappingProxyType
from typing import Any, BinaryIO

from pymedphys._imports import pydicom

from .clean_graphics_runs import (
    GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE,
    RUNS,
    SECONDARY_CAPTURE,
    InstanceRuns,
    evaluate,
    instance_summary,
    run_instance,
)
from .diagnostics import redacted_diagnostics
from .pixel_cleaning import TextFinder
from .text_evaluation_archives import (
    ARCHIVES,
    Archive,
    RangeReader,
    archive_index,
    http_opener,
)
from .text_evaluation_frames import EvaluationRefused
from .text_evaluation_idc import OPEN_COLLECTIONS
from .text_evaluation_idc import SOURCE as IDC_HOST

FORMAT = "pymedphys-deid-clean-graphics-check/2"
RT_IMAGE = "1.2.840.10008.5.1.4.1.1.481.1"
# The archives that the members are read from, by the keys that
# text_evaluation_archives gives them: a Zenodo record and the MD5 of its
# file, and a path of the University of Sydney's data store.
CARDIAC_MR_COLLECTION = "zenodo_cardiac_mr_0p55t"
CARDIAC_MR = "23089164/aa60c0f515584b4214849cc7fa1382f5"
KNEE_MR_COLLECTION = "zenodo_knee_mr_0p55t"
KNEE_MR = "23964089/1dfe43da0e2feaa8a739998002630005"
# The knee archive of the two Presentation States without annotations, whose
# overlay groups hold only Overlay Activation Layer (60xx,1001).
KNEE_MR_ACTIVATION = "23964089/3145043d3f56591e4e7e669a75ecc0ef"
BRAVEHEART_COLLECTION = "sydney_braveheart_rt_image"
BRAVEHEART = "32833_Byrne_2/P01-P05 (Anonymised).zip"
PET_IMAGE = "1.2.840.10008.5.1.4.1.1.128"
ACRIN_FLT_BREAST = "acrin_flt_breast"
DCM4CHE_TEST_DATA = "dcm4che_test_data"
IDC_BUCKET = "https://idc-open-data.s3.amazonaws.com/"
# The commit of dcm4che whose test data the check reads.
DCM4CHE_COMMIT = "dd6f352c068ca6be399062b0447353458eb30e43"
# Ranges of 1 MiB: an archive's central directory, then each member, take
# few requests and fetch little beyond them.
BLOCK = 1 << 20

JSON_NAME = "clean-graphics-check.json"
MARKDOWN_NAME = "clean-graphics-check.md"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


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
        KNEE_MR_COLLECTION,
        KNEE_MR_ACTIVATION,
        14,
        "7dcdc75192194913e126e59b28c71e5acafa7413c04b57dcc94c6e0c7efbc486",
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    ),
    PinnedMember(
        KNEE_MR_COLLECTION,
        KNEE_MR_ACTIVATION,
        18,
        "5f975b9fb3c49af3efbaeb5698f63c217b8b43e73ec0856a4d24b9840559b591",
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
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


@dataclasses.dataclass(frozen=True)
class ObjectCollection:
    """A collection whose files the check reads whole, each at the address
    that its key gives under the collection's.

    Attributes
    ----------
    name : str
        The collection's name in the summary.
    host : str
        Where its files are served.
    licence : str
    citation : str
        Its DOI, as ``doi:`` and the DOI, or, where it has none, the
        address of the files' source.
    base : str
        The address under which each of its files is served at its key.
    key : str
        A regular expression that each of its files' keys must match whole.
    """

    name: str
    host: str
    licence: str
    citation: str
    base: str
    key: str


# The collections that single files are read from, by name. ACRIN-FLT-Breast
# is named by IDC's collection_id, with the DOI that IDC's index
# (idc-index-data 25.0.5) gives it, and the licence that text_evaluation_idc
# vetted; each of its files is named by IDC's identifiers of its series and
# of it, the CRDC UUIDs, which are no value of the instance. dcm4che's test
# data is read at a pinned commit of its repository, under the repository's
# licence, since its files carry none of their own.
OBJECT_COLLECTIONS: Mapping[str, ObjectCollection] = MappingProxyType(
    {
        ACRIN_FLT_BREAST: ObjectCollection(
            ACRIN_FLT_BREAST,
            IDC_HOST,
            OPEN_COLLECTIONS[ACRIN_FLT_BREAST],
            "doi:10.7937/k9/tcia.2017.ol20zmxg",
            IDC_BUCKET,
            rf"{_UUID}/{_UUID}\.dcm",
        ),
        DCM4CHE_TEST_DATA: ObjectCollection(
            DCM4CHE_TEST_DATA,
            "GitHub",
            "MPL 1.1, GPL 2.0 or later, or LGPL 2.1 or later",
            "https://github.com/dcm4che/dcm4che/tree/"
            f"{DCM4CHE_COMMIT}/dcm4che-test-data",
            "https://raw.githubusercontent.com/dcm4che/dcm4che/"
            f"{DCM4CHE_COMMIT}/dcm4che-test-data/src/main/resources/",
            r"[a-z0-9_]+\.dcm",
        ),
    }
)


@dataclasses.dataclass(frozen=True)
class PinnedObject:
    """One file served whole, a single instance, which the check reads.

    Attributes
    ----------
    collection : str
        Its collection, one of :data:`OBJECT_COLLECTIONS`.
    key : str
        Its address under its collection's.
    size : int
        Its size in bytes.
    sha256 : str
        The SHA-256 of its bytes, as 64 lower-case hex digits.
    sop_class : str
        Its SOP Class UID.
    """

    collection: str
    key: str
    size: int
    sha256: str
    sop_class: str

    def __post_init__(self):
        found = OBJECT_COLLECTIONS.get(self.collection)
        if found is None:
            raise CheckRefused("An object's collection is not a pinned one.")
        if not re.fullmatch(found.key, self.key):
            raise CheckRefused("An object's key is not of its collection.")
        if self.size <= 0:
            raise CheckRefused("An object's size must be in range.")
        if not _SHA256.fullmatch(self.sha256):
            raise CheckRefused("An object needs its digest.")

    @property
    def url(self) -> str:
        """Where its collection serves it."""
        return OBJECT_COLLECTIONS[self.collection].base + self.key

    @property
    def label(self) -> str:
        """The object's name in the summary: its collection and the first
        eight characters of its file's name."""
        return f"{self.collection} {pathlib.PurePosixPath(self.key).stem[:8]}"


# Three PET images of ACRIN-FLT-Breast, each of another patient: two of
# scanner model 1080 and one of Somaris/5 3D, as IDC's index gives their
# models. Each holds an overlay group with Overlay Data, and no curve. Then
# dcm4che's test pattern ovly_p01.dcm, a Secondary Capture of no patient,
# which holds two overlays in unused bits of Pixel Data, bits 14 and 15 of
# 12-bit stored values, and two overlay groups with Overlay Data.
OBJECTS: tuple[PinnedObject, ...] = (
    PinnedObject(
        ACRIN_FLT_BREAST,
        "5262efce-36b2-4334-bb4e-0818398ad2bf/071d33e9-a26b-44bb-ac7b-2ed0adcc1e86.dcm",
        560402,
        "341d6288c67c27b6861b759dddced1b6e74cfba6bb196979a1d4288a695aaa8c",
        PET_IMAGE,
    ),
    PinnedObject(
        ACRIN_FLT_BREAST,
        "d6fee68e-c319-4a49-bf2b-0e326dd846a8/0269516e-4580-4e18-9d72-8dfc976a041d.dcm",
        560382,
        "943f2d688a6e3de72985c81ac997e456e8c6d2061e07b9bf3cf7b2ab2166500c",
        PET_IMAGE,
    ),
    PinnedObject(
        ACRIN_FLT_BREAST,
        "6a8cf6b6-0314-4414-8f9d-c378418d6e97/084d6d18-3ce7-4ecd-8d13-a285c81bb59a.dcm",
        68406,
        "17b750eb676cf651c8fc2d86053918fb2e30d64515ab143abb28086a684fd365",
        PET_IMAGE,
    ),
    PinnedObject(
        DCM4CHE_TEST_DATA,
        "ovly_p01.dcm",
        590940,
        "654df0779faf4afbf9654f2e9edb90bc04d584651312a728c675af2da6a26e3a",
        SECONDARY_CAPTURE,
    ),
)

# A pinned instance, of either kind.
Pinned = PinnedMember | PinnedObject


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


def object_opener(pinned: PinnedObject) -> BinaryIO:
    """An object as its collection serves it, read by ranges."""
    return RangeReader(pinned.url, pinned.size, block=BLOCK)  # type: ignore[return-value]


def read_objects(
    objects: Sequence[PinnedObject] = OBJECTS,
    *,
    opener: Callable[[PinnedObject], BinaryIO] = object_opener,
) -> tuple[tuple[PinnedObject, bytes], ...]:
    """Read each object whole, in order.

    Each must give its pinned size in bytes, and match the SHA-256 and the
    SOP Class that its pin gives it. :func:`object_opener` reads no further
    than that size, so nothing that a server holds beyond it is read.

    Raises
    ------
    CheckRefused
        Where an object is not served, or is not the pinned one.
    """
    found = []
    for pinned in objects:
        try:
            with opener(pinned) as opened:
                data = opened.read(pinned.size + 1)
        except EvaluationRefused:
            raise CheckRefused("An object was not served.") from None
        if len(data) != pinned.size:
            raise CheckRefused("An object is not the pinned one.")
        if hashlib.sha256(data).hexdigest() != pinned.sha256:
            raise CheckRefused("An object is not the pinned one.")
        if sop_class_of(data) != pinned.sop_class:
            raise CheckRefused("An object is not of its pinned SOP Class.")
        found.append((pinned, data))
    return tuple(found)


def read_pinned() -> tuple[tuple[Pinned, bytes], ...]:
    """Every pinned instance: the archives' members, then the objects."""
    return (*read_members(), *read_objects())


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


def _detector() -> TextFinder:
    """The text finder of the run with Clean Pixel Data: the text detector,
    whose pinned model it downloads."""
    # pylint: disable-next = import-outside-toplevel
    from .text_detection import TextDetector

    return TextDetector()


def check(
    found: Sequence[tuple[Pinned, bytes]],
    *,
    detector: Callable[[], TextFinder] | None = None,
) -> dict[str, Any]:
    """Run each member, as :mod:`.clean_graphics_runs` describes, and return
    the summary, whose ``met`` says whether every expectation is met.

    ``detector`` makes the text finder of the run with Clean Pixel Data,
    once, and only where a member takes that run; the summary gives its
    method. It defaults to the text detector.
    """
    members: list[InstanceRuns] = []
    crashed: collections.Counter[str] = collections.Counter()
    made: list[TextFinder] = []
    make = _detector if detector is None else detector

    def finder() -> TextFinder:
        if not made:
            made.append(make())
        return made[0]

    with redacted_diagnostics():
        for member, data in found:
            ran = run_instance(member.label, member.sop_class, data, finder)
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
    records = _collections()
    named = dict.fromkeys(member.collection for member, _ in found)
    digests = sorted(hashlib.sha256(data).hexdigest() for _, data in found)
    return {
        "format": FORMAT,
        "collections": [
            {"name": name, **records[name]} for name in named if name in records
        ],
        "instances": {
            "count": len(found),
            "bytes": sum(len(data) for _, data in found),
            "sha256": hashlib.sha256(
                "".join(f"{each}\n" for each in digests).encode("ascii")
            ).hexdigest(),
        },
        "software": _software(),
        "finder": dict(made[0].method) if made else {},
        "runs": dict(RUNS),
        "members": [instance_summary(each) for each in members],
        "expectations": expectations,
        "met": all(each["met"] for each in expectations),
        "crashed": _sorted(crashed),
    }


def _collections() -> dict[str, dict[str, str]]:
    """Each collection that a pin may name, with its host, its licence, and
    its citation: its DOI, or the address of its source."""
    found = {
        each.collection.name: {
            "host": each.collection.host,
            "licence": each.collection.licence,
            "citation": f"doi:{each.collection.doi}",
        }
        for each in ARCHIVES
    }
    for name, each in OBJECT_COLLECTIONS.items():
        found[name] = {
            "host": each.host,
            "licence": each.licence,
            "citation": each.citation,
        }
    return found


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
        "Public instances that hold graphics, or an overlay group that holds "
        "no overlay, all of real people but a test pattern, each given to "
        "de-identification transforms under Modified Dates, alone and with "
        "Clean Graphics, with reviewed annotations lists built from its own "
        "annotations where it has any, and, where it holds an overlay in "
        "unused bits of Pixel Data, with Clean Graphics and Clean Pixel Data, "
        "and each written file to a release gate. Only counts are shown: no "
        "value, text, image, or file of the instances.",
        "",
        "| About | |",
        "| --- | --- |",
        *(
            f"| Collection | `{each['name']}`, {each['host']}, "
            f"{each['licence']}, {each['citation']} |"
            for each in summary["collections"]
        ),
        f"| Instances | {instances['count']}, {instances['bytes']} bytes, "
        f"SHA-256 of their SHA-256s `{instances['sha256']}` |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
        *(
            [f"| Finder | `{json.dumps(summary['finder'], sort_keys=True)}` |"]
            if summary["finder"]
            else []
        ),
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
            "## Files written with and without Clean Graphics",
            "",
            "The tags in which the file written with Clean Graphics differs "
            "from the one written under Modified Dates alone, without a list.",
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
        summary = check(read_pinned())
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
