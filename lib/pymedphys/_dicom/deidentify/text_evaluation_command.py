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

"""The development command of the text detector's evaluation (D-056) on
series of NCI's Imaging Data Commons, folders of pinned archives, and
phantoms.

Run as ``python -m pymedphys._dicom.deidentify.text_evaluation_command``,
on CI's runners alone. It is not registered with the ``pymedphys``
command: nothing de-identification related joins the public command line
before the first supported release.

``idc-select``
    reads IDC's index from the pinned idc-index-data wheel and writes the
    selection's counts (``selection.json``), its series (``series.json``),
    and an ``s5cmd`` manifest (``manifest.s5cmd``); with ``--phantoms``, it
    selects series of IDC's phantom collections alone;
``idc-measure``
    measures the downloaded series with a model at today's settings or its
    publishers', and writes the counts-only summary
    (``summary.json`` and ``summary.md``), the per-case report
    (``cases.json``), and the assessment against the chosen criteria
    (``assessment.json``); with ``--converted``, it measures the classic
    CT, MR, and PET series alone, each read as the Legacy Converted
    Enhanced instances that its images convert to;
``idc-parity``
    counts what the resize alone changes for a model at its publishers'
    settings (``parity.json``);
``archive-fetch``
    reads the indexes of the pinned archives on Zenodo and in the
    University of Sydney's data store over HTTP, selects folders of them,
    writes their members under ``--downloads``, and writes the selection's
    counts (``archives.json``);
``phantom-report``
    measures the synthetic phantoms of tier T1 and the downloaded series of
    a ``--phantoms`` selection, of tier T2, that are in the part of the split
    evaluated, and writes, beside the counts-only summary of every case
    (``summary.json`` and ``summary.md``), each case's full report and PNG previews of its
    regions and texts under ``phantoms/``, with ``phantoms/index.json`` and
    ``phantoms/ATTRIBUTION.md``
    (:func:`~.text_evaluation_phantom_report.write_phantom_reports`).

``idc-measure`` and ``idc-parity`` also read, with ``--archives``, the
folders that ``archive-fetch`` wrote, as cases counted only.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .text_detection import TextDetectionError
from .text_evaluation import (
    EVALUATED,
    EvaluationSettings,
    evaluate,
    split_of,
    subject_of,
    summarise,
)
from .text_evaluation_cases import cases_report
from .text_evaluation_converted import ConvertedCase
from .text_evaluation_criteria import CHOSEN_CRITERIA, HELD_OUT_COLLECTIONS, assess
from .text_evaluation_detector import (
    DetectorVariant,
    EvaluationDetector,
    PostProcessing,
    published_point,
    published_variant,
)
from .text_evaluation_frames import EvaluationRefused
from .text_evaluation_idc import (
    PHANTOM_NAMES,
    IdcSeries,
    IdcSeriesCase,
    index_rows,
    manifest,
    select_series,
)
from .text_evaluation_injection import InjectionPlan
from .text_evaluation_lce import TARGETS
from .text_evaluation_markdown import markdown
from .text_evaluation_models import (
    PADDLE_MODELS,
    PP_OCRV6_SMALL,
    RAPIDOCR_MODELS,
    DetectionModel,
)
from .text_evaluation_parity import resize_parity
from .text_evaluation_phantom_report import (
    PhantomSource,
    phantom_dicom_cases,
    write_phantom_reports,
)
from .text_evaluation_phantoms import phantom_cases
from .text_evaluation_sources import DicomCase, SkippedFiles
from .text_evaluation_archives import (
    ARCHIVES,
    archive_index,
    fetch,
    http_opener,
    select_folders,
    archive_cases,
)

MODELS: Mapping[str, DetectionModel] = MappingProxyType(
    {model.name: model for model in (PP_OCRV6_SMALL, *RAPIDOCR_MODELS, *PADDLE_MODELS)}
)
SETTINGS = ("today", "published")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one of the module's commands.

    Raises
    ------
    SystemExit
        With a refusal's message, which quotes no value, and no traceback.
    """
    arguments = _parser().parse_args(argv)
    out = pathlib.Path(arguments.out)
    if out.exists():
        raise SystemExit("The output directory must not exist.")
    try:
        written = arguments.run(arguments)
    except EvaluationRefused as refused:
        raise SystemExit(str(refused)) from None
    except TextDetectionError as error:
        raise SystemExit(f"The text detector cannot run: {error}.") from None
    # A command may have written its own files under the directory, which
    # did not exist before it ran.
    out.mkdir(parents=True, exist_ok=True)
    for name, content in written.items():
        (out / name).write_text(content, encoding="utf-8")
    if "summary.md" in written:
        sys.stdout.write(written["summary.md"])
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.text_evaluation_command",
        description=(
            "Select, and measure the text detector on, openly licensed series "
            "of NCI's Imaging Data Commons, folders of pinned archives, and "
            "phantoms. For development only."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("idc-select", help="Select series from IDC.")
    select.add_argument("wheel", help="idc-index-data's pinned wheel.")
    select.add_argument("--per-collection", type=int, default=3)
    select.add_argument("--max-mb", type=float, default=3000.0)
    select.add_argument("--max-series-mb", type=float, default=1000.0)
    select.add_argument(
        "--downloads",
        default="downloads",
        help="Where the manifest places each series' folder.",
    )
    select.add_argument(
        "--phantoms",
        action="store_true",
        help="Select series of IDC's phantom collections alone.",
    )
    select.set_defaults(run=_select)
    fetched = commands.add_parser(
        "archive-fetch", help="Select and fetch folders of the pinned archives."
    )
    fetched.add_argument("--per-collection", type=int, default=2)
    fetched.add_argument("--max-mb", type=float, default=2000.0)
    fetched.add_argument("--max-folder-mb", type=float, default=400.0)
    fetched.add_argument(
        "--downloads", required=True, help="Where each folder's files are written."
    )
    fetched.set_defaults(run=_archive_fetch)
    for name, run, help_text in (
        ("idc-measure", _measure, "Measure the downloaded series."),
        ("idc-parity", _parity, "Count what the resize alone changes."),
        ("phantom-report", _phantoms, "Report the phantoms in full."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("series", help="series.json, as idc-select wrote it.")
        command.add_argument("downloads", help="Where the series were downloaded.")
        if name != "phantom-report":
            command.add_argument(
                "--archives", help="Where archive-fetch wrote its folders, if it ran."
            )
        command.add_argument(
            "--model", choices=sorted(MODELS), default="PP-OCRv6 small"
        )
        command.add_argument("--evaluated", choices=EVALUATED, default="tuning")
        command.set_defaults(run=run)
        if name in ("idc-measure", "phantom-report"):
            command.add_argument("--settings", choices=SETTINGS, default="today")
            command.add_argument("--workers", type=int, default=1)
        if name == "idc-measure":
            command.add_argument(
                "--converted",
                action="store_true",
                help="Read classic CT, MR, and PET series as converted.",
            )
    for command in commands.choices.values():
        command.add_argument(
            "--out", required=True, help="A directory, which must not exist."
        )
    return parser


def _json(value: object) -> str:
    return json.dumps(value, indent=1) + "\n"


def _select(arguments: argparse.Namespace) -> dict[str, str]:
    selection = select_series(
        index_rows(arguments.wheel),
        per_collection=arguments.per_collection,
        max_mb=arguments.max_mb,
        max_series_mb=arguments.max_series_mb,
        phantoms=arguments.phantoms,
    )
    return {
        "selection.json": _json(selection.described()),
        "series.json": _json([dataclasses.asdict(each) for each in selection.series]),
        "manifest.s5cmd": manifest(selection, arguments.downloads),
    }


def _archive_fetch(arguments: argparse.Namespace) -> dict[str, str]:
    folders = []
    for archive in ARCHIVES:
        # Small blocks, as an index is read from an archive's end alone.
        with http_opener(archive, block=1 << 20) as opened:
            folders += archive_index(archive, opened)
    selection = select_folders(
        folders,
        per_collection=arguments.per_collection,
        max_mb=arguments.max_mb,
        max_folder_mb=arguments.max_folder_mb,
    )
    written = fetch(selection, arguments.downloads)
    return {"archives.json": _json({**selection.described(), "files_written": written})}


def read_series(path: pathlib.Path | str) -> tuple[IdcSeries, ...]:
    """The series that ``idc-select`` wrote, each checked again."""
    try:
        records = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        series = tuple(IdcSeries(**record) for record in records)
    except (OSError, ValueError, TypeError):
        raise EvaluationRefused("The series file is not idc-select's.") from None
    # Each series was checked again as it was made; none may be repeated.
    if len({each.series_instance_uid for each in series}) != len(series):
        raise EvaluationRefused("The series file is not idc-select's.")
    return series


def _cases(
    arguments: argparse.Namespace,
) -> list[IdcSeriesCase | DicomCase | ConvertedCase | SkippedFiles]:
    downloads = pathlib.Path(arguments.downloads)
    converted = getattr(arguments, "converted", False)
    cases: list[IdcSeriesCase | DicomCase | ConvertedCase | SkippedFiles] = [
        IdcSeriesCase(each, downloads, converted=converted)
        for each in read_series(arguments.series)
        if not converted or each.sop_class_uid in TARGETS
    ]
    if getattr(arguments, "archives", None):
        cases += archive_cases(arguments.archives, converted=converted)
    return cases


def _settings(points: tuple[PostProcessing, ...], evaluated: str) -> EvaluationSettings:
    return EvaluationSettings(
        points=points,
        plan=InjectionPlan(),
        evaluated=evaluated,
        held_out_collections=HELD_OUT_COLLECTIONS,
    )


def _detector(
    arguments: argparse.Namespace,
) -> tuple[functools.partial[EvaluationDetector], EvaluationSettings]:
    """The detector that a run measures, made in each worker, and its
    settings, by the model and settings that the arguments name."""
    model = MODELS[arguments.model]
    if arguments.settings == "published":
        variant = published_variant(model)
        points: tuple[PostProcessing, ...] = (published_point(model),)
    else:
        variant = DetectorVariant()
        points = (PostProcessing(),)
    detector = functools.partial(EvaluationDetector, variant, model)
    return detector, _settings(points, arguments.evaluated)


def _measure(arguments: argparse.Namespace) -> dict[str, str]:
    detector, settings = _detector(arguments)
    run = evaluate(_cases(arguments), detector, settings, workers=arguments.workers)
    summary = summarise(run)
    return {
        "summary.json": _json(summary),
        "summary.md": markdown(summary),
        "cases.json": _json(cases_report(run)),
        "assessment.json": _json(assess(summary, CHOSEN_CRITERIA)),
    }


def _parity(arguments: argparse.Namespace) -> dict[str, str]:
    model = MODELS[arguments.model]
    settings = _settings(
        (published_point(model), PostProcessing()), arguments.evaluated
    )
    found = resize_parity(
        _cases(arguments),
        model,
        settings,
        first=published_variant(model, "cv2"),
        second=published_variant(model, "harness"),
    )
    return {"parity.json": _json(found)}


def _phantom_sources(
    arguments: argparse.Namespace,
) -> list[PhantomSource | SkippedFiles]:
    """The synthetic phantoms, and the downloaded series of a ``--phantoms``
    selection, each read only as a phantom collection's files.

    Raises
    ------
    EvaluationRefused
        If any series is not of a phantom collection, before any is read.
    """
    series = read_series(arguments.series)
    if any(each.collection_id not in PHANTOM_NAMES for each in series):
        raise EvaluationRefused("Only a selection of phantoms is reported in full.")
    downloads = pathlib.Path(arguments.downloads)
    sources: list[PhantomSource | SkippedFiles] = list(phantom_cases())
    for each in series:
        name = PHANTOM_NAMES[each.collection_id]
        folder = downloads / each.crdc_series_uuid
        if not folder.is_dir():
            sources.append(
                SkippedFiles(name, each.series_instance_uid, "not-downloaded", 1)
            )
            continue
        sources += phantom_dicom_cases(folder, name)
    return sources


def _in_split(
    sources: Sequence[PhantomSource | SkippedFiles], settings: EvaluationSettings
) -> list[PhantomSource | SkippedFiles]:
    """The sources in the part of the split evaluated, so that no case held
    out is previewed while the detector is tuned."""
    if settings.evaluated == "all":
        return list(sources)
    return [
        each
        for each in sources
        if isinstance(each, SkippedFiles)
        or settings.evaluated
        == split_of(each.collection, subject_of(each), settings.held_out_collections)
    ]


def _phantoms(arguments: argparse.Namespace) -> dict[str, str]:
    detector, settings = _detector(arguments)
    sources = _phantom_sources(arguments)
    # The reports and previews take the part evaluated alone; the summary
    # takes every case, and counts those of each part, as idc-measure does.
    write_phantom_reports(
        _in_split(sources, settings),
        detector,
        settings,
        pathlib.Path(arguments.out) / "phantoms",
    )
    summary = summarise(
        evaluate(sources, detector, settings, workers=arguments.workers)
    )
    return {"summary.json": _json(summary), "summary.md": markdown(summary)}


if __name__ == "__main__":
    sys.exit(main())
