"""Tests for safe MetersetMap report filenames."""

import pathlib

import pytest

from pymedphys._streamlit.apps.metersetmap.main import _report_filename_stem


def test_report_filename_keeps_normal_identifiers():
    assert (
        _report_filename_stem("PAT123", "Plan A", "Delivery B")
        == "PAT123 Plan A vs Delivery B"
    )


@pytest.mark.parametrize(
    ("patient_id", "reference_identifier", "evaluation_identifier"),
    [
        ("../../private", "../outside", "delivery"),
        (r"..\..\private", r"C:\private", "delivery"),
        ("Patient\x00ID", "Plan\nA", "Delivery\tB"),
        ('<patient>:"?', "A*B|C", "D"),
    ],
)
def test_report_filename_confined_to_one_directory(
    tmp_path, patient_id, reference_identifier, evaluation_identifier
):
    stem = _report_filename_stem(
        patient_id, reference_identifier, evaluation_identifier
    )

    assert pathlib.Path(stem).name == stem
    assert "/" not in stem
    assert "\\" not in stem
    assert all(ord(ch) >= 32 for ch in stem)
    assert (tmp_path / stem).resolve().parent == tmp_path.resolve()
