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

"""Tests of the answer key that the NCI validation script is given (D-018).

The answer keys and mapping files are made by hand, with synthetic UIDs, in
the layouts that the script and the harness use.
"""

import json
import sqlite3

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import midi_benchmark_command, midi_script_results

RELEASED = "2.25.101"
WITHHELD = "2.25.102"
WRAPPED = "2.25.103"
REPLACEMENTS = {RELEASED: "2.25.901", WITHHELD: "2.25.902", WRAPPED: "2.25.903"}


def _answer_key(path, sop_instance_uids):
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "CREATE TABLE answer_data "
            "(id INTEGER PRIMARY KEY, SOPInstanceUID TEXT, AnswerData TEXT)"
        )
        connection.execute("CREATE TABLE other (value TEXT)")
        connection.execute("INSERT INTO other VALUES ('SYNTHETIC OTHER')")
        for uid in sop_instance_uids:
            connection.execute(
                "INSERT INTO answer_data (SOPInstanceUID, AnswerData) VALUES (?, ?)",
                [uid, json.dumps({"uid": uid})],
            )
    connection.close()
    return path


def _mapping(path):
    path.write_text(
        "id_old,id_new\n"
        + "".join(f"{old},{new}\n" for old, new in REPLACEMENTS.items()),
        encoding="utf-8",
    )
    return path


def _release(directory, *old_uids):
    directory.mkdir()
    for uid in old_uids:
        (directory / f"{REPLACEMENTS[uid]}.dcm").write_bytes(b"")
    return directory


def _rows(path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT id, SOPInstanceUID, AnswerData FROM answer_data ORDER BY id"
        ).fetchall()
    finally:
        connection.close()


def test_the_released_answer_key_keeps_only_the_released_instances_rows(tmp_path):
    key = _answer_key(tmp_path / "key.db", [RELEASED, WITHHELD, RELEASED])
    out = tmp_path / "released.db"

    counts = midi_script_results.write_released_answer_key(
        key,
        _release(tmp_path / "release", RELEASED),
        _mapping(tmp_path / "uids.csv"),
        out,
    )

    assert counts == {"released_instances": 1, "answer_key_instances": 1, "rows": 2}
    assert _rows(out) == [
        (1, RELEASED, json.dumps({"uid": RELEASED})),
        (3, RELEASED, json.dumps({"uid": RELEASED})),
    ]
    connection = sqlite3.connect(out)
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        connection.close()
    assert tables == [("answer_data",)]


def test_the_released_answer_key_matches_a_wrapped_uid(tmp_path):
    key = _answer_key(tmp_path / "key.db", [f"<{WRAPPED}>", WITHHELD])
    out = tmp_path / "released.db"

    counts = midi_script_results.write_released_answer_key(
        key,
        _release(tmp_path / "release", WRAPPED),
        _mapping(tmp_path / "uids.csv"),
        out,
    )

    assert counts["rows"] == 1
    assert [row[1] for row in _rows(out)] == [f"<{WRAPPED}>"]


def test_an_output_without_a_mapped_input_is_refused(tmp_path):
    release = _release(tmp_path / "release", RELEASED)
    (release / "2.25.999.dcm").write_bytes(b"")

    with pytest.raises(midi_script_results.ScriptResultsError, match="UID mapping"):
        midi_script_results.write_released_answer_key(
            _answer_key(tmp_path / "key.db", [RELEASED]),
            release,
            _mapping(tmp_path / "uids.csv"),
            tmp_path / "released.db",
        )
    assert not (tmp_path / "released.db").exists()


def test_an_existing_destination_is_refused(tmp_path):
    out = tmp_path / "released.db"
    out.write_bytes(b"")

    with pytest.raises(midi_script_results.ScriptResultsError, match="must not exist"):
        midi_script_results.write_released_answer_key(
            _answer_key(tmp_path / "key.db", [RELEASED]),
            _release(tmp_path / "release", RELEASED),
            _mapping(tmp_path / "uids.csv"),
            out,
        )
    assert out.read_bytes() == b""


def test_an_answer_key_without_its_table_is_refused(tmp_path):
    key = tmp_path / "key.db"
    connection = sqlite3.connect(key)
    with connection:
        connection.execute("CREATE TABLE other (value TEXT)")
    connection.close()

    with pytest.raises(midi_script_results.ScriptResultsError, match="answer_data"):
        midi_script_results.write_released_answer_key(
            key,
            _release(tmp_path / "release", RELEASED),
            _mapping(tmp_path / "uids.csv"),
            tmp_path / "released.db",
        )
    assert not (tmp_path / "released.db").exists()


def test_the_command_writes_the_released_answer_key(tmp_path, capsys):
    out = tmp_path / "released.db"

    assert (
        midi_benchmark_command.main(
            [
                "released-answer-key",
                str(_answer_key(tmp_path / "key.db", [RELEASED, WITHHELD])),
                "--release",
                str(_release(tmp_path / "release", RELEASED)),
                "--uid-mapping",
                str(_mapping(tmp_path / "uids.csv")),
                "--out",
                str(out),
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {
        "released_instances": 1,
        "answer_key_instances": 1,
        "rows": 1,
    }
    assert [row[1] for row in _rows(out)] == [RELEASED]
