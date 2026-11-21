"""Keep mock database credentials out of URL parsing ambiguities."""

from pymedphys._imports import pytest
from pymedphys._mosaiq.mock import generate


def test_mock_database_connection_handles_reserved_password_characters(monkeypatch):
    pytest.importorskip("sqlalchemy")
    password = "synthetic@host.invalid:443/with%2Fpercent#fragment"
    monkeypatch.setattr(generate.utilities, "SA_PASSWORD", password)
    observed = []

    class FakeEngine:
        def connect(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def dispose(self):
            observed.append("disposed")

    def fake_create_engine(url, **kwargs):
        assert url.drivername == "mssql+pymssql"
        assert url.username == generate.utilities.SA_USER
        assert url.password == password
        assert url.host == generate.utilities.MSQ_SERVER
        assert url.port == generate.utilities.MSQ_PORT
        assert url.database == "SyntheticDB"
        assert password not in str(url)
        assert kwargs["echo"] is False
        observed.append("connected")
        return FakeEngine()

    monkeypatch.setattr(generate.sqlalchemy, "create_engine", fake_create_engine)

    class FakeFrame:
        def to_sql(self, *_args, **_kwargs):
            observed.append("written")

    generate.dataframe_to_sql(
        FakeFrame(), "Patient", index_label="Pat_ID1", database="SyntheticDB"
    )
    assert observed == ["connected", "written", "disposed"]
