# Copyright (C) 2026 jdotc1

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Keep mock database credentials out of URL parsing ambiguities."""

from pymedphys._imports import pytest


def test_mock_database_connection_handles_reserved_password_characters(monkeypatch):
    pytest.importorskip("sqlalchemy")
    from pymedphys._mosaiq.mock import generate

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
        rendered_url = str(url)
        assert password not in rendered_url
        assert "***@" in rendered_url
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
