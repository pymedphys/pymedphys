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

"""Create a project key for de-identification runs that extend each other.

Run as ``python -m pymedphys._dicom.deidentify.key_command KEY_FILE``. It is
not registered with the ``pymedphys`` command: nothing de-identification
related joins the public command line before the first supported release.

A project key is a new 256-bit key from the operating system's secure
generator, written by :func:`~.keys.write_key_file` to a new file that only
its owner can read, and never inside the PyMedPhys configuration directory
or a directory given with ``--protect``, such as a run's source, release,
and QC pack directories (D-004). The custodian keeps it, with the subject
profile store that runs under it record, for every run of the project, and
gives it to no recipient: anyone who holds it can recompute the replacement
values of candidate identifiers, so it is as sensitive as a map from source
to replacement values. A run takes it with ``--key-file`` only once project
keys are enabled (:data:`~.keys.PROJECT_KEYS_ENABLED`).

The command prints the key's non-secret identifier, which a release report
of a run under the key records, and never the key or the file's path.

Exit statuses:

- :data:`EXIT_CREATED`, 0: the key file was written;
- :data:`EXIT_NOT_CREATED`, 1: nothing was written, because the file
  already exists, lies inside a protected directory, or could not be
  created;
- :data:`EXIT_USAGE`, 2: the arguments could not be parsed, and the message
  quotes none of them.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from . import command
from .command import _Parser, _print
from .keys import DeidKey, DeidKeyError, write_key_file

EXIT_CREATED = 0
EXIT_NOT_CREATED = 1
EXIT_USAGE = command.EXIT_USAGE

_NOT_CREATED = (
    "error: the key file could not be created; its path is not shown, and "
    "nothing was written"
)


def build_parser(*, stderr: TextIO | None = None) -> argparse.ArgumentParser:
    """Return the parser of the command's arguments.

    An argument error prints the usage and a fixed message to ``stderr``,
    by default :data:`sys.stderr`, and exits with :data:`EXIT_USAGE`.
    """
    parser = _Parser(
        prog="python -m pymedphys._dicom.deidentify.key_command",
        stderr=stderr,
        description=(
            "Write a new project key to KEY_FILE, which must not exist, "
            "readable only by its owner. For use before the first supported "
            "release."
        ),
    )
    parser.add_argument(
        "key_file",
        metavar="KEY_FILE",
        help="the new key file, kept by the custodian and never given to recipients",
    )
    parser.add_argument(
        "--protect",
        action="append",
        default=[],
        metavar="DIRECTORY",
        help=(
            "a directory that KEY_FILE must not be inside, such as a run's "
            "source, release, or QC pack; may be given more than once"
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse the arguments, write a new key, and print its identifier.

    Returns
    -------
    int
        The exit status, as the module describes.

    Raises
    ------
    SystemExit
        With :data:`EXIT_USAGE` if the arguments cannot be parsed, or 0 for
        ``--help``, as :mod:`argparse` does.
    """
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    arguments = build_parser(stderr=stderr).parse_args(argv)
    key = DeidKey.generate()
    try:
        write_key_file(arguments.key_file, key, protected_dirs=arguments.protect)
    except (DeidKeyError, OSError):
        _print(_NOT_CREATED, stderr)
        return EXIT_NOT_CREATED
    _print(f"wrote a new project key with identifier {key.key_id}", stdout)
    return EXIT_CREATED


if __name__ == "__main__":
    sys.exit(main())
