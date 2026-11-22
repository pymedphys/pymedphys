"""Patient lookup must never interpret identifiers as glob patterns."""

from pymedphys._streamlit.apps.metersetmap import _dicom, _icom, _trf


def test_monaco_plan_lookup_uses_literal_patient_id(tmp_path):
    own = tmp_path / "PAT001_plan.dcm"
    other = tmp_path / "PAT002_plan.dcm"
    own.touch()
    other.touch()

    assert _dicom._find_patient_plan_files(tmp_path, "PAT001") == [own]
    assert _dicom._find_patient_plan_files(tmp_path, "PAT*") == []
    assert _dicom._find_patient_plan_files(tmp_path, "../PAT002") == []


def test_icom_lookup_uses_literal_patient_directory(tmp_path):
    own = tmp_path / "PAT001_A" / "20261122_093000.xz"
    other = tmp_path / "PAT002_B" / "20261122_093000.xz"
    for path in (own, other):
        path.parent.mkdir()
        path.touch()

    assert _icom._find_patient_icom_files(tmp_path, "PAT001") == [own]
    assert _icom._find_patient_icom_files(tmp_path, "PAT*") == []
    assert _icom._find_patient_icom_files(tmp_path, "../PAT002") == []


def test_indexed_trf_lookup_uses_literal_patient_directory(tmp_path):
    own = tmp_path / "machine" / "PAT001_A" / "day" / "month" / "time" / "one.trf"
    other = tmp_path / "machine" / "PAT002_B" / "day" / "month" / "time" / "two.trf"
    for path in (own, other):
        path.parent.mkdir(parents=True)
        path.touch()

    assert _trf._find_patient_trf_files(tmp_path, "PAT001") == [own]
    assert _trf._find_patient_trf_files(tmp_path, "PAT*") == []
    assert _trf._find_patient_trf_files(tmp_path, "../PAT002") == []
