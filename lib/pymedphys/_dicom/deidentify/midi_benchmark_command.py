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

"""The development command of the MIDI benchmark (D-018).

Run as ``python -m pymedphys._dicom.deidentify.midi_benchmark_command``.
It is not registered with the ``pymedphys`` command: nothing
de-identification related joins the public command line before the first
supported release.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import (
    midi_benchmark,
    midi_benchmark_flips,
    midi_benchmark_shards,
    midi_script_results,
    run,
)
from .midi_answer_key import AnswerKeyError, read_answer_key
from .policy import PolicyError
from .safe_private import SafePrivateList


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark, compare two runs, or prepare or count the validation script's run.

    ``run`` takes ``--source``, ``--answer-key``, ``--work``, and optionally
    ``--preset`` or one or more ``--option``, ``--safe-private-list``, ``--collection``, ``--tg263``, ``--watch``, and ``--shard``, as :func:`~pymedphys._dicom.deidentify.midi_benchmark.run_benchmark` does, and
    prints the results as CommonMark. ``combine`` takes every shard's
    ``benchmark.json`` and ``--out``, a directory that must not exist,
    writes :func:`~pymedphys._dicom.deidentify.midi_benchmark_shards.combine`'s
    results there as JSON and CommonMark, and prints the CommonMark. ``flip-check`` takes the answer key,
    ``--reference``, the check outcomes of a run under ``basic``,
    ``--compared``, those of a run under one Retain option alone,
    ``--option``, and ``--out``, writes :func:`~pymedphys._dicom.deidentify.midi_benchmark_flips.flip_check`'s
    results there as JSON, prints them as CommonMark, and exits with 1
    where the check failed or found no effect. ``released-answer-key`` takes the
    answer key, ``--release``, ``--uid-mapping``, and ``--out``, writes :func:`~pymedphys._dicom.deidentify.midi_script_results.write_released_answer_key`'s
    answer key for the script, and prints its counts as JSON.
    ``script-results`` takes the script's ``validation_results.db``, or one
    for each part of a release that it scored in parts, and prints :func:`~pymedphys._dicom.deidentify.midi_script_results.summarise_script_results`'s
    counts as JSON.

    Raises
    ------
    SystemExit
        With a refusal's message, which quotes no value, and no traceback,
        whose status is 1.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.midi_benchmark_command",
        description=(
            "Score the de-identification engine against an NCI MIDI test data "
            "set. For development only."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    benchmark = commands.add_parser(
        "run",
        help=(
            "De-identify a local copy of a MIDI test data set under a preset, "
            "whether enabled or not, and score the release against its answer "
            "key by answer-key category."
        ),
    )
    benchmark.add_argument(
        "--source", required=True, help="The test data set's DICOM files."
    )
    benchmark.add_argument(
        "--answer-key", required=True, help="Its answer key, an SQLite database."
    )
    benchmark.add_argument(
        "--work",
        required=True,
        help=(
            "A directory, which must not exist, for the release, the "
            "confidential QC pack and validation script inputs, and the results."
        ),
    )
    policy = benchmark.add_mutually_exclusive_group()
    policy.add_argument(
        "--preset",
        help=(
            "The preset, enabled or not. Defaults to basic. Under "
            "basic-clean-descriptors, ROI Names are cleaned with the pinned "
            "TG-263 edition, and a name that would be held for review is "
            "emptied. Under Clean Recognizable Visual Features, every instance "
            "that can show a face is held, since a benchmark has no face verdicts."
        ),
    )
    policy.add_argument(
        "--option",
        action="append",
        metavar="OPTION",
        help=(
            "An option of a custom option set, enabled or not, in place of a "
            "preset, such as retain_uids. May be repeated."
        ),
    )
    benchmark.add_argument(
        "--safe-private-list",
        choices=[each.value for each in SafePrivateList],
        default=SafePrivateList.REVIEWED.value,
        help=(
            "Under Retain Safe Private, the list whose rules settle private "
            "attributes: reviewed (the default) or tcia, TCIA's Private Tag "
            "Dictionary."
        ),
    )
    benchmark.add_argument(
        "--collection",
        help="The test data set's name and version, recorded in the results.",
    )
    benchmark.add_argument(
        "--tg263",
        help=(
            "A copy of the pinned TG-263 edition's spreadsheet, for a preset "
            "with Clean Descriptors, in place of PyMedPhys's cached download."
        ),
    )
    benchmark.add_argument(
        "--watch",
        action="append",
        default=[],
        metavar="TAG",
        help=(
            "An attribute, such as (0020,0011), each of whose checks is counted "
            "by where it ended up. May be repeated."
        ),
    )
    benchmark.add_argument(
        "--shard",
        type=_shard,
        metavar="NUMBER/COUNT",
        help=(
            "Run one shard of the run, such as 2/6: the patients that it is "
            "given, balanced by their pixels, and the checks of their "
            "instances. The shards' results are added up with combine."
        ),
    )
    combined = commands.add_parser(
        "combine",
        help=(
            "Add up the results of every shard of one run, write them as JSON "
            "and CommonMark, and print the CommonMark."
        ),
    )
    combined.add_argument(
        "results", nargs="+", help="Each shard's results, benchmark.json."
    )
    combined.add_argument(
        "--out",
        required=True,
        help="A directory, which must not exist, for the combined results.",
    )
    released = commands.add_parser(
        "released-answer-key",
        help=(
            "Copy the answer key's rows for the released instances, for the "
            "NCI validation script, and print the counts as JSON."
        ),
    )
    released.add_argument("answer_key", help="The answer key, an SQLite database.")
    released.add_argument("--release", required=True, help="The run's release.")
    released.add_argument(
        "--uid-mapping", required=True, help="The run's UID mapping file."
    )
    released.add_argument(
        "--out", required=True, help="The new answer key, which must not exist."
    )
    results = commands.add_parser(
        "script-results",
        help=(
            "Count the NCI validation script's results by answer-key category, as JSON."
        ),
    )
    results.add_argument(
        "results",
        nargs="+",
        help=(
            "The script's validation_results.db, or one for each part of a "
            "release that it scored in parts."
        ),
    )
    flips = commands.add_parser(
        "flip-check",
        help=(
            "Compare a run under basic with one under a Retain option alone, "
            "check by check, write the results as JSON, and print them as "
            "CommonMark."
        ),
    )
    flips.add_argument("answer_key", help="The answer key, an SQLite database.")
    flips.add_argument(
        "--reference",
        required=True,
        help="The check outcomes of the run under basic, check-outcomes.txt.",
    )
    flips.add_argument(
        "--compared",
        required=True,
        help="The check outcomes of the run under the option alone.",
    )
    flips.add_argument("--option", required=True, help="The Retain option.")
    flips.add_argument(
        "--out", required=True, help="The results' JSON file, which must not exist."
    )
    arguments = parser.parse_args(argv)
    status = 0
    try:
        if arguments.command == "run":
            text = midi_benchmark.run_benchmark(
                arguments.source,
                arguments.answer_key,
                arguments.work,
                preset=arguments.preset,
                options=arguments.option,
                safe_private_list=SafePrivateList(arguments.safe_private_list),
                collection=arguments.collection,
                tg263_spreadsheet=arguments.tg263,
                watched=arguments.watch,
                shard=arguments.shard,
            ).markdown()
        elif arguments.command == "combine":
            text = _combine(arguments)
        elif arguments.command == "released-answer-key":
            text = (
                json.dumps(
                    midi_script_results.write_released_answer_key(
                        arguments.answer_key,
                        arguments.release,
                        arguments.uid_mapping,
                        arguments.out,
                    ),
                    indent=2,
                )
                + "\n"
            )
        elif arguments.command == "flip-check":
            text, status = _flip_check(arguments)
        else:
            text = (
                json.dumps(
                    midi_script_results.summarise_script_results(
                        # One file is named by one digest, as before.
                        arguments.results
                        if len(arguments.results) > 1
                        else arguments.results[0]
                    ),
                    indent=2,
                )
                + "\n"
            )
    except (
        midi_benchmark.BenchmarkError,
        midi_benchmark_flips.FlipCheckError,
        midi_benchmark_shards.ShardError,
        midi_script_results.ScriptResultsError,
        AnswerKeyError,
        PolicyError,
        run.RunError,
        run.RunStopped,
    ) as error:
        raise SystemExit(str(error)) from None
    sys.stdout.write(text)
    return status


def _shard(text: str) -> midi_benchmark_shards.Shard:
    try:
        return midi_benchmark_shards.Shard.parse(text)
    except midi_benchmark_shards.ShardError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _combine(arguments: argparse.Namespace) -> str:
    """Combine the shards' results, write them, and return the CommonMark."""
    out = Path(arguments.out)
    if out.exists() or not out.parent.is_dir():
        raise midi_benchmark_shards.ShardError(
            "the combined results' directory must not exist, and its parent must"
        )
    documents = []
    for each in arguments.results:
        try:
            document = json.loads(Path(each).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise midi_benchmark_shards.ShardError(
                "a shard's results could not be read"
            ) from None
        if not isinstance(document, dict):
            raise midi_benchmark_shards.ShardError("a file is not a shard's results")
        documents.append(document)
    combined = midi_benchmark.Benchmark(midi_benchmark_shards.combine(documents), b"")
    out.mkdir()
    (out / midi_benchmark.RESULTS_JSON).write_text(
        combined.json(), encoding="utf-8", newline="\n"
    )
    text = combined.markdown()
    (out / midi_benchmark.RESULTS_MARKDOWN).write_text(
        text, encoding="utf-8", newline="\n"
    )
    return text


def _flip_check(arguments: argparse.Namespace) -> tuple[str, int]:
    """Run a flip check, write its JSON, and return its CommonMark and status."""
    out = Path(arguments.out)
    if out.exists():
        raise midi_benchmark_flips.FlipCheckError("the results file must not exist")
    document = midi_benchmark_flips.flip_check(
        read_answer_key(arguments.answer_key),
        midi_benchmark_flips.read_check_outcomes(arguments.reference),
        midi_benchmark_flips.read_check_outcomes(arguments.compared),
        arguments.option,
    )
    out.write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return (
        midi_benchmark_flips.render_markdown(document),
        0 if midi_benchmark_flips.passed(document) else 1,
    )


if __name__ == "__main__":
    sys.exit(main())
