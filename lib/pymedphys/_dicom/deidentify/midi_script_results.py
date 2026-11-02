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

"""Give the NCI validation script its answer key, and count its results (D-018).

The script writes its results to ``validation_results.db``, a table
``validation_results`` with a row for each check of each instance, its
action, whether it passed (1, 0, or blank), and a column for each
answer-key category that some check has. These are the published figures;
:mod:`~pymedphys._dicom.deidentify.midi_benchmark` counts its own results
by the same categories.

The script scores every answer-key instance that has no file in the release
as missing, and holds the result of every check in memory until it writes
them all. Where a run withholds most instances, as on MIDI-B's Test subset,
that ran a 16 GB runner out of memory. :func:`write_released_answer_key`
gives it only the released instances' rows instead: it looks up each file's
rows by the file's SOP Instance UID, so it scores the released files as it
would have, and the harness reports the withheld instances itself. Where
most instances are released, the results alone fill the memory, so the
workflow scores the release in parts, each with its own answer key, and
:func:`summarise_script_results` adds up the parts' results.
"""

from __future__ import annotations

import collections
import csv
import dataclasses
import hashlib
import io
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .midi_answer_key import (
    ANSWER_TABLE,
    Action,
    Categories,
    Category,
    category_of,
    category_order,
)

SCRIPT_RESULTS_TABLE = "validation_results"
UID_MAPPING = "uid_mapping.csv"
PATIENT_ID_MAPPING = "patid_mapping.csv"


class ScriptResultsError(Exception):
    """Results that cannot be read, or an answer key that cannot be written
    for the script. The message quotes no value."""


def summarise_script_results(
    paths: str | Path | Sequence[str | Path],
) -> dict[str, object]:
    """Count the validation script's results by answer-key category.

    Parameters
    ----------
    paths : str, Path, or sequence of them
        The script's ``validation_results.db``, or one for each part of a
        release that it scored in parts.

    Returns
    -------
    dict
        ``categories``: for each category, the checks that the script
        passed, failed, and left blank, over every file, ordered as
        :func:`run_benchmark` orders them; and ``results_sha256``, naming
        the file, or a list naming each file in the order given.

    Raises
    ------
    ScriptResultsError
        If no file is given, or a file is not an SQLite database with the
        script's table.
    """
    if isinstance(paths, (str, Path)):
        several, files = False, [Path(paths)]
    else:
        several, files = True, [Path(path) for path in paths]
    if not files:
        raise ScriptResultsError("no validation results were given")
    counts: dict[Category | None, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    digests = [_count_script_results(path, counts) for path in files]
    return {
        "results_sha256": digests if several else digests[0],
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


def _count_script_results(
    path: Path, counts: dict[Category | None, collections.Counter]
) -> str:
    """Add one results file's checks to ``counts``, and return its digest."""
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
    return digest


def write_mapping_files(
    directory: Path, uids: Mapping[str, str], patient_ids: Mapping[str, str]
) -> None:
    """Write the script's UID and Patient ID mapping files into a new directory.

    Each maps the test data's identifiers to their replacements, with the
    columns ``id_old`` and ``id_new``, and only its owner may read it.
    """
    directory.mkdir(mode=0o700)
    for name, pairs in ((UID_MAPPING, uids), (PATIENT_ID_MAPPING, patient_ids)):
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(("id_old", "id_new"))
        writer.writerows(pairs.items())
        descriptor = os.open(
            directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with open(descriptor, "w", encoding="utf-8", newline="") as file:
            file.write(text.getvalue())


def write_released_answer_key(
    answer_key: str | Path,
    release: str | Path,
    uid_mapping: str | Path,
    destination: str | Path,
) -> dict[str, int]:
    """Copy the answer key's rows for the released instances, for the script.

    Parameters
    ----------
    answer_key : str or Path
        The answer key, an SQLite database with the table ``answer_data``.
    release : str or Path
        The release, or links to its files, each with the suffix ``.dcm``.
        Each file's SOP Instance UID is read from the file, not its name:
        under Retain UIDs, a file holds its source's UID but is named by
        that UID's keyed replacement.
    uid_mapping : str or Path
        The harness's UID mapping file, with the columns ``id_old`` and
        ``id_new``.
    destination : str or Path
        The new answer key, which must not exist. It holds the table
        ``answer_data`` alone, with its rows for the released instances.

    Returns
    -------
    dict
        ``released_instances``, the files in the release;
        ``answer_key_instances``, the released instances that the answer key
        has rows for; and ``rows``, the rows copied. They hold no value.

    Raises
    ------
    ScriptResultsError
        If the destination exists, a released file's SOP Instance UID
        cannot be read, the mapping lacks a column or a released file, or
        the answer key has no table ``answer_data``. Nothing is written
        then.
    """
    destination = Path(destination)
    if destination.exists():
        raise ScriptResultsError("the new answer key must not exist")
    released = _released_inputs(Path(release), Path(uid_mapping))
    try:
        connection = sqlite3.connect(
            f"{destination.absolute().as_uri()}?mode=rwc", uri=True
        )
    except sqlite3.Error:
        raise ScriptResultsError("the new answer key could not be written") from None
    try:
        counts = _copy_released_rows(connection, Path(answer_key), released)
    except BaseException:
        connection.close()
        destination.unlink(missing_ok=True)
        raise
    connection.close()
    return counts


def _released_inputs(release: Path, uid_mapping: Path) -> set[str]:
    """Return the input SOP Instance UIDs of the release's files."""
    try:
        with open(uid_mapping, encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            if not {"id_old", "id_new"} <= set(reader.fieldnames or ()):
                raise ScriptResultsError(
                    "the UID mapping needs the columns id_old and id_new"
                )
            inputs = {row["id_new"]: row["id_old"] for row in reader}
        paths = [path for path in release.rglob("*.dcm") if path.is_file()]
    except OSError:
        raise ScriptResultsError(
            "the release or the UID mapping could not be read"
        ) from None
    with redacted_diagnostics():
        outputs = [_stored_uid(path) for path in paths]
    if None in outputs:
        raise ScriptResultsError("a released file's SOP Instance UID could not be read")
    if any(output not in inputs for output in outputs):
        raise ScriptResultsError(
            "the release has a file that the UID mapping maps from no input"
        )
    return {inputs[output] for output in outputs}


def _stored_uid(path: Path) -> str | None:
    """Return the SOP Instance UID that a released file holds, or None."""
    try:
        dataset = pydicom.dcmread(
            path, stop_before_pixels=True, specific_tags=["SOPInstanceUID"]
        )
        value = dataset.get("SOPInstanceUID")
    except Exception:  # pylint: disable = broad-exception-caught
        # Any file that cannot be read is refused; the message names none.
        return None
    text = None if value is None else str(value).strip(" \x00")
    return text or None


def _copy_released_rows(
    connection: sqlite3.Connection, answer_key: Path, released: set[str]
) -> dict[str, int]:
    try:
        connection.execute(
            "ATTACH DATABASE ? AS answer_key",
            (f"{answer_key.absolute().as_uri()}?mode=ro",),
        )
        schema = connection.execute(
            "SELECT sql FROM answer_key.sqlite_master "
            "WHERE type = 'table' AND name = ?",
            (ANSWER_TABLE,),
        ).fetchone()
    except sqlite3.Error:
        raise ScriptResultsError("the answer key is not an SQLite database") from None
    if schema is None:
        raise ScriptResultsError(f"the answer key has no table {ANSWER_TABLE!r}")
    try:
        with connection:
            connection.execute(schema[0])
            connection.execute("CREATE TEMP TABLE released (uid TEXT PRIMARY KEY)")
            # The script reads identifiers as they are stored, which may be
            # wrapped in angle brackets, as its other values are.
            connection.executemany(
                "INSERT OR IGNORE INTO released VALUES (?)",
                [(form,) for uid in released for form in (uid, f"<{uid}>")],
            )
            connection.execute(
                f"INSERT INTO main.{ANSWER_TABLE} "  # nosec B608
                f"SELECT * FROM answer_key.{ANSWER_TABLE} "
                "WHERE SOPInstanceUID IN (SELECT uid FROM released)"
            )
        rows, instances = connection.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT SOPInstanceUID) "  # nosec B608
            f"FROM main.{ANSWER_TABLE}"
        ).fetchone()
    except sqlite3.Error:
        raise ScriptResultsError(
            f"the answer key's table {ANSWER_TABLE!r} could not be copied"
        ) from None
    return {
        "released_instances": len(released),
        "answer_key_instances": instances,
        "rows": rows,
    }
