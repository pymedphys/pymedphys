"""Reject glob injection through patient IDs in treatment-file searches."""

from pathlib import Path

import pytest

from pymedphys._streamlit.apps.metersetmap._patient_pattern import escape_patient_id


def test_wildcards_in_patient_ids_are_literal(tmp_path: Path):
    for filename in ("A1_plan.dcm", "A2_plan.dcm", "A[1]_plan.dcm"):
        (tmp_path / filename).touch()
    matches = list(tmp_path.glob(f"{escape_patient_id('A[1]')}_*.dcm"))
    assert [path.name for path in matches] == ["A[1]_plan.dcm"]
    assert list(tmp_path.glob(f"{escape_patient_id('A*')}_*.dcm")) == []


@pytest.mark.parametrize(
    "patient_id",
    ("../else", r"..\else", ".", "..", "one/two", r"one\two", "a\x00b"),
)
def test_patient_id_cannot_supply_path_components(patient_id):
    with pytest.raises(ValueError, match="one literal path component"):
        escape_patient_id(patient_id)
