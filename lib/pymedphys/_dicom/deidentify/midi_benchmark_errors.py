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

"""Describe the MIDI benchmark's internal errors without a value (D-018).

The run sequesters an instance whose transform or gate raises, with
:attr:`~pymedphys._dicom.deidentify.reasons.RunReason.INTERNAL_ERROR`, and
keeps nothing of the exception, whose message could quote a value. To fix
such an error, a developer needs to know where it was raised and for what
kind of instance. :class:`ErrorRecorder` wraps the transform and the gate
that the benchmark gives the run: each exception is counted by the stage
that raised it, its type, the code locations of its innermost frame and of
the innermost frame in PyMedPhys, and the instance's SOP Class and transfer
syntax, as the standard names them, and then raised again, so the run
treats it exactly as it would have.
"""

from __future__ import annotations

import collections
import io
import threading
import traceback
from collections.abc import Mapping
from pathlib import Path, PurePath

from pymedphys._imports import pydicom

from .elements import (
    DEFAULT_CODECS,
    UndecodableElement,
    dataset_codecs,
    read_element,
)
from .file_layout import ElementPath
from .references import InstanceRecord
from .run_results import (
    Gate,
    HoldForReview,
    Release,
    Sequestered,
    Transform,
    Transformed,
)
from .source import SourceEvidence, SourceRefused, read_source

# Directories below which a path names code, innermost root first.
_ROOTS = ("site-packages", "dist-packages")
_PACKAGES = ("pymedphys",)


def code_location(filename: str) -> str:
    """Return the part of a source path that names code, not where it is.

    >>> code_location("/venv/lib/python3.14/site-packages/pydicom/dataset.py")
    'pydicom/dataset.py'
    >>> code_location("/work/pymedphys/lib/pymedphys/_dicom/deidentify/run.py")
    'pymedphys/_dicom/deidentify/run.py'
    >>> code_location("/usr/lib/python3.14/zipfile/__init__.py")
    'zipfile/__init__.py'
    >>> code_location("/data/somewhere/else.py")
    '<elsewhere>'
    """
    if filename.startswith("<") and filename.endswith(">"):
        return filename
    parts = PurePath(filename).parts
    for root in _ROOTS:
        if root in parts:
            index = len(parts) - 1 - parts[::-1].index(root)
            return "/".join(parts[index + 1 :]) or "<elsewhere>"
    for package in _PACKAGES:
        if package in parts[:-1]:
            index = len(parts) - 2 - parts[-2::-1].index(package)
            return "/".join(parts[index:])
    for index, part in enumerate(parts[:-1]):
        if part.startswith("python3"):
            return "/".join(parts[index + 1 :])
    return "<elsewhere>"


def uid_name(uid: object) -> str:
    """Return the name the standard gives a UID, ``other``, or ``none``.

    A UID that pydicom's dictionary of the standard's UIDs does not hold,
    such as a private SOP Class, is ``other``, so no UID is quoted.

    >>> uid_name("1.2.840.10008.5.1.4.1.1.2")
    'CT Image Storage'
    >>> uid_name("1.2.3.4")
    'other'
    """
    if uid is None:
        return "none"
    text = str(uid).strip(" \x00")
    if not text:
        return "none"
    name = pydicom.uid.UID(text).name
    return name if name and name != text else "other"


def kinds_of(data: bytes) -> tuple[str, str]:
    """Return the SOP Class and transfer syntax of a Part 10 file, by name."""
    try:
        dataset = pydicom.dcmread(
            io.BytesIO(data), stop_before_pixels=True, specific_tags=["SOPClassUID"]
        )
        sop_class = dataset.get("SOPClassUID")
        transfer_syntax = dataset.file_meta.get("TransferSyntaxUID")
    except Exception:  # pylint: disable = broad-exception-caught
        return "unreadable", "unreadable"
    return uid_name(sop_class), uid_name(transfer_syntax)


def describe(error: BaseException) -> tuple[str, str, str]:
    """Return an exception's type, its innermost frame, and its innermost PyMedPhys frame."""
    kind = type(error)
    frames = [
        f"{code_location(frame.filename)}:{frame.lineno} in {frame.name}"
        for frame in traceback.extract_tb(error.__traceback__)
    ]
    ours = [frame for frame in frames if frame.startswith("pymedphys/")]
    return (
        f"{kind.__module__}.{kind.__qualname__}",
        frames[-1] if frames else "none",
        ours[-1] if ours else "none",
    )


class ErrorRecorder:
    """Count the exceptions that a run's transform and gate raise, by kind."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: collections.Counter[tuple[str, ...]] = collections.Counter()

    def _record(self, stage: str, error: BaseException, data: bytes) -> None:
        kind = (stage, *describe(error), *kinds_of(data))
        with self._lock:
            self._counts[kind] += 1

    def transform(self, transform: Transform) -> Transform:
        """Return ``transform``, recording what it raises."""

        def recorded(data: bytes, record: InstanceRecord) -> Transformed | Sequestered:
            try:
                return transform(data, record)
            except Exception as error:
                self._record("transform", error, data)
                raise

        return recorded

    def gate(self, gate: Gate) -> Gate:
        """Return ``gate``, recording what it raises."""

        def recorded(
            written: bytes, evidence: object, subject: tuple[object, ...]
        ) -> Release | HoldForReview | Sequestered:
            try:
                return gate(written, evidence, subject)
            except Exception as error:
                self._record("gate", error, written)
                raise

        return recorded

    def records(self) -> list[dict[str, object]]:
        """Return each kind of error and how many times it was raised, sorted."""
        fields = (
            "stage",
            "exception",
            "raised_at",
            "pymedphys_frame",
            "sop_class",
            "transfer_syntax",
        )
        with self._lock:
            counted = sorted(self._counts.items())
        return [{**dict(zip(fields, kind)), "times": times} for kind, times in counted]


NO_SOP_CLASS_FIELDS = (
    "engine_read",
    "sop_class",
    "media_storage_sop_class",
    "transfer_syntax",
    "specific_character_set",
)
_SOP_CLASS = ElementPath((), "(0008,0016)")


def no_sop_class_cause(path: Path) -> tuple[str, str, str, str, str]:
    """Say, without a value, why the run found no SOP Class UID in a file.

    Returns
    -------
    tuple of str
        Where the engine's reading of SOP Class UID (0008,0016) stopped:
        ``refused: <reason>``, ``data set: <exception>``, ``character set:
        <reason>``, ``absent``, ``undecodable``, ``<n> values``,
        ``empty``, or ``read``; then the SOP Class UID that pydicom reads in
        the data set, the Media Storage SOP Class UID, and the Transfer
        Syntax UID of the File Meta Information, each as :func:`uid_name`
        names it, so that no UID is quoted; and the Specific Character Set,
        each value as the Defined Term it is, or ``other``.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return ("unreadable", "none", "none", "none", "none")
    return (_engine_read(data), *_pydicom_read(path))


def no_sop_class_rows(
    counted: Mapping[tuple[str, ...], int],
) -> list[dict[str, object]]:
    """Return counted causes as rows of :data:`NO_SOP_CLASS_FIELDS`, most first."""
    return [
        {**dict(zip(NO_SOP_CLASS_FIELDS, cause)), "instances": n}
        for cause, n in sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _engine_read(data: bytes) -> str:
    """Read SOP Class UID as the run's transform does, and say how far it got."""
    try:
        source = read_source(data)
    except SourceRefused as refused:
        return f"refused: {getattr(refused.reason, 'value', refused.reason)}"
    dataset = _data_set(source)
    if isinstance(dataset, str):
        return dataset
    if _SOP_CLASS not in source:
        return "absent"
    try:
        values = read_element(dataset, _SOP_CLASS, DEFAULT_CODECS, source=source).values
    except UndecodableElement:
        return "undecodable"
    if len(values) != 1:
        return f"{len(values)} values"
    value = values[0]
    return "read" if isinstance(value, str) and value.strip(" \x00") else "empty"


def _data_set(source: SourceEvidence) -> pydicom.Dataset | str:
    """Return the data set as the transform reads it, with its character set,
    or say where reading stopped; the transform reads no SOP Class UID then."""
    try:
        dataset = source.dataset()
    except (SourceRefused, UndecodableElement) as error:
        return f"data set: {type(error).__name__}"
    try:
        dataset_codecs(dataset, source=source)
    except UndecodableElement as error:
        # Its reason quotes no value.
        return f"character set: {error.reason}"
    except SourceRefused as refused:
        return f"character set: {getattr(refused.reason, 'value', refused.reason)}"
    return dataset


def _pydicom_read(path: Path) -> tuple[str, str, str, str]:
    try:
        dataset = pydicom.dcmread(
            path,
            stop_before_pixels=True,
            specific_tags=["SOPClassUID", "SpecificCharacterSet"],
        )
    except Exception:  # pylint: disable = broad-exception-caught
        return ("unreadable", "unreadable", "unreadable", "unreadable")
    meta = getattr(dataset, "file_meta", None) or pydicom.Dataset()
    sop_class = dataset.get("SOPClassUID")
    return (
        # Several values are not a UID, and are not named.
        "other"
        if isinstance(sop_class, pydicom.multival.MultiValue)
        else uid_name(sop_class),
        uid_name(meta.get("MediaStorageSOPClassUID")),
        uid_name(meta.get("TransferSyntaxUID")),
        _character_set(dataset),
    )


def _character_set(dataset: pydicom.Dataset) -> str:
    """Return a Specific Character Set's terms, without other text.

    Each value is named where it is a Defined Term of PS3.3 Tables C.12-2
    to C.12-5, or ``ISO_IR 6``, which the engine reads too. Any other value
    is ``other``, or ``other like <term>`` where it differs from one of
    them only in case, spaces, hyphens, and underscores, as a misspelt
    term does.
    """
    element = dataset.get((0x0008, 0x0005))
    if element is None:
        return "absent"
    raw = element.value
    values = list(raw) if isinstance(raw, pydicom.multival.MultiValue) else [raw]
    return "\\".join(_term(str(value).strip()) for value in values)


# The Defined Terms of PS3.3 Tables C.12-2 to C.12-5, including the two
# (ISO_IR 203 and ISO 2022 IR 203) that the engine cannot decode, and
# ISO_IR 6, which is not one but names the Default Character Repertoire.
_SINGLE_BYTE = "13 100 101 109 110 126 127 138 144 148 166 203".split()
_NAMED_TERMS = frozenset(
    {
        "ISO_IR 6",
        "ISO_IR 192",
        "GB18030",
        "GBK",
        *(f"ISO_IR {n}" for n in _SINGLE_BYTE),
        *(f"ISO 2022 IR {n}" for n in ("6", *_SINGLE_BYTE, "87", "149", "159", "58")),
    }
)


def _term(value: str) -> str:
    if not value:
        return "empty"
    if value in _NAMED_TERMS:
        return value
    like = sorted(term for term in _NAMED_TERMS if _squeezed(term) == _squeezed(value))
    return f"other like {like[0]}" if like else "other"


def _squeezed(text: str) -> str:
    return "".join(c for c in text.upper() if c not in " -_")
