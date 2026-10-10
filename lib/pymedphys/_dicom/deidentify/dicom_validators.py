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

"""Run independent DICOM validators over files, and keep only what holds no value.

Three validators, none of them part of PyMedPhys, check what the standard
requires of an instance rather than what de-identification removes:

- ``dciodvfy``, from David Clunie's dicom3tools (BSD-3-Clause), checks an
  instance against the modules and attributes of its IOD, each value
  against its VR and VM, defined terms and enumerated values, and the
  encoding of the file;
- ``dcentvfy``, from dicom3tools, checks that instances of one patient,
  study, series, frame of reference, or equipment give the same values for
  the attributes of that information entity;
- dicom-validator, from the pydicom project (MIT), checks an instance
  against the IOD that it reads from the DocBook source of one edition of
  PS3.3, PS3.4, and PS3.6, which this module pins to the edition that the
  engine's own tables are generated from.

The dicom3tools executables must be on the ``PATH``. dicom-validator is a
Python package, which the ``tests`` extra installs; it downloads the
DocBook source of its edition from NEMA the first time it is used, into a
directory that the caller chooses.

Every validator quotes values: dciodvfy and dcentvfy print them, and file
names, in their messages, and dicom-validator keeps them in the context of
its findings. None of that leaves this module. Each message is reduced to a
:class:`Finding`: the validator, the severity, the attribute's path as tags
alone, without item numbers or private creators, the message type, and the
module or information entity that it names. A message type is the text of
the message before the first value that it quotes, in angle brackets or
quotation marks or after an equals sign, with any reason that follows the
value. Each part is kept only where it is made of strings compiled into the
validator's own executable, with counts replaced and a few short words
between them, so nothing passes that is not the validator's own text; any
other message is counted without its text. A module, an information
entity, an attribute's keyword that pydicom's dictionary lacks, and an IOD
name are kept only where the validator's executable holds them too, since a
value that spans lines can print a line of a message's form. A line that
does not have the form of a message is counted as unrecognised, without its
text. The diagnostics of pydicom's reads, for dicom-validator, are redacted
as the engine's are (:func:`~pymedphys._dicom.deidentify.diagnostics.redacted_diagnostics`).
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import functools
import hashlib
import importlib.metadata
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from pymedphys._imports import (
    dicom_validator_editions,
    dicom_validator_files,
    dicom_validator_handlers,
    dicom_validator_results,
    pydicom,
)

from .diagnostics import redacted_diagnostics

DCIODVFY = "dciodvfy"
DCENTVFY = "dcentvfy"
DICOM_VALIDATOR = "dicom-validator"
VALIDATORS = (DCIODVFY, DCENTVFY, DICOM_VALIDATOR)

ERROR = "error"
WARNING = "warning"
# A line of a validator's output that has no message's form, counted without
# its text.
UNRECOGNISED = "unrecognised"
UNRECOGNISED_MESSAGE = "line not recognised"
# The message type of a message whose text is not the validator's own.
UNPROVEN_MESSAGE = "message not shown"
# What a finding that names no attribute gives as its path.
NO_PATH = ""

# Each validator run on one file is stopped after this many seconds.
TIMEOUT_SECONDS = 600
# The shortest printable run of an executable's bytes that is kept as one of
# its strings.
_SHORTEST_STRING = 4

# A path's private creators are quoted, and may hold any character but a
# quotation mark.
_DCIODVFY_LINE = re.compile(
    r"^(?P<severity>Error|Warning) - "
    r'(?:<(?P<path>/(?:"[^"]*"|[^"])*?)> - )?(?P<message>.*)$'
)
_DCENTVFY_LINE = re.compile(
    r"^(?P<severity>Error|Warning) - (?P<message>[^<>]*?)"
    r" - Element=<(?P<element>[A-Za-z0-9]+)> IE=<(?P<entity>[A-Za-z]+)>"
)
_MODULE = re.compile(r" - Module=<(?P<module>[A-Za-z0-9]+)>$")
_IOD_NAME = re.compile(r"^[A-Za-z0-9]+$")
# What starts a value in a dicom3tools message.
_VALUE_START = re.compile(r"[<\"'=]")
# The words, too short to be kept as strings of an executable, that
# dicom3tools puts between the strings of a message.
_CONNECTORS = frozenset(
    {"a", "an", "and", "at", "but", "by", "for", "in", "is", "not", "of", "on"}
    | {"or", "the", "to"}
)
# A word, between spaces or the ends of the text.
_WORD = re.compile(r"(?<![^ ])[a-z]+(?![^ ])")
_COUNT = re.compile(r"[0-9]+")
_VR_CODE = re.compile(r"\[([A-Z]{2})\]")
# The VRs of PS3.5 Table 6.2-1, which dicom3tools prints in brackets.
_VRS = frozenset(
    "AE AS AT CS DA DS DT FD FL IS LO LT OB OD OF OL OV OW PN SH SL SQ SS ST SV"
    " TM UC UI UL UN UR US UT UV".split()
)
# The longest string of an executable that a message is matched against,
# and the longest text that is matched at all.
_LONGEST_PIECE = 200
_LONGEST_TEXT = 500
_QUOTED = re.compile(r'"[^"]*"')
_TAG = re.compile(r"\(([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4})")
_VERSION = re.compile(r"^dicom3tools Version: (?P<version>[A-Za-z0-9._-]+)\s*$")
# The messages with which dciodvfy reports an attribute that its dictionary
# does not have, read from a file in Implicit VR, whose contents it therefore
# cannot parse.
_UNPARSED_IN_IMPLICIT_VR = (
    "Attribute with an even group number is not a recognized standard attribute",
)
# The message with which dciodvfy reports an attribute that its dictionary
# does not have, given the VR UN in a file in Explicit VR, whose contents it
# therefore cannot parse either.
_UNPARSED = ("Unrecognized tag - explicit value representation is UN",)
# The status of dciodvfy and dcentvfy when they ran to the end: 0 without
# errors and 1 with them.
_COMPLETED = (0, 1)


class ValidatorUnavailable(Exception):
    """A validator that was asked for is not installed or cannot be loaded."""


class Status(enum.Enum):
    """Whether a validator could check a file."""

    VALIDATED = "validated"
    # The validator did not run to the end, for example because it crashed.
    FAILED = "failed"
    # The validator does not know the file's SOP Class.
    UNSUPPORTED = "unsupported"


@dataclasses.dataclass(frozen=True, order=True)
class Finding:
    """One kind of message of a validator, without any value.

    Attributes
    ----------
    validator : str
        One of :data:`VALIDATORS`.
    severity : str
        :data:`ERROR`, :data:`WARNING`, or :data:`UNRECOGNISED`.
    path : str
        The attribute's place, its tags from the top level down, such as
        ``"(0008,1115)/(0008,1150)"``, without item numbers, or
        :data:`NO_PATH`.
    message : str
        The message type, such as ``"Missing attribute for Type 1
        Required"``. Where the message quoted a value, it reads
        ``<value>`` in its place.
    context : str
        The module that dciodvfy or dicom-validator names, or the
        information entity that dcentvfy names, or ``""``.
    """

    validator: str
    severity: str
    path: str
    message: str
    context: str = ""

    def json(self) -> dict[str, str]:
        """Return the finding as a JSON object."""
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Validation:
    """What one validator found in one file, or in one set of files.

    Attributes
    ----------
    validator : str
        One of :data:`VALIDATORS`.
    status : Status
        Whether the validator could check it.
    findings : Mapping[Finding, int]
        How many times the validator gave each finding.
    unparsed : frozenset[str]
        The paths of the attributes whose contents the validator could not
        parse, because its dictionary lacks them and the file is in Implicit
        VR or gives them the VR UN. A finding below one of them in another
        file cannot be compared with this one.
    iod : str
        The IOD that dciodvfy checked the file against, as it names it, or
        dicom-validator's name of the IOD; ``""`` where none is known.
    """

    validator: str
    status: Status
    findings: Mapping[Finding, int]
    unparsed: frozenset[str] = frozenset()
    iod: str = ""


@dataclasses.dataclass(frozen=True)
class Versions:
    """The validators' versions, and what dicom-validator checks against.

    Attributes
    ----------
    dicom3tools : str or None
        The dicom3tools snapshot that ``dciodvfy`` reports, or ``None``.
    dicom_validator : str or None
        The installed dicom-validator distribution's version, or ``None``.
    edition : str or None
        The DICOM edition whose DocBook source dicom-validator reads.
    docbook_sha256 : Mapping[str, str]
        The SHA-256 of each DocBook file it read, by file name.
    """

    dicom3tools: str | None
    dicom_validator: str | None
    edition: str | None
    docbook_sha256: Mapping[str, str]

    def json(self) -> dict[str, object]:
        """Return the versions as a JSON object."""
        return {
            "dicom3tools": self.dicom3tools,
            "dicom_validator": self.dicom_validator,
            "edition": self.edition,
            "docbook_sha256": dict(sorted(self.docbook_sha256.items())),
        }


def tag_path(tags: Iterable[int]) -> str:
    """Return the path of tags, from the top level down, as text.

    >>> tag_path([0x00081115, 0x00081150])
    '(0008,1115)/(0008,1150)'
    """
    return "/".join(f"({tag >> 16:04X},{tag & 0xFFFF:04X})" for tag in tags)


def _dciodvfy_path(text: str) -> str:
    """Return the tags of a dciodvfy path, without its private creators."""
    return "/".join(
        f"({group.upper()},{element.upper()})"
        for group, element in _TAG.findall(_QUOTED.sub("", text))
    )


def message_type(text: str, strings: frozenset[str]) -> tuple[str, str]:
    """Return a dicom3tools message's type and its module, without values.

    The type is the message before the first value it quotes, in angle
    brackets or quotation marks or after an equals sign, with ``<value>`` in
    place of the value, and the reason after the last value. The text before
    the value must be made of ``strings``, those compiled into the validator
    (:func:`composed`), or the type is :data:`UNPROVEN_MESSAGE`; the reason is
    kept only where it is too. A module is kept only where it is a name of
    letters and digits that is the validator's own (:func:`own_name`).

    >>> message_type(
    ...     "Value dubious for this VR [PN] = <ANY^VALUE> - Retired Person Name form",
    ...     frozenset({"Value dubious for this VR", "Retired Person Name form"}),
    ... )
    ('Value dubious for this VR [PN] = <value> - Retired Person Name form', '')
    >>> message_type(
    ...     'Orientation cannot be identical = "LE" and "LE"',
    ...     frozenset({"Orientation cannot be identical"}),
    ... )
    ('Orientation cannot be identical = <value>', '')
    >>> message_type("Unrecognized enumerated value = <ANY - VALUE>", frozenset())
    ('message not shown', '')
    """
    module = ""
    found = _MODULE.search(text)
    if found:
        module = found["module"] if own_name(found["module"], strings) else ""
        text = text[: found.start()]
    start = _VALUE_START.search(text)
    head = (text if start is None else text[: start.start()]).strip()
    kept = composed(head, strings)
    if kept is None:
        return UNPROVEN_MESSAGE, module
    if start is None:
        return kept, module
    kept += " = <value>" if start.group() == "=" else " <value>"
    _, separator, reason = text[start.end() :].rpartition(" - ")
    if separator and _VALUE_START.search(reason) is None:
        proven = composed(reason.strip(), strings)
        if proven:
            kept += f" - {proven}"
    return kept, module


@functools.lru_cache(maxsize=65536)
def composed(text: str, strings: frozenset[str]) -> str | None:
    """Return text made of an executable's strings, or ``None`` if it is not.

    The text must be a sequence of ``strings``, separated by spaces or by the
    short words that dicom3tools puts between them, with VRs in brackets and
    counts, each of which reads ``<n>``.

    >>> composed("Missing attribute for Type 1 Required",
    ...          frozenset({"Missing attribute", "Type 1 Required"}))
    'Missing attribute for Type 1 Required'
    >>> composed("have 3 items", frozenset({"have", "items"}))
    'have <n> items'
    >>> composed("Missing attribute JOHN", frozenset({"Missing attribute"})) is None
    True
    """
    failed: set[int] = set()

    def rest(index: int) -> list[str] | None:
        if index == len(text):
            return []
        if index not in failed:
            for piece, end in _pieces(text, index, strings):
                tail = rest(end)
                if tail is not None:
                    return [piece, *tail]
            failed.add(index)
        return None

    if not text or len(text) > _LONGEST_TEXT:
        return None
    pieces = rest(0)
    return None if pieces is None else "".join(pieces)


def _pieces(
    text: str, index: int, strings: frozenset[str]
) -> Iterable[tuple[str, int]]:
    """Yield each piece that text can begin with at an index, and its end."""
    if text[index] in " -":
        yield text[index], index + 1
    for end in range(min(len(text), index + _LONGEST_PIECE), index, -1):
        if text[index:end] in strings:
            yield text[index:end], end
    found = _WORD.match(text, index)
    if found and found.group() in _CONNECTORS:
        yield found.group(), found.end()
    found = _VR_CODE.match(text, index)
    if found and found[1] in _VRS:
        yield found.group(), found.end()
    found = _COUNT.match(text, index)
    if found:
        yield "<n>", found.end()


@functools.cache
def _strings(executable: str) -> frozenset[str]:
    """Return the printable strings compiled into an executable."""
    data = Path(executable).read_bytes()
    pattern = rb"[\x20-\x7e]{%d,}" % _SHORTEST_STRING
    return frozenset(run.decode("ascii").strip() for run in re.findall(pattern, data))


@functools.lru_cache(maxsize=4096)
def own_name(name: str, strings: frozenset[str]) -> bool:
    """Return whether a name is one of an executable's strings, or ends one.

    A compiler may store a string as the end of a longer one that ends the
    same way, so a module's name can be found only as such an end.

    >>> own_name("Patient", frozenset({"ClinicalTrialPatient"}))
    True
    >>> own_name("Smith", frozenset({"ClinicalTrialPatient"}))
    False
    """
    return name in strings or any(string.endswith(name) for string in strings)


def find_executable(name: str) -> str | None:
    """Return the resolved path of a dicom3tools executable on the PATH."""
    found = shutil.which(name)
    return None if found is None else os.path.realpath(found)


def dicom3tools_version(executable: str) -> str | None:
    """Return the dicom3tools snapshot that an executable reports."""
    completed = subprocess.run(
        [executable, "-version"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    for line in (completed.stdout + completed.stderr).splitlines():
        found = _VERSION.match(line)
        if found:
            return found["version"]
    return None


def _run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            list(arguments),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def parse_dciodvfy(
    output: str, strings: frozenset[str], *, implicit_vr: bool = False
) -> Validation:
    """Reduce dciodvfy's output for one file to findings without values.

    ``strings`` are those compiled into the executable that wrote it. In a
    file in Implicit VR, ``implicit_vr``, an attribute that dciodvfy's
    dictionary lacks is one whose contents it cannot parse; in Explicit VR
    it reads them from the VR the file gives, unless that is UN. The status is
    :attr:`Status.VALIDATED`; :func:`run_dciodvfy` gives another where
    dciodvfy did not run to the end.
    """
    findings: collections.Counter[Finding] = collections.Counter()
    unparsed = set()
    iod = ""
    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        found = _DCIODVFY_LINE.match(line)
        if found is None:
            if not iod and _IOD_NAME.match(line) and own_name(line, strings):
                iod = line
            else:
                findings[_unrecognised(DCIODVFY)] += 1
            continue
        path = _dciodvfy_path(found["path"] or "")
        message, module = message_type(found["message"], strings)
        findings[
            Finding(DCIODVFY, found["severity"].lower(), path, message, module)
        ] += 1
        if path and (
            message in _UNPARSED
            or (implicit_vr and message in _UNPARSED_IN_IMPLICIT_VR)
        ):
            unparsed.add(path)
    return Validation(
        DCIODVFY, Status.VALIDATED, dict(findings), frozenset(unparsed), iod
    )


def _unrecognised(validator: str) -> Finding:
    return Finding(validator, UNRECOGNISED, NO_PATH, UNRECOGNISED_MESSAGE)


def run_dciodvfy(executable: str, path: Path) -> Validation:
    """Check one file with dciodvfy."""
    completed = _run([executable, "-new", os.fspath(path)])
    if completed is None or completed.returncode not in _COMPLETED:
        return Validation(DCIODVFY, Status.FAILED, {})
    return parse_dciodvfy(
        completed.stdout + completed.stderr,
        _strings(executable),
        implicit_vr=_in_implicit_vr(path),
    )


def _in_implicit_vr(path: Path) -> bool:
    """Return whether a file's File Meta Information gives Implicit VR."""
    try:
        with redacted_diagnostics():
            meta = pydicom.filereader.read_file_meta_info(path)
    except Exception:  # pylint: disable = broad-exception-caught
        return False
    return meta.get("TransferSyntaxUID") == pydicom.uid.ImplicitVRLittleEndian


def parse_dcentvfy(output: str, strings: frozenset[str]) -> Validation:
    """Reduce dcentvfy's output for a set of files to findings without values.

    Each finding names the attribute, by its tag where pydicom's dictionary
    has its keyword and otherwise by the keyword, and the information
    entity; the files and values that dcentvfy compared are dropped. The
    message is kept only where it is made of ``strings``, those compiled
    into the executable that wrote it (:func:`composed`), and a keyword or
    entity only where it is one of them (:func:`own_name`).
    """
    findings: collections.Counter[Finding] = collections.Counter()
    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        found = _DCENTVFY_LINE.match(line)
        if found is None:
            findings[_unrecognised(DCENTVFY)] += 1
            continue
        tag = pydicom.datadict.tag_for_keyword(found["element"])
        if tag is not None:
            path = tag_path([tag])
        elif own_name(found["element"], strings):
            path = found["element"]
        else:
            path = NO_PATH
        findings[
            Finding(
                DCENTVFY,
                found["severity"].lower(),
                path,
                composed(found["message"].strip(), strings) or UNPROVEN_MESSAGE,
                found["entity"] if own_name(found["entity"], strings) else "",
            )
        ] += 1
    return Validation(DCENTVFY, Status.VALIDATED, dict(findings))


def run_dcentvfy(executable: str, paths: Sequence[Path]) -> Validation:
    """Check that a set of files gives each information entity consistently."""
    completed = _run([executable, *(os.fspath(path) for path in paths)])
    if completed is None or completed.returncode not in _COMPLETED:
        return Validation(DCENTVFY, Status.FAILED, {})
    return parse_dcentvfy(completed.stdout + completed.stderr, _strings(executable))


@dataclasses.dataclass(frozen=True)
class DicomValidator:
    """dicom-validator, loaded with the tables of one edition.

    Attributes
    ----------
    edition : str
        The DICOM edition.
    standard_path : Path
        The directory with that edition's DocBook source and tables.
    """

    edition: str
    standard_path: Path
    info: object = dataclasses.field(repr=False, compare=False)

    @classmethod
    def load(cls, standard_path: str | Path, edition: str) -> DicomValidator:
        """Load an edition's tables, downloading its DocBook source if needed.

        Raises
        ------
        ValidatorUnavailable
            If the edition cannot be downloaded or read.
        """
        standard_path = Path(standard_path)
        standard_path.mkdir(parents=True, exist_ok=True)
        # dicom-validator's readers give the root logger a handler that
        # writes to standard output, at level INFO, so that every later
        # record of any logger, pydicom's among them, would be printed
        # there. The root logger is restored.
        root = logging.getLogger()
        handlers, level = list(root.handlers), root.level
        try:
            reader = dicom_validator_editions.EditionReader(standard_path)
            if reader.get_edition_path(edition) is None:
                raise ValidatorUnavailable(
                    f"dicom-validator could not obtain DICOM edition {edition}"
                )
            info = reader.load_dicom_info(edition)
        finally:
            root.handlers[:] = handlers
            root.setLevel(level)
        return cls(edition, standard_path, info)

    def docbook_sha256(self) -> dict[str, str]:
        """Return the SHA-256 of each DocBook file the tables were read from."""
        directory = self.standard_path / self.edition / "docbook"
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.glob("*.xml"))
        }

    def validate(self, path: Path) -> Validation:
        """Check one file against its IOD."""
        settings = pydicom.config.settings
        saved = settings.reading_validation_mode
        # Nothing is reported as it is found: the findings are read from the
        # result.
        handler = dicom_validator_handlers.NullValidationResultHandler()
        validator = dicom_validator_files.DicomFileValidator(
            self.info, logging.CRITICAL, error_handler=handler
        )
        try:
            with redacted_diagnostics():
                (result,) = list(validator.validate(os.fspath(path)).values())
                unparsed = _unparsed_by_pydicom(path)
        except Exception:  # pylint: disable = broad-exception-caught
            # A file that dicom-validator cannot read is reported by its
            # status, never by the exception, which can quote a value.
            return Validation(DICOM_VALIDATOR, Status.FAILED, {})
        finally:
            settings.reading_validation_mode = saved
        statuses = dicom_validator_results.Status
        if result.status == statuses.UnknownSOPClassUID:
            return Validation(DICOM_VALIDATOR, Status.UNSUPPORTED, {})
        if result.status not in (statuses.Passed, statuses.Failed):
            return Validation(DICOM_VALIDATOR, Status.FAILED, {})
        findings: collections.Counter[Finding] = collections.Counter()
        for module, errors in result.module_errors.items():
            for tag, error in errors.items():
                findings[_dicom_validator_finding(module, tag, error)] += 1
        iod = self.info.iods.get(result.sop_class_uid, {}).get("title", "")
        return Validation(
            DICOM_VALIDATOR, Status.VALIDATED, dict(findings), unparsed, str(iod)
        )


def _dicom_validator_finding(module: str, tag: object, error: object) -> Finding:
    """Return a finding of dicom-validator, without the error's context."""
    path = tag_path([*(tag.parents or []), tag.tag])  # type: ignore[attr-defined]
    code = error.code.name  # type: ignore[attr-defined]
    tag_type = str(getattr(error.type, "value", error.type))  # type: ignore[attr-defined]
    scope = error.scope.name  # type: ignore[attr-defined]
    message = f"{code} (Type {tag_type})"
    if scope != "General":
        message += f" in {scope}"
    return Finding(DICOM_VALIDATOR, ERROR, path, message, module)


def _unparsed_by_pydicom(path: Path) -> frozenset[str]:
    """Return the paths of the elements that pydicom reads as UN.

    dicom-validator reads files with pydicom, which gives an element that
    its dictionary lacks, in a file in Implicit VR, the VR UN, as it does an
    element that a file in Explicit VR gives that VR, so the element's
    contents are not checked. A private element is UN for any validator, and
    is left out.
    """
    dataset = pydicom.dcmread(path, stop_before_pixels=True, force=True)
    unparsed: set[str] = set()

    def walk(items: pydicom.Dataset, parents: tuple[int, ...]) -> None:
        for element in items:
            place = (*parents, int(element.tag))
            if element.VR == "UN" and not element.tag.is_private:
                unparsed.add(tag_path(place))
            elif element.VR == "SQ":
                for item in element.value:
                    walk(item, place)

    walk(dataset, ())
    return frozenset(unparsed)


def dicom_validator_version() -> str | None:
    """Return the installed dicom-validator distribution's version."""
    try:
        return importlib.metadata.version(DICOM_VALIDATOR)
    except importlib.metadata.PackageNotFoundError:
        return None
