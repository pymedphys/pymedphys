"""Security regression checks for local mock Mosaiq restoration."""

import types

from pymedphys._mosaiq.mock import server_from_bak


def test_restored_mosaiq_docker_port_is_loopback_only(monkeypatch, tmp_path):
    commands = []
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

    (command,) = commands
    assert command[command.index("-p") + 1] == "127.0.0.1:1433:1433"
    assert "1433:1433" not in command
