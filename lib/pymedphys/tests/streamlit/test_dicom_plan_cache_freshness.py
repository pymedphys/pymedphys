"""Never reuse a stale cached DICOM plan after the file is replaced."""

from types import SimpleNamespace

from pymedphys._streamlit.apps.metersetmap import _dicom


def test_replaced_dicom_plan_is_read_again(monkeypatch):
    reads = iter(
        [
            SimpleNamespace(SOPClassUID=_dicom.DICOM_PLAN_UID, RTPlanName="first"),
            SimpleNamespace(SOPClassUID=_dicom.DICOM_PLAN_UID, RTPlanName="revised"),
        ]
    )
    monkeypatch.setattr(_dicom.pydicom, "dcmread", lambda *args, **kwargs: next(reads))
    assert _dicom.load_dicom_file_if_plan("exported_plan.dcm").RTPlanName == "first"
    assert _dicom.load_dicom_file_if_plan("exported_plan.dcm").RTPlanName == "revised"
