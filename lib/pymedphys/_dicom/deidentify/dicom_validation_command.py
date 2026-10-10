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

"""The development command that validates a de-identified release.

Run as ``python -m pymedphys._dicom.deidentify.dicom_validation_command``.
It is not registered with the ``pymedphys`` command: nothing
de-identification related joins the public command line before the first
supported release.

It exits with status 0 when the release passed
(:attr:`~pymedphys._dicom.deidentify.dicom_validation.Comparison.passed`), 1
when it introduced unexplained findings, and 2 when it could not compare,
for example because a validator is missing.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from . import dicom_validation, midi_benchmark, run, standard
from .dicom_validators import ValidatorUnavailable

# The directory of dicom-validator's DocBook source and tables, unless
# --standard-path or this variable names another.
STANDARD_PATH_VARIABLE = "PYMEDPHYS_DICOM_VALIDATOR_STANDARD"
USAGE_ERROR = 2


def default_standard_path() -> Path:
    """Return dicom-validator's directory, from the environment or the home."""
    named = os.environ.get(STANDARD_PATH_VARIABLE)
    if named:
        return Path(named)
    return Path.home() / ".pymedphys" / "dicom-validator"


def main(argv: Sequence[str] | None = None) -> int:
    """Validate a release against its inputs, and print the results.

    ``compare`` takes the inputs, ``--source``, the release, ``--release``,
    and a CSV file mapping SOP Instance UIDs, ``--uid-mapping``. ``midi``
    takes the inputs and the work directory of the MIDI benchmark,
    ``--work``, whose release and UID mapping file it reads. Both write
    ``dicom-validation.json`` and ``dicom-validation.md`` into ``--out``,
    which must not exist, and print the CommonMark.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dicom.deidentify.dicom_validation_command",
        description=(
            "Check each released instance's input and output with dciodvfy, "
            "dcentvfy, and dicom-validator, and report what the "
            "de-identification introduced. For development only."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser(
        "compare", help="Compare a release with its inputs through a UID mapping."
    )
    compare.add_argument("--release", required=True, help="The release directory.")
    compare.add_argument(
        "--uid-mapping",
        required=True,
        help=(
            "A CSV file with the columns id_old and id_new, mapping each "
            "input's SOP Instance UID to its output's."
        ),
    )
    midi = commands.add_parser(
        "midi", help="Compare a MIDI benchmark's release with its inputs."
    )
    midi.add_argument("--work", required=True, help="The benchmark's work directory.")
    for command in (compare, midi):
        command.add_argument("--source", required=True, help="The input files.")
        command.add_argument(
            "--out",
            required=True,
            help="A directory, which must not exist, for the results.",
        )
        command.add_argument(
            "--standard-path",
            type=Path,
            default=None,
            help=(
                "dicom-validator's directory of DocBook source and tables. "
                f"Defaults to ${STANDARD_PATH_VARIABLE}, or "
                "~/.pymedphys/dicom-validator."
            ),
        )
        command.add_argument(
            "--workers",
            type=int,
            default=os.cpu_count() or 1,
            help="Processes that run the per-file validators.",
        )
    arguments = parser.parse_args(argv)
    if arguments.command == "midi":
        work = Path(arguments.work)
        release = work / "release"
        mapping = work / midi_benchmark.SCRIPT_INPUTS / midi_benchmark.UID_MAPPING
    else:
        release = Path(arguments.release)
        mapping = Path(arguments.uid_mapping)
    out = Path(arguments.out)
    if out.exists() or not out.parent.is_dir():
        print(
            "the --out directory must not exist, and its parent must", file=sys.stderr
        )
        return USAGE_ERROR
    if not release.is_dir() or not mapping.is_file():
        print(
            "the release directory or the UID mapping file is missing", file=sys.stderr
        )
        return USAGE_ERROR
    try:
        toolset = dicom_validation.Toolset.find(
            arguments.standard_path or default_standard_path(),
            standard.load_data_dictionary().edition,
        )
        pairs, unpaired = dicom_validation.pairs_from_uid_mapping(
            arguments.source, release, mapping
        )
        comparison = dicom_validation.compare(
            pairs, toolset, unpaired=unpaired, workers=arguments.workers
        )
    except (ValidatorUnavailable, run.RunError) as error:
        print(str(error), file=sys.stderr)
        return USAGE_ERROR
    dicom_validation.write_results(comparison, out)
    sys.stdout.write(comparison.markdown())
    return 0 if comparison.passed else 1


if __name__ == "__main__":
    sys.exit(main())
