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

"""The development command of the text detector check on HaN-Seg (D-037).

Run as ``python -m pymedphys._dicom.deidentify.pixel_text_validation_command``.
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

from . import pixel_text_validation
from .text_detection import TextDetectionError, TextDetector

JSON_NAME = "pixel-text-validation.json"
MARKDOWN_NAME = "pixel-text-validation.md"


def main(argv: Sequence[str] | None = None) -> int:
    """Count the text detector's regions on one image of HaN-Seg's cases.

    ``hanseg`` takes HaN-Seg's ZIP file, ``--image``, ``--out``, a
    directory that must not exist, and ``--workers``, and writes
    :func:`~pymedphys._dicom.deidentify.pixel_text_validation.summarise`'s
    counts there, as ``pixel-text-validation.json`` and
    ``pixel-text-validation.md``, and prints the Markdown. The detector is
    made as a run under the Clean Pixel Data Option makes it, with the
    pinned model, which it downloads on first use, and its default
    parameters.

    Raises
    ------
    SystemExit
        With a refusal's message, or the detector's, which quotes no value,
        and no traceback.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.pixel_text_validation_command",
        description=(
            "Count the regions that the text detector of the Clean Pixel Data "
            "Option finds in a data set's slices, which hold no burned-in "
            "text, and write only counts. For development only."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    hanseg = commands.add_parser(
        "hanseg",
        help=(
            "Count the regions in the HaN-Seg data set's head and neck CT or "
            "MR volumes, read from its ZIP file without extracting it."
        ),
    )
    hanseg.add_argument(
        "archive", help="HaN-Seg.zip, from Zenodo record 7442914, unchanged."
    )
    hanseg.add_argument(
        "--image",
        required=True,
        choices=pixel_text_validation.IMAGES,
        help="Which of each case's images to search.",
    )
    hanseg.add_argument(
        "--out",
        required=True,
        help=(
            "A directory, which must not exist, for pixel-text-validation.json "
            "and pixel-text-validation.md."
        ),
    )
    hanseg.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "How many processes search the volumes, each with a detector of "
            "one thread; they find the same regions as one does. Default 1."
        ),
    )
    arguments = parser.parse_args(argv)
    out = pathlib.Path(arguments.out)
    if out.exists():
        raise SystemExit("The output directory must not exist.")
    try:
        summary = pixel_text_validation.check_hanseg(
            pathlib.Path(arguments.archive),
            arguments.image,
            finder=TextDetector,
            workers=arguments.workers,
        )
    except pixel_text_validation.PixelTextValidationRefused as refused:
        raise SystemExit(str(refused)) from None
    except TextDetectionError as error:
        raise SystemExit(f"The text detector cannot run: {error}.") from None
    except OSError:
        raise SystemExit("The text detector's model could not be read.") from None
    page = pixel_text_validation.markdown(summary)
    out.mkdir(parents=True)
    (out / JSON_NAME).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / MARKDOWN_NAME).write_text(page, encoding="utf-8")
    sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
