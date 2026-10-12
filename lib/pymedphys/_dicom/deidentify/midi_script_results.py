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

"""Count the NCI validation script's own results by answer-key category (D-018).

The script writes its results to ``validation_results.db``, a table
``validation_results`` with a row for each check of each instance, its
action, whether it passed (1, 0, or blank), and a column for each
answer-key category that some check has. These are the published figures;
:mod:`~pymedphys._dicom.deidentify.midi_benchmark` counts its own results
by the same categories.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import sqlite3
from pathlib import Path

from .midi_answer_key import Action, Categories, Category, category_of, category_order

SCRIPT_RESULTS_TABLE = "validation_results"


class ScriptResultsError(Exception):
    """Results that cannot be read. The message quotes no value."""


def summarise_script_results(path: str | Path) -> dict[str, object]:
    """Count the validation script's results by answer-key category.

    Parameters
    ----------
    path : str or Path
        The script's ``validation_results.db``.

    Returns
    -------
    dict
        ``categories``: for each category, the checks that the script
        passed, failed, and left blank, ordered as :func:`run_benchmark`
        orders them; and ``results_sha256``, naming the file.

    Raises
    ------
    ScriptResultsError
        If the file is not an SQLite database with the script's table.
    """
    path = Path(path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        connection = sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        raise ScriptResultsError("the validation results could not be read") from None
    try:
        names = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({SCRIPT_RESULTS_TABLE})")
        }
        # The script makes a category's column only where some check has it.
        fields = [
            field.name
            for field in dataclasses.fields(Categories)
            if field.name in names
        ]
        if not {"action", "check_passed"} <= names:
            raise sqlite3.OperationalError
        rows = connection.execute(
            f"SELECT {', '.join(['action', 'check_passed', *fields])} "  # nosec B608
            f"FROM {SCRIPT_RESULTS_TABLE}"
        ).fetchall()
    except sqlite3.Error:
        raise ScriptResultsError(
            f"the validation results have no table {SCRIPT_RESULTS_TABLE!r} "
            "with the script's columns"
        ) from None
    finally:
        connection.close()
    counts: dict[Category | None, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for action_text, passed, *codes in rows:
        name = action_text.strip("<>") if isinstance(action_text, str) else ""
        try:
            action: Action | None = Action(name)
        except ValueError:
            action = None
        categories = Categories(
            **{
                field: code if isinstance(code, str) and code else None
                for field, code in zip(fields, codes)
            }
        )
        outcome = {1: "passed", 0: "failed"}.get(
            int(passed) if isinstance(passed, (int, float)) else -1, "blank"
        )
        counts[category_of(action, categories)][outcome] += 1
    return {
        "results_sha256": digest,
        "categories": [
            {
                "family": None if category is None else category.family,
                "code": None if category is None else category.code,
                "passed": tally["passed"],
                "failed": tally["failed"],
                "blank": tally["blank"],
            }
            for category, tally in sorted(
                counts.items(), key=lambda pair: category_order(pair[0])
            )
        ],
    }
