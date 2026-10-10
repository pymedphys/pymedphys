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

from . import midi_benchmark, midi_script_results, run
from .midi_answer_key import AnswerKeyError
from .policy import PolicyError


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark, or count the validation script's results.

    ``run`` takes ``--source``, ``--answer-key``, ``--work``, and optionally
    ``--preset``, ``--collection``, and ``--tg263``, as :func:`~pymedphys._dicom.deidentify.midi_benchmark.run_benchmark` does, and
    prints the results as CommonMark. ``script-results`` takes the script's
    ``validation_results.db`` and prints :func:`~pymedphys._dicom.deidentify.midi_script_results.summarise_script_results`'s
    counts as JSON.

    Raises
    ------
    SystemExit
        With a refusal's message, which quotes no value, and no traceback.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.midi_benchmark_command",
        description=(
            "Score the de-identification engine against an NCI MIDI test data "
            "set (D-018). For development only."
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
    benchmark.add_argument(
        "--preset",
        default="basic",
        help=(
            "The preset, enabled or not. Defaults to basic. Under "
            "basic-clean-descriptors, ROI Names are cleaned with the pinned "
            "TG-263 edition, and a name that would be held for review is emptied."
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
    results = commands.add_parser(
        "script-results",
        help=(
            "Count the NCI validation script's results by answer-key category, as JSON."
        ),
    )
    results.add_argument("results", help="The script's validation_results.db.")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "run":
            text = midi_benchmark.run_benchmark(
                arguments.source,
                arguments.answer_key,
                arguments.work,
                preset=arguments.preset,
                collection=arguments.collection,
                tg263_spreadsheet=arguments.tg263,
            ).markdown()
        else:
            text = (
                json.dumps(
                    midi_script_results.summarise_script_results(arguments.results),
                    indent=2,
                )
                + "\n"
            )
    except (
        midi_benchmark.BenchmarkError,
        midi_script_results.ScriptResultsError,
        AnswerKeyError,
        PolicyError,
        run.RunError,
        run.RunStopped,
    ) as error:
        raise SystemExit(str(error)) from None
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
