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

import json
import subprocess
import traceback
import types

import pytest

from pymedphys._mosaiq.mock import server_from_bak


@pytest.fixture(name="fake_docker")
def docker_fixture(monkeypatch, tmp_path):
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    records = {
        "commands": [],
        "runs": [],
        "version": "28.0.0",
        "containers": {},
        "context_endpoint": "unix:///var/run/docker.sock",
    }

    def check_output(command, **_kwargs):
        records["commands"].append(command)
        if command == ["docker", "context", "show"]:
            return "safe-context\n"
        if command[:3] == ["docker", "context", "inspect"]:
            return records["context_endpoint"]
        if command[-3:] == ["version", "--format", "{{.Server.Version}}"]:
            return records["version"]
        if command[-5:] == [
            "ps",
            "--filter",
            "publish=1433/tcp",
            "--format",
            "{{.ID}}",
        ]:
            return "\n".join(records["containers"])
        if "inspect" in command:
            container_id = command[-1]
            return json.dumps([records["containers"][container_id]])
        raise AssertionError(f"Unexpected Docker command: {command}")

    def run(command, **kwargs):
        records["runs"].append((command, kwargs))
        if records.get("fail_run") and "run" in command:
            raise subprocess.CalledProcessError(125, command)
        if records.get("fail_stop") and "stop" in command:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, stdout="container-id\n")

    monkeypatch.setattr(server_from_bak.subprocess, "check_output", check_output)
    monkeypatch.setattr(server_from_bak.subprocess, "run", run)

    records["connections"] = []
    cursor = types.SimpleNamespace(execute=lambda *_args: None)
    connection = types.SimpleNamespace(cursor=lambda: cursor, close=lambda: None)

    def connect(*args, **kwargs):
        records["connections"].append((args, kwargs))
        return connection

    monkeypatch.setattr(
        server_from_bak, "pymssql", types.SimpleNamespace(connect=connect)
    )
    records["bak_path"] = tmp_path / "synthetic.bak"
    return records


def restore(fake_docker):
    server_from_bak.start_mssql_docker_image_with_bak_restore(
        fake_docker["bak_path"], "synthetic-password"
    )


@pytest.mark.parametrize("engine_version", ["28.0.0", "28.0.1+build", "29.0.0"])
def test_secure_restore_uses_pinned_context_and_loopback(fake_docker, engine_version):
    fake_docker["version"] = engine_version
    restore(fake_docker)
    assert fake_docker["commands"] == [
        ["docker", "context", "show"],
        [
            "docker",
            "context",
            "inspect",
            "safe-context",
            "--format",
            "{{.Endpoints.docker.Host}}",
        ],
        [
            "docker",
            "--host",
            "unix:///var/run/docker.sock",
            "version",
            "--format",
            "{{.Server.Version}}",
        ],
        [
            "docker",
            "--host",
            "unix:///var/run/docker.sock",
            "ps",
            "--filter",
            "publish=1433/tcp",
            "--format",
            "{{.ID}}",
        ],
    ]
    ((command, kwargs),) = fake_docker["runs"]
    assert command[:4] == ["docker", "--host", "unix:///var/run/docker.sock", "run"]
    assert command[command.index("-p") + 1] == "127.0.0.1:1433:1433"
    assert "1433:1433" not in command
    assert kwargs["check"] is True
    assert fake_docker["connections"][0][0][0] == "127.0.0.1"


@pytest.mark.parametrize("engine_version", ["27.5.1", "28.0.0-rc.1", "unknown", ""])
def test_rejects_unsafe_or_unverifiable_version(fake_docker, engine_version):
    fake_docker["version"] = engine_version
    with pytest.raises(RuntimeError, match=r"Docker Engine 28\.0\.0 or newer"):
        restore(fake_docker)
    assert fake_docker["runs"] == []
    assert fake_docker["connections"] == []


def test_unavailable_docker_engine_fails_closed(fake_docker, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(server_from_bak.subprocess, "check_output", unavailable)
    with pytest.raises(
        RuntimeError, match="Cannot determine the active Docker context"
    ):
        restore(fake_docker)
    assert not fake_docker["connections"]


def test_context_switch_does_not_change_selected_daemon(fake_docker, monkeypatch):
    original_check_output = server_from_bak.subprocess.check_output

    def switching_context(command, **kwargs):
        if "version" in command:
            monkeypatch.setenv("DOCKER_CONTEXT", "unsafe-context")
        return original_check_output(command, **kwargs)

    monkeypatch.setattr(server_from_bak.subprocess, "check_output", switching_context)
    restore(fake_docker)
    assert all(
        command[1:3] == ["--host", "unix:///var/run/docker.sock"]
        for command in fake_docker["commands"]
        if "version" in command or "ps" in command
    )
    assert fake_docker["runs"][0][0][1:3] == [
        "--host",
        "unix:///var/run/docker.sock",
    ]


@pytest.mark.parametrize(
    ("variable", "value", "expected_endpoint"),
    [
        ("DOCKER_CONTEXT", "selected", "unix:///var/run/docker.sock"),
        ("DOCKER_HOST", "unix:///tmp/docker.sock", "unix:///tmp/docker.sock"),
    ],
)
def test_environment_selected_target_remains_pinned(
    fake_docker, monkeypatch, variable, value, expected_endpoint
):
    monkeypatch.setenv(variable, value)
    restore(fake_docker)
    assert ["docker", "context", "show"] not in fake_docker["commands"]
    if variable == "DOCKER_CONTEXT":
        assert [
            "docker",
            "context",
            "inspect",
            value,
            "--format",
            "{{.Endpoints.docker.Host}}",
        ] in fake_docker["commands"]
    else:
        assert not any("context" in command for command in fake_docker["commands"])
    assert fake_docker["commands"][-2][:3] == [
        "docker",
        "--host",
        expected_endpoint,
    ]
    assert fake_docker["runs"][0][0][:3] == [
        "docker",
        "--host",
        expected_endpoint,
    ]


@pytest.mark.parametrize(
    "endpoint",
    [
        "ssh://user@remote.example",
        "tcp://remote.example:2376",
        "tcp://127.0.0.1:2375",
        "http://remote.example:2375",
        "",
        "unix:///",
        "npipe:////./pipe/",
    ],
)
def test_rejects_remote_or_invalid_context_before_container_actions(
    fake_docker, endpoint
):
    fake_docker["context_endpoint"] = endpoint
    with pytest.raises(RuntimeError, match="requires a local Docker Engine"):
        restore(fake_docker)
    assert not any("ps" in command for command in fake_docker["commands"])
    assert not fake_docker["runs"]
    assert not fake_docker["connections"]


@pytest.mark.parametrize(
    "endpoint", ["ssh://user@remote.example", "tcp://127.0.0.1:2375"]
)
def test_rejects_remote_docker_host_before_container_actions(
    fake_docker, monkeypatch, endpoint
):
    monkeypatch.setenv("DOCKER_HOST", endpoint)
    with pytest.raises(RuntimeError, match="requires a local Docker Engine"):
        restore(fake_docker)
    assert fake_docker["commands"] == []
    assert not fake_docker["runs"]
    assert not fake_docker["connections"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "unix:///var/run/docker.sock",
        "unix:///home/user/.docker/desktop/docker.sock",
        "npipe:////./pipe/docker_engine",
    ],
)
def test_local_socket_endpoints_remain_supported(fake_docker, endpoint):
    fake_docker["context_endpoint"] = endpoint
    restore(fake_docker)
    assert fake_docker["runs"][0][0][:4] == ["docker", "--host", endpoint, "run"]
    assert len(fake_docker["connections"]) == 1


def test_context_inspection_failure_fails_closed(fake_docker, monkeypatch):
    original_check_output = server_from_bak.subprocess.check_output

    def failing_inspection(command, **kwargs):
        if command[:3] == ["docker", "context", "inspect"]:
            raise subprocess.CalledProcessError(1, command)
        return original_check_output(command, **kwargs)

    monkeypatch.setattr(server_from_bak.subprocess, "check_output", failing_inspection)
    with pytest.raises(RuntimeError, match="Cannot verify the selected Docker"):
        restore(fake_docker)
    assert not fake_docker["runs"]
    assert not fake_docker["connections"]


def old_container(
    fake_docker, image="mcr.microsoft.com/mssql/server:2017-latest", mount=None
):
    return {
        "Config": {"Image": image},
        "Mounts": [
            {
                "Source": str(mount or fake_docker["bak_path"].parent),
                "Destination": "/mosaiq-data",
            }
        ],
        "NetworkSettings": {
            "Ports": {"1433/tcp": [{"HostIp": "0.0.0.0", "HostPort": "1433"}]}
        },
    }


def test_replaces_matching_exposed_legacy_container(fake_docker):
    fake_docker["containers"]["legacy-id"] = old_container(fake_docker)
    restore(fake_docker)
    (stop_command, stop_kwargs), (run_command, run_kwargs) = fake_docker["runs"]
    assert stop_command == [
        "docker",
        "--host",
        "unix:///var/run/docker.sock",
        "stop",
        "legacy-id",
    ]
    assert stop_kwargs["check"] is True
    assert run_command[3] == "run"
    assert run_kwargs["check"] is True
    assert len(fake_docker["connections"]) == 1


def test_does_not_stop_unrelated_container(fake_docker):
    fake_docker["containers"]["unrelated-id"] = old_container(
        fake_docker, image="mcr.microsoft.com/mssql/server:2022-latest"
    )
    with pytest.raises(RuntimeError, match="unrelated container"):
        restore(fake_docker)
    assert fake_docker["runs"] == []
    assert fake_docker["connections"] == []


def test_failed_legacy_stop_aborts_before_connect(fake_docker):
    fake_docker["containers"]["legacy-id"] = old_container(fake_docker)
    fake_docker["fail_stop"] = True
    with pytest.raises(RuntimeError, match="Cannot stop the previous"):
        restore(fake_docker)
    assert len(fake_docker["runs"]) == 1
    assert not fake_docker["connections"]


def test_failed_docker_run_does_not_connect_to_old_service(fake_docker):
    fake_docker["fail_run"] = True
    with pytest.raises(RuntimeError, match="refusing to connect"):
        restore(fake_docker)
    assert fake_docker["connections"] == []


def test_startup_failure_traceback_does_not_disclose_password(fake_docker):
    fake_docker["fail_run"] = True
    with pytest.raises(RuntimeError) as error:
        restore(fake_docker)
    rendered_traceback = "".join(traceback.format_exception(error.value))
    assert "synthetic-password" not in rendered_traceback
