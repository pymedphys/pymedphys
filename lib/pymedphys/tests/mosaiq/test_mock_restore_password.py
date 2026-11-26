# Copyright (C) 2026 Jeff (jdotc1)

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Verify the mock Mosaiq Docker invocation does not expose credentials in argv."""

import os
import types
from unittest.mock import Mock

from pymedphys._mosaiq.mock import server_from_bak


def test_sql_password_passed_via_environment_not_process_arguments(
    monkeypatch, tmp_path
):
    captured = []

    def fake_docker_call(command, **kwargs):
        captured.append((command, kwargs))
        return 0

    monkeypatch.setattr(server_from_bak.subprocess, "call", fake_docker_call)
    connection = types.SimpleNamespace(
        cursor=lambda: types.SimpleNamespace(execute=lambda *_args: None),
        close=lambda: None,
    )
    connect = Mock(return_value=connection)
    monkeypatch.setattr(
        server_from_bak, "pymssql", types.SimpleNamespace(connect=connect)
    )
    monkeypatch.setenv("MSSQL_SA_PASSWORD", "synthetic-existing-password")
    monkeypatch.setenv("PYMEDPHYS_TEST_INHERITED", "sentinel")
    password = "synthetic-not-a-live-password"

    server_from_bak.start_mssql_docker_image_with_bak_restore(
        tmp_path / "synthetic.bak", password
    )

    ((command, kwargs),) = captured
    assert all(password not in argument for argument in command)
    assert (
        command[command.index("-e", command.index("ACCEPT_EULA=Y")) + 1]
        == "MSSQL_SA_PASSWORD"
    )
    assert kwargs["env"]["MSSQL_SA_PASSWORD"] == password
    assert kwargs["env"]["PYMEDPHYS_TEST_INHERITED"] == "sentinel"
    assert os.environ["MSSQL_SA_PASSWORD"] == "synthetic-existing-password"
    connect.assert_called_once_with(
        "localhost", "sa", password=password, port="1433", autocommit=True
    )
