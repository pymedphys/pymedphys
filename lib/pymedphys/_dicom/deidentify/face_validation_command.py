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

"""The development command of the face block check (D-054).

Run as ``python -m pymedphys._dicom.deidentify.face_validation_command``.
It is not registered with the ``pymedphys`` command: nothing
de-identification related joins the public command line before the first
supported release.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

from . import face_validation, face_validation_dicom
from .face_validation_dicom_markdown import markdown as dicom_markdown
from .face_validation_markdown import markdown

JSON_NAME = "face-validation.json"
MARKDOWN_NAME = "face-validation.md"


def main(argv: Sequence[str] | None = None) -> int:
    """Check the face block and CT defacing against a data set's masks,
    or the face block and its holds on a directory of DICOM files.

    ``hanseg`` takes HaN-Seg's ZIP file and ``--out``, a directory that
    must not exist, and writes :func:`~pymedphys._dicom.deidentify.face_validation.summarise`'s
    counts there, as ``face-validation.json`` and ``face-validation.md``,
    and prints the Markdown. ``dicom`` takes a directory of DICOM files and
    ``--out`` likewise, and writes
    :func:`~pymedphys._dicom.deidentify.face_validation_dicom.summarise`'s
    counts.

    Raises
    ------
    SystemExit
        With a refusal's message, which quotes no value, and no traceback;
        for ``dicom``, also with the type and place of anything else that
        the check raises, never its message.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.face_validation_command",
        description=(
            "Check the face block finder and CT defacing of the Clean "
            "Recognizable Visual Features Option against a data set's reference "
            "masks, or on DICOM files, and write only counts. For development "
            "only."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    hanseg = commands.add_parser(
        "hanseg",
        help=(
            "Check against the HaN-Seg data set's head and neck CTs and organ "
            "masks, read from its ZIP file without extracting it."
        ),
    )
    hanseg.add_argument(
        "archive", help="HaN-Seg.zip, from Zenodo record 7442914, unchanged."
    )
    hanseg.add_argument(
        "--out",
        required=True,
        help=(
            "A directory, which must not exist, for face-validation.json and "
            "face-validation.md."
        ),
    )
    dicom = commands.add_parser(
        "dicom",
        help=(
            "Check the face block, its holds, RT Dose defacing, and contour "
            "cutting on a directory of DICOM files, such as a planning "
            "system's CT, RT Structure Set, RT Plan, and RT Dose exports, "
            "rendering nothing."
        ),
    )
    dicom.add_argument(
        "directory", help="The directory of DICOM files, searched below it."
    )
    dicom.add_argument(
        "--out",
        required=True,
        help=(
            "A directory, which must not exist, for face-validation.json and "
            "face-validation.md."
        ),
    )
    arguments = parser.parse_args(argv)
    out = pathlib.Path(arguments.out)
    if out.exists():
        raise SystemExit("The output directory must not exist.")
    try:
        if arguments.command == "dicom":
            summary = _check_dicom(pathlib.Path(arguments.directory))
            page = dicom_markdown(summary)
        else:
            summary = face_validation.check_hanseg(pathlib.Path(arguments.archive))
            page = markdown(summary)
    except face_validation.FaceValidationRefused as refused:
        raise SystemExit(str(refused)) from None
    out.mkdir(parents=True)
    (out / JSON_NAME).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / MARKDOWN_NAME).write_text(page, encoding="utf-8")
    sys.stdout.write(page)
    return 0


def _check_dicom(directory: pathlib.Path) -> dict[str, Any]:
    """The DICOM check's counts.

    Raises
    ------
    FaceValidationRefused
        As :func:`~.face_validation_dicom.check_dicom` does.
    SystemExit
        With the type and place of anything else that it raises, never its
        message, which could quote a value, since this runs where no wrapper
        redacts a traceback.
    """
    try:
        return face_validation_dicom.check_dicom(directory)
    except face_validation.FaceValidationRefused:
        raise
    except Exception as error:  # pylint: disable = broad-exception-caught
        raise SystemExit(
            f"The check stopped: {face_validation.crash_site(error)}."
        ) from None


if __name__ == "__main__":
    sys.exit(main())
