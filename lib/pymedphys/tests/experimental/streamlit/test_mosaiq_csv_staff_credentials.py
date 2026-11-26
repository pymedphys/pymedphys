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

"""Keep source password bytes out of experimental MOSAIQ CSV exports."""

from pymedphys._imports import pandas as pd
from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pandas")

from pymedphys._experimental.streamlit.apps import mosaiq_to_csv as app  # noqa: E402


@pytest.mark.parametrize(
    "passwords",
    [
        [b"SYNTHETIC-PASSWORD-A", b"SYNTHETIC-PASSWORD-B"],
        [None, b"SYNTHETIC-PASSWORD-C"],
    ],
)
def test_every_staff_password_is_replaced_including_unnamed_rows(
    monkeypatch, passwords
):
    source = {
        "Ident": pd.DataFrame({"Pat_Id1": [1]}),
        "Patient": pd.DataFrame(),
        "TxField": pd.DataFrame({"SIT_Set_ID": [1], "FLD_ID": [1]}),
        "Site": pd.DataFrame(),
        "TrackTreatment": pd.DataFrame({"Machine_ID_Staff_ID": [2]}),
        "Chklist": pd.DataFrame(
            {"TSK_ID": [1], "Rsp_Staff_ID": [1], "Com_Staff_ID": [2]}
        ),
        "QCLTask": pd.DataFrame(),
        "Staff": pd.DataFrame(
            {
                "Staff_ID": [1, 2],
                "First_Name": ["Simon", " "],
                "User_Name": ["synthetic-a", "synthetic-b"],
                "PasswordBytes": passwords,
            }
        ),
        "TxFieldPoint": pd.DataFrame(),
    }

    def get_table(connection, types, table, column, values):
        types[table] = {"PasswordBytes": "binary"} if table == "Staff" else {}
        return source[table].copy(deep=True)

    monkeypatch.setattr(app, "get_filtered_table", get_table)
    monkeypatch.setattr(app.st, "write", lambda *_: None)
    tables, types = app._get_all_tables(object(), ["synthetic-id"])
    assert tables["Staff"]["PasswordBytes"].tolist() == [b"\x00" * 15] * 2
    assert source["Staff"]["PasswordBytes"].tolist() == passwords

    app._apply_table_type_conversions_inplace(tables, types)
    csv = tables["Staff"].to_csv(index=False)
    assert "SYNTHETIC-PASSWORD" not in csv
    assert tables["Staff"]["PasswordBytes"].tolist() == ["AAAAAAAAAAAAAAAAAAAA"] * 2
