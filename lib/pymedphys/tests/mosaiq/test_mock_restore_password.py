"""Verify the mock Mosaiq Docker invocation does not expose credentials in argv."""

import types

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
    monkeypatch.setattr(
        server_from_bak,
        "pymssql",
        types.SimpleNamespace(connect=lambda *_args, **_kwargs: connection),
    )
    password = "synthetic-not-a-live-password"

    server_from_bak.start_mssql_docker_image_with_bak_restore(
        tmp_path / "synthetic.bak", password
    )

    (command, kwargs), = captured
    assert all(password not in argument for argument in command)
    assert command[command.index("-e", command.index("ACCEPT_EULA=Y")) + 1] == "MSSQL_SA_PASSWORD"
    assert kwargs["env"]["MSSQL_SA_PASSWORD"] == password
