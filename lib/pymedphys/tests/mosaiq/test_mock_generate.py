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

"""Unit tests for generating the mock Mosaiq database."""

import sys
import types

from pymedphys._imports import pandas as pd
from pymedphys._imports import pytest, sqlalchemy

from pymedphys._mosaiq.mock import generate, paths, utilities


@pytest.mark.parametrize(
    "database", ["invalid-name", "name; DROP DATABASE master", "1database", ""]
)
def test_invalid_database_name_fails_before_connecting(monkeypatch, database):
    def unexpected_connect(*_args, **_kwargs):
        pytest.fail("Invalid database names must not open a server connection")

    fake_pymssql = types.SimpleNamespace(connect=unexpected_connect)
    monkeypatch.setitem(sys.modules, "pymssql", fake_pymssql)

    with pytest.raises(ValueError, match="Invalid database identifier"):
        generate.create_test_db(database)


def test_csv_loader_preserves_nul_text(monkeypatch, tmp_path):
    (tmp_path / "Text.csv").write_text("id,text\n1,before\0after\n", encoding="utf-8")
    monkeypatch.setattr(paths, "DATA", tmp_path)

    assert utilities._load_tables()["Text"]["text"].tolist() == ["before\0after"]


def test_dataframe_to_sql_preserves_nul_text(monkeypatch, tmp_path):
    pytest.importorskip(
        "sqlalchemy", reason="Private mock database generation needs the user extra"
    )
    # Exercise pandas and SQLAlchemy against a real local database. SQLite's
    # equivalent of SQL Server's NCHAR lets the insertion execute here; the
    # observer checks the transport constraint that pymssql imposes.
    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'nul.db'}")
    with engine.connect() as connection:
        connection.connection.driver_connection.create_function("nchar", 1, chr)

    @sqlalchemy.event.listens_for(engine, "before_cursor_execute")
    def require_nul_free_parameters(
        _conn, _cursor, statement, parameters, _context, executemany
    ):
        assert "\0" not in statement
        rows = parameters if executemany else [parameters]
        for row in rows:
            assert all(not isinstance(value, str) or "\0" not in value for value in row)

    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *_args, **_kwargs: engine)
    values = ["ordinary", "\0", "before\0after", "\0\0", "O'Brien\0café", "", None]
    frame = pd.DataFrame({"text": values})
    original = frame.copy(deep=True)

    generate.dataframe_to_sql(frame, "TextRoundTrip", index_label="id")

    with engine.connect() as connection:
        actual = (
            connection.execute(
                sqlalchemy.text('SELECT text FROM "TextRoundTrip" ORDER BY id')
            )
            .scalars()
            .all()
        )
    assert actual == values
    pd.testing.assert_frame_equal(frame, original)
