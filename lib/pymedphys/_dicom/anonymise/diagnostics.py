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

"""Keep source values and paths out of the anonymisation entry points' diagnostics.

The ``pymedphys dicom anonymise`` and ``pymedphys experimental dicom
pseudonymise`` commands and the DICOM Pseudonymisation app use these helpers.
The library functions they call are unchanged: their exceptions, and pydicom's
warnings and log records, can still quote file paths and DICOM values.

The redaction itself is the de-identification engine's, in
:mod:`pymedphys._dicom.deidentify.diagnostics`.
"""

from __future__ import annotations

import contextlib
import functools
import sys
from collections.abc import Callable, Iterator
from typing import Any

from pymedphys._dicom.deidentify.diagnostics import (
    REDACTED,
    SUMMARY,
    redacted_diagnostics,
    safe_summary,
)

__all__ = [
    "REDACTED",
    "SUMMARY",
    "redacted_pydicom_diagnostics",
    "report_errors_by_type",
    "safe_summary",
]


@contextlib.contextmanager
def redacted_pydicom_diagnostics() -> Iterator[None]:
    """Keep file paths and DICOM values out of pydicom's warnings and log records.

    Within this context, in the thread that entered it, each record of the
    ``pydicom`` logger or a logger below it has its message replaced by
    :func:`safe_summary`, and each warning is shown with its message
    replaced and its location hidden. No warning filter is added, so other
    code in the same process, such as the other GUI apps, still sees
    pydicom's warnings. See
    :func:`pymedphys._dicom.deidentify.diagnostics.redacted_diagnostics`.
    """
    with redacted_diagnostics():
        yield


def report_errors_by_type(
    command: Callable[[Any], None],
) -> Callable[[Any], None]:
    """Report a command's errors by exception type only, and exit with status 1.

    Exception messages and tracebacks can quote file paths and DICOM values,
    so neither is shown. Directory commands also log the number of the file
    that failed. The command runs within :func:`redacted_pydicom_diagnostics`.
    """

    @functools.wraps(command)
    def run_command(args: Any) -> None:
        with redacted_pydicom_diagnostics():
            try:
                command(args)
            except Exception as error:  # pylint: disable = broad-exception-caught
                print(
                    f"Error: {type(error).__name__}. Details are not shown "
                    "because they can contain file paths or DICOM values.",
                    file=sys.stderr,
                )
                raise SystemExit(1) from None

    return run_command
