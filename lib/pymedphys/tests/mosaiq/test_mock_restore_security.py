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

"""Security regression checks for local mock Mosaiq restoration."""

import subprocess
import types

import pytest

from pymedphys._mosaiq.mock import server_from_bak


@pytest.mark.parametrize("engine_version", ["28.0.0", "28.0.1+build", "29.0.0"])
def test_restored_mosaiq_docker_port_is_loopback_only(
    monkeypatch, tmp_path, engine_version
):
    commands = []
    version_commands = []

    def docker_version(command, **kwargs):
        version_commands.append((command, kwargs))
        return f"{engine_version}\n"

    monkeypatch.setattr(server_from_bak.subprocess, "check_output", docker_version)
    monkeypatch.setattr(
        server_from_bak.subprocess, "call", lambda command: commands.append(command)
    )
    cursor = types.SimpleNamespace(execute=lambda *_args: None)
    connection = types.SimpleNamespace(cursor=lambda: cursor, close=lambda: None)
    monkeypatch.setattr(
        server_from_bak,
        "pymssql",
        types.SimpleNamespace(connect=lambda *_args, **_kwargs: connection),
    )

    server_from_bak.start_mssql_docker_image_with_bak_restore(
        tmp_path / "synthetic.bak", "fake-password"
    )

    assert version_commands == [
        (
            ["docker", "version", "--format", "{{.Server.Version}}"],
            {"text": True, "stderr": subprocess.DEVNULL},
        )
    ]
    (command,) = commands
    assert command[command.index("-p") + 1] == "127.0.0.1:1433:1433"
    assert "1433:1433" not in command


@pytest.mark.parametrize("engine_version", ["27.5.1", "28.0.0-rc.1", "unknown", ""])
def test_restored_mosaiq_rejects_unsafe_or_unknown_engine(
    monkeypatch, tmp_path, engine_version
):
    monkeypatch.setattr(
        server_from_bak.subprocess,
        "check_output",
        lambda *_args, **_kwargs: engine_version,
    )
    monkeypatch.setattr(
        server_from_bak.subprocess,
        "call",
        lambda *_args, **_kwargs: pytest.fail("docker run must not be invoked"),
    )

    with pytest.raises(RuntimeError, match=r"Docker Engine 28\.0\.0 or newer"):
        server_from_bak.start_mssql_docker_image_with_bak_restore(
            tmp_path / "synthetic.bak", "fake-password"
        )


def test_restored_mosaiq_rejects_unverifiable_engine(monkeypatch, tmp_path):
    def fail_docker_version(*_args, **_kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(server_from_bak.subprocess, "check_output", fail_docker_version)
    monkeypatch.setattr(
        server_from_bak.subprocess,
        "call",
        lambda *_args, **_kwargs: pytest.fail("docker run must not be invoked"),
    )

    with pytest.raises(RuntimeError, match=r"Docker Engine 28\.0\.0 or newer"):
        server_from_bak.start_mssql_docker_image_with_bak_restore(
            tmp_path / "synthetic.bak", "fake-password"
        )
