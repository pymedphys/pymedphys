"""Ensure clinical DBF table reads do not reuse global cached objects."""

import pytest

from pymedphys._experimental.streamlit.utilities import dbf


def test_clinical_dbf_tables_are_loaded_per_call(monkeypatch):
    opened = []

    def fake_dbf(path):
        result = object()
        opened.append(result)
        return result

    monkeypatch.setattr(dbf.dbfread, "DBF", fake_dbf)
    first = dbf.get_dbf_table("clinical.DBF")
    second = dbf.get_dbf_table("clinical.DBF")
    assert first is not second
    assert opened == [first, second]


def test_missing_dbf_exception_hides_sensitive_path(monkeypatch):
    def missing(path):
        raise dbf.dbfread.DBFNotFound(path)

    monkeypatch.setattr(dbf.dbfread, "DBF", missing)
    with pytest.raises(
        FileNotFoundError, match="DBF table could not be opened"
    ) as error:
        dbf.get_dbf_table("/patients/PrivateName/clinical.DBF")
    assert "PrivateName" not in str(error.value)
    assert error.value.__suppress_context__
