"""Reject unsafe SQL Server restore identifiers before launching Docker."""

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
    ],
)
def test_unsafe_restore_database_names_fail_before_docker(
    monkeypatch, tmp_path, database_name
):
    def unexpected_docker_call(*_args, **_kwargs):
        pytest.fail("Invalid database names must not launch Docker")

    monkeypatch.setattr(
        server_from_bak.subprocess, "call", unexpected_docker_call
    )
    with pytest.raises(ValueError, match="Invalid database identifier"):
        server_from_bak.start_mssql_docker_image_with_bak_restore(
            tmp_path / "synthetic.bak", "fake-password", database_name=database_name
        )
