"""Clinical MOSAIQ lookup values must not be shared via global caches."""

from pymedphys._streamlit.apps.metersetmap import _mosaiq


def test_patient_fields_are_queried_for_each_call(monkeypatch):
    results = iter(["patient-1", "patient-2"])
    monkeypatch.setattr(
        _mosaiq.msq_helpers, "get_patient_fields", lambda *_: next(results)
    )
    connection = object()
    assert _mosaiq.get_patient_fields(connection, "synthetic-id") == "patient-1"
    assert _mosaiq.get_patient_fields(connection, "synthetic-id") == "patient-2"


def test_patient_names_are_queried_for_each_call(monkeypatch):
    results = iter(["before", "after"])
    monkeypatch.setattr(
        _mosaiq.msq_helpers, "get_patient_name", lambda *_: next(results)
    )
    connection = object()
    assert _mosaiq.get_patient_name(connection, "synthetic-id") == "before"
    assert _mosaiq.get_patient_name(connection, "synthetic-id") == "after"
