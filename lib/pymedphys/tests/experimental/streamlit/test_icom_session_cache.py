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

"""Experimental iCOM results stay within the requesting Streamlit session."""

from pymedphys._imports import pandas as pd
from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pandas")
pytest.importorskip("numpy")

from streamlit.testing.v1 import AppTest  # noqa: E402

from pymedphys._experimental.streamlit.utilities import icom  # noqa: E402
from pymedphys._imports import streamlit as st  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_icom_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.mark.parametrize(
    "function_name",
    ["_get_relevant_times", "get_icom_datetimes_meterset_machine", "get_icom_dataset"],
)
def test_icom_caches_reuse_within_session_but_not_between_sessions(
    monkeypatch, function_name
):
    reads = []

    def read_record(path):
        marker = st.session_state["synthetic_marker"]
        reads.append((path, marker))
        return b"000000002026-01-0100:00:00" + marker.encode()

    def extract(item, label):
        values = {"Machine ID": item[26:].decode(), "Delivery MU": 1}
        return item, values.get(label, 0)

    monkeypatch.setattr(icom, "read_icom_log", read_record)
    monkeypatch.setattr(
        icom.pmp_icom_extract, "get_data_points", lambda stream: [stream]
    )
    monkeypatch.setattr(icom.pmp_icom_extract, "extract", extract)
    monkeypatch.setattr(
        icom.pmp_icom_delivery, "get_delivery_data_items", lambda _: [1, 0, 0, [], []]
    )
    monkeypatch.setattr(
        icom,
        "_determine_width_length_centre",
        lambda *_: tuple(
            pd.Series([0], name=name)
            for name in ["width", "length", "centre_x", "centre_y"]
        ),
    )
    script = f"""
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
from pymedphys._experimental.streamlit.utilities import icom
# AppTest otherwise assigns every runner the same fixed session ID.
get_script_run_ctx().session_id = st.session_state["synthetic_marker"]
result = getattr(icom, {function_name!r})({f"synthetic-{function_name}.xz"!r})
if {function_name!r} == "_get_relevant_times":
    marker = result[0]
elif {function_name!r} == "get_icom_datetimes_meterset_machine":
    marker = result[2].iloc[0]
else:
    marker = result["machine_id"].iloc[0]
st.text(marker)
"""
    first = AppTest.from_string(script)
    first.session_state["synthetic_marker"] = "FIRST-SYNTHETIC-SESSION"
    first.run()
    assert not first.exception
    assert first.text[0].value == "FIRST-SYNTHETIC-SESSION"
    initial_reads = len(reads)
    first.run()
    assert len(reads) == initial_reads

    second = AppTest.from_string(script)
    second.session_state["synthetic_marker"] = "SECOND-SYNTHETIC-SESSION"
    second.run()
    assert not second.exception
    assert second.text[0].value == "SECOND-SYNTHETIC-SESSION"
    assert len(reads) > initial_reads

    total_reads = len(reads)
    first.run()
    second.run()
    assert first.text[0].value == "FIRST-SYNTHETIC-SESSION"
    assert second.text[0].value == "SECOND-SYNTHETIC-SESSION"
    assert len(reads) == total_reads
