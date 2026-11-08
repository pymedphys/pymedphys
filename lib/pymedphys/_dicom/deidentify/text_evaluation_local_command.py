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

"""The development command of the text detector's evaluation on a folder of
DICOM files on a person's own machine: T6 of D-056.

Run as ``python -m pymedphys._dicom.deidentify.text_evaluation_local_command
<folder> --out <results>``, on the machine where the files lie, by someone
allowed to use them. It is not registered with the ``pymedphys`` command:
nothing de-identification related joins the public command line before the
first supported release.

It reads the RT Images below the folder (or the SOP Classes asked for), as a
run gives their frames to the text detector
(:func:`~.text_evaluation_sources.dicom_folder_cases`), grouped into cases by
patient and named only by a salted digest. Each frame is measured as read,
its regions counted as regions where text is unknown, apart from false
positives, unless the folder is said to hold no text or someone drew boxes
around its text; then again with synthetic text burned into a copy held in
memory (:func:`~.text_evaluation_injection.inject`), whose pieces are
counted fully covered, partly covered, or missed, in fixed bins of the share
of their ink covered. It writes, into a directory that must not exist and
must lie outside the folder, only the counts-only summary (``summary.json``
and ``summary.md``) and the assessment against the chosen criteria
(``assessment.json``), and prints the page. It renders nothing, writes
nothing beside the files read, and changes none of them.

pydicom's warnings and log records, which could quote a value or a path, are
redacted in every process
(:func:`~.diagnostics.redacted_diagnostics`), and anything that stops the
command is reported by the exception's type and place in the code alone,
since no wrapper redacts a traceback on a person's own machine.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import importlib.util
import json
import multiprocessing
import pathlib
import sys
from collections.abc import Sequence

from .diagnostics import redacted_diagnostics
from .face_validation import crash_site
from .text_detection import TextDetectionError
from .text_evaluation import EVALUATED, EvaluationSettings, evaluate, summarise
from .text_evaluation_command import MODELS, SETTINGS
from .text_evaluation_criteria import CHOSEN_CRITERIA, HELD_OUT_COLLECTIONS, assess
from .text_evaluation_detector import (
    DetectorVariant,
    EvaluationDetector,
    PostProcessing,
    published_point,
    published_variant,
)
from .text_evaluation_font_files import PINNED_FONTS, pinned_font
from .text_evaluation_fonts import FontRefused, PillowBitmapFont
from .text_evaluation_frames import EvaluationRefused
from .text_evaluation_injection import InjectionPlan
from .text_evaluation_markdown import markdown
from .text_evaluation_models import DetectionModel
from .text_evaluation_sources import (
    GROUPINGS,
    RT_IMAGE_STORAGE,
    DicomCase,
    TextAnnotations,
    dicom_folder_cases,
)

DEFAULT_COLLECTION = "local RT Images"
# What may be said of the text of the frames that no annotation covers: by
# default unknown, since a clinic's images may hold text; "none" only where
# the folder is known to hold none, so that each region is a false positive.
KNOWN_TEXT_CHOICES = ("unknown", "none")
# The fonts that the synthetic text is drawn in: the bitmap fonts that the
# evaluation's patients' job on CI draws in, or those and Pillow's bitmap
# font and the pinned fonts under the SIL Open Font License, fetched from
# PyPI on first use.
FONT_CHOICES = ("all", "bitmaps")
WRITTEN = ("assessment.json", "summary.json", "summary.md")


def main(argv: Sequence[str] | None = None) -> int:
    """Measure the text detector on a folder of DICOM files, as the module
    describes.

    Raises
    ------
    SystemExit
        With a refusal's message, which quotes no value or path, or with
        the type and place of anything else that stops the command, never
        its message; and no traceback.
    """
    arguments = _parser().parse_args(argv)
    with redacted_diagnostics():
        try:
            _run(arguments)
        except EvaluationRefused as refused:
            raise SystemExit(str(refused)) from None
        except TextDetectionError as error:
            raise SystemExit(f"The text detector cannot run: {error}.") from None
        # Anything else, a failure to create or write the output among it,
        # is reported by where, never by its message, which could quote a
        # value or a path.
        except Exception as error:  # pylint: disable = broad-exception-caught
            raise SystemExit(f"The command stopped: {crash_site(error)}.") from None
    return 0


def _run(arguments: argparse.Namespace) -> None:
    """Check the paths, measure, and write and print the results."""
    folder = pathlib.Path(arguments.folder)
    out = pathlib.Path(arguments.out)
    if out.exists():
        raise EvaluationRefused("The output directory must not exist.")
    if not folder.is_dir():
        raise EvaluationRefused("The folder to read must be a directory.")
    if out.resolve().is_relative_to(folder.resolve()):
        raise EvaluationRefused(
            "The output directory must lie outside the folder read, which is "
            "left as it was."
        )
    written = measure(arguments)
    out.mkdir(parents=True)
    for name, content in written.items():
        (out / name).write_text(content, encoding="utf-8")
    sys.stdout.write(written["summary.md"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.text_evaluation_local_command",
        description=(
            "Measure the text detector on a folder of DICOM files on your own "
            "machine, by default its RT Images, with synthetic text burned into "
            "copies held in memory, and write only counts. For development only."
        ),
    )
    parser.add_argument(
        "folder", help="The folder of DICOM files, searched below it, read only."
    )
    parser.add_argument(
        "--out",
        required=True,
        help=(
            "A directory, which must not exist and must lie outside the folder, "
            "for summary.json, summary.md, and assessment.json."
        ),
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="What the summary calls these files.",
    )
    classes = parser.add_mutually_exclusive_group()
    classes.add_argument(
        "--sop-class",
        action="append",
        dest="sop_classes",
        metavar="UID",
        help=(
            "A SOP Class UID to read, repeatable; by default RT Image Storage "
            f"({RT_IMAGE_STORAGE}) alone."
        ),
    )
    classes.add_argument(
        "--all-sop-classes",
        action="store_true",
        help="Read the files of every SOP Class.",
    )
    parser.add_argument("--group-by", choices=GROUPINGS, default="patient")
    parser.add_argument(
        "--known-text",
        choices=KNOWN_TEXT_CHOICES,
        default="unknown",
        help=(
            "What is known of the text of frames that no annotation covers: "
            "'none' only where the folder is known to hold no burned-in text."
        ),
    )
    parser.add_argument(
        "--annotations",
        help=(
            "A CSV file of boxes drawn around the text of some instances, with "
            "the columns sop_instance_uid, frame, top, left, bottom, and right."
        ),
    )
    parser.add_argument("--fonts", choices=FONT_CHOICES, default="all")
    parser.add_argument("--model", choices=sorted(MODELS), default="PP-OCRv6 small")
    parser.add_argument("--settings", choices=SETTINGS, default="today")
    parser.add_argument("--evaluated", choices=EVALUATED, default="tuning")
    parser.add_argument("--workers", type=int, default=1)
    return parser


def measure(arguments: argparse.Namespace) -> dict[str, str]:
    """The files that the command writes, by name.

    Raises
    ------
    EvaluationRefused
        For a folder that holds no file to measure, published settings
        that need OpenCV where it is not installed, annotations that
        cannot be read or are not of their form, or a pinned font that cannot be fetched or checked,
        quoting no value.
    """
    annotations = None
    if arguments.annotations is not None:
        try:
            annotations = TextAnnotations.from_csv(arguments.annotations)
        except (OSError, UnicodeDecodeError):
            raise EvaluationRefused("The annotations file cannot be read.") from None
    cases = dicom_folder_cases(
        arguments.folder,
        collection=arguments.collection,
        group_by=arguments.group_by,
        sop_classes=(
            None
            if arguments.all_sop_classes
            else tuple(arguments.sop_classes or (RT_IMAGE_STORAGE,))
        ),
        known_text=arguments.known_text,
        annotations=annotations,
        tier="T6",
    )
    if not any(
        isinstance(each, DicomCase) and each.case != "not-read" for each in cases
    ):
        raise EvaluationRefused("The folder holds no DICOM file of a SOP Class read.")
    model = MODELS[arguments.model]
    if arguments.settings == "published":
        variant = published_variant(model)
        if (
            variant.network_input.resampler == "cv2"
            and importlib.util.find_spec("cv2") is None
        ):
            raise EvaluationRefused(
                "Published settings resize as the model's publishers do, with "
                "OpenCV, which is not installed: install the "
                "opencv-python-headless that .github/text-evaluation/"
                "requirements.txt pins, or use --settings today."
            )
        points: tuple[PostProcessing, ...] = (published_point(model),)
    else:
        variant = DetectorVariant()
        points = (PostProcessing(),)
    try:
        plan = injection_plan(arguments.fonts)
    except (FontRefused, OSError):
        raise EvaluationRefused(
            "A pinned font could not be fetched or checked; pass --fonts "
            "bitmaps to draw the bitmap fonts alone."
        ) from None
    settings = EvaluationSettings(
        points=points,
        plan=plan,
        evaluated=arguments.evaluated,
        held_out_collections=HELD_OUT_COLLECTIONS,
    )
    run = evaluate(
        cases,
        functools.partial(process_detector, variant, model),
        settings,
        workers=arguments.workers,
    )
    summary = summarise(run)
    return {
        "assessment.json": _json(assess(summary, CHOSEN_CRITERIA)),
        "summary.json": _json(summary),
        "summary.md": markdown(summary),
    }


def injection_plan(fonts: str) -> InjectionPlan:
    """The plan of the synthetic text: the plan that the patients' job on CI
    burns in, with, for ``"all"``, Pillow's bitmap font, crisp and smooth,
    and every pinned font beside its bitmap fonts.

    Raises
    ------
    FontRefused
        If a pinned font does not have its pinned SHA-256.
    OSError
        If a pinned font cannot be fetched, such as offline.
    """
    if fonts not in FONT_CHOICES:
        raise EvaluationRefused("The fonts must be a known choice.")
    plan = InjectionPlan()
    if fonts == "bitmaps":
        return plan
    drawn = (
        *plan.fonts,
        PillowBitmapFont(crisp=True),
        PillowBitmapFont(),
        *(pinned_font(each) for each in PINNED_FONTS),
    )
    return InjectionPlan(fonts=drawn)


# The redaction of a worker process, entered once, for the process's life.
WORKER_REDACTION: list[contextlib.ExitStack] = []


def process_detector(
    variant: DetectorVariant, model: DetectionModel
) -> EvaluationDetector:
    """The detector, made once in each process that measures cases; in a
    worker process, which the command's own redaction does not reach, it
    first redacts pydicom's warnings and log records there for the
    process's life, in the thread that measures the cases."""
    if multiprocessing.parent_process() is not None and not WORKER_REDACTION:
        stack = contextlib.ExitStack()
        stack.enter_context(redacted_diagnostics())
        WORKER_REDACTION.append(stack)
    return EvaluationDetector(variant, model)


def _json(value: object) -> str:
    return json.dumps(value, indent=1) + "\n"


if __name__ == "__main__":
    sys.exit(main())
