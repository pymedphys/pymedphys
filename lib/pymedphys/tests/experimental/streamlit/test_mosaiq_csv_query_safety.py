# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""SQL boundaries for the experimental MOSAIQ CSV exporter, without a database."""

from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pandas")

from pymedphys._experimental.streamlit.apps import mosaiq_to_csv as app  # noqa: E402


@pytest.mark.parametrize(
    "table, column",
    [
        ("Patient; DROP TABLE Staff;--", "Pat_ID1"),
        ("Patient]", "Pat_ID1"),
        ("Patient", "Pat_ID1 OR 1=1"),
        ("Patient", "Pat_ID1]"),
        ("NotAnAllowedTable", "Pat_ID1"),
    ],
)
def test_unapproved_identifiers_are_rejected_before_database_access(
    monkeypatch, table, column
):
    def unexpected_database_access(*args, **kwargs):
        pytest.fail("Rejected identifiers must not reach the database")

    monkeypatch.setattr(app, "_get_all_columns", unexpected_database_access)
    monkeypatch.setattr(app.pymedphys.mosaiq, "execute", unexpected_database_access)

    with pytest.raises(ValueError, match="allowlist"):
        app._get_filtered_table.__wrapped__(object(), table, column, "synthetic")


@pytest.mark.parametrize(
    "value", ["SYNTHETIC'; DROP TABLE Patient;--", "SYNTHETIC_%", "SYNTHETIC\nVALUE"]
)
def test_filter_values_remain_bound_parameters(monkeypatch, value):
    connection = object()
    calls = []
    monkeypatch.setattr(
        app, "_get_all_columns", lambda *args: (["Pat_ID1"], ["varchar"])
    )

    def execute(conn, query, parameters):
        calls.append((conn, query, parameters))
        return [(value,)]

    monkeypatch.setattr(app.pymedphys.mosaiq, "execute", execute)
    result = app._get_filtered_table.__wrapped__(
        connection, "Patient", "Pat_ID1", value
    )

    assert len(calls) == 1
    actual_connection, query, parameters = calls[0]
    assert actual_connection is connection
    assert value not in query
    assert "%(column_value)s" in query
    assert parameters["column_value"] == value
    assert result["Pat_ID1"].tolist() == [value]
