"""Security regression tests for index.json logfile path resolution."""

import os

import pytest

from pymedphys._utilities.config import get_filepath


def _entry(relative_path):
    return {"synthetic_hash": {"filepath": relative_path}}


def test_get_filepath_preserves_valid_relative_logfile_path(tmp_path):
    expected = tmp_path / "indexed" / "clinic" / "fraction.trf"
    resolved = get_filepath(
        _entry("clinic/fraction.trf"),
        {"linac_logfile_data_directory": str(tmp_path)},
        "synthetic_hash",
    )
    assert resolved == os.path.abspath(expected)


@pytest.mark.parametrize(
    "invalid",
    [
        "../outside.trf",
        "../../outside.trf",
        "/tmp/outside.trf",
    ],
)
def test_get_filepath_rejects_absolute_and_traversal_entries(tmp_path, invalid):
    with pytest.raises(ValueError, match="escapes the indexed directory"):
        get_filepath(
            _entry(invalid),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )


def test_get_filepath_rejects_symlink_alias_outside_root(tmp_path):
    indexed = tmp_path / "indexed"
    indexed.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    try:
        (indexed / "alias").symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks unavailable")

    with pytest.raises(ValueError, match="escapes the indexed directory"):
        get_filepath(
            _entry("alias/clinical.trf"),
            {"linac_logfile_data_directory": str(tmp_path)},
            "synthetic_hash",
        )
