"""Regression coverage for traversal-safe machine diagnostic directories."""
from pathlib import Path

import pytest

from pymedphys._trf.manage import diagnostics_zips


def test_machine_diagnostic_paths_use_normal_subdirectories(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        diagnostics_zips,
        "fetch_system_diagnostics",
        lambda *args: calls.append(args),
    )
    diagnostics_zips.fetch_system_diagnostics_multi_linac(
        {"Linac A": "192.0.2.10"}, tmp_path
    )
    assert calls == [
        (
            "192.0.2.10",
            str((tmp_path / "to_be_indexed" / "Linac A").resolve()),
            str((tmp_path / "already_indexed" / "Linac A").resolve()),
        )
    ]
    assert (tmp_path / "to_be_indexed" / "Linac A").is_dir()


@pytest.mark.parametrize(
    "machine",
    ["", ".", "..", "../escape", "nested/machine", "/tmp/escape",
     r"..\escape", r"C:\escape", "bad\nmachine", "bad\x00name"],
)
def test_machine_id_cannot_select_another_directory(tmp_path, monkeypatch, machine):
    monkeypatch.setattr(
        diagnostics_zips,
        "fetch_system_diagnostics",
        lambda *_args: pytest.fail("No copy may start for an invalid machine"),
    )
    with pytest.raises(ValueError, match="Machine identifier"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {machine: "192.0.2.10"}, tmp_path
        )


def test_machine_id_cannot_follow_existing_symlink_outside_root(tmp_path, monkeypatch):
    indexed_root = tmp_path / "to_be_indexed"
    indexed_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (indexed_root / "alias").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    monkeypatch.setattr(
        diagnostics_zips,
        "fetch_system_diagnostics",
        lambda *_args: pytest.fail("No copy may start through an unsafe symlink"),
    )
    with pytest.raises(ValueError, match="escapes the diagnostics root"):
        diagnostics_zips.fetch_system_diagnostics_multi_linac(
            {"alias": "192.0.2.10"}, tmp_path
        )
