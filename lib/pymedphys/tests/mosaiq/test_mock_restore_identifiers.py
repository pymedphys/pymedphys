# Copyright (C) 2026 jdotc1

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Check SQL Server restore input validation and SQL literal handling."""

from types import SimpleNamespace
from unittest.mock import Mock

from pymedphys._imports import pytest
from pymedphys._mosaiq.mock import server_from_bak


@pytest.mark.parametrize(
    "database_name",
    [
        "BAD NAME",
        "1bad",
        "",
        "PRACTICE; DROP DATABASE master",
        "PRACTICE' --",
        "PRACTICE] WAITFOR DELAY '00:00:01' --",
        "A" * 129,
        "Ångström",
        None,
        5,
    ],
)
def test_unsafe_restore_database_names_fail_before_docker(
    monkeypatch, tmp_path, database_name
):
    def unexpected_docker_call(*_args, **_kwargs):
        pytest.fail("Invalid database names must not launch Docker")

    monkeypatch.setattr(server_from_bak.subprocess, "call", unexpected_docker_call)
    with pytest.raises(ValueError, match="Invalid database identifier"):
        server_from_bak.start_mssql_docker_image_with_bak_restore(
            tmp_path / "synthetic.bak", "fake-password", database_name=database_name
        )


@pytest.mark.parametrize("database_name", ["PRACTICE", "SELECT", "A" * 128])
def test_restore_quotes_identifiers_and_backup_path(
    monkeypatch, tmp_path, database_name
):
    docker_call = Mock(return_value=0)
    connection = Mock()
    monkeypatch.setattr(server_from_bak.subprocess, "call", docker_call)
    monkeypatch.setattr(
        server_from_bak,
        "pymssql",
        SimpleNamespace(connect=Mock(return_value=connection)),
    )

    bak_filepath = tmp_path / "backup'; DROP TABLE patients;--.bak"
    server_from_bak.start_mssql_docker_image_with_bak_restore(
        bak_filepath, "fake-password", database_name=database_name
    )

    sql = connection.cursor.return_value.execute.call_args.args[0]
    assert f"RESTORE DATABASE [{database_name}]\n" in sql
    assert "FROM DISK = '/mosaiq-data/backup''; DROP TABLE patients;--.bak'" in sql
    assert f"MOVE '{database_name}' TO '/mosaiq-data/data.mdf'" in sql
    assert f"MOVE '{database_name}_log' TO '/mosaiq-data/log.ldf'" in sql
    docker_call.assert_called_once()
    connection.close.assert_called_once()
