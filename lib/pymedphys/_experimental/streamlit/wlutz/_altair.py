# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import altair as alt
from pymedphys._imports import streamlit as st


def build_both_axis_altair_charts(table):
    chart_bucket = {}

    for axis in ["y", "x"]:
        raw_chart = _build_altair_chart(table, axis)
        chart_bucket[axis] = st.altair_chart(raw_chart, use_container_width=True)

    return chart_bucket


def _build_altair_chart(table, axis):
    parameters = {
        "x": {
            "column-name": "diff_x",
            "axis-name": "X-axis",
            "plot-type": "Transverse",
        },
        "y": {"column-name": "diff_y", "axis-name": "Y-axis", "plot-type": "Radial"},
    }[axis]

    raw_chart = (
        alt.Chart(table)
        .mark_line(point=True)
        .encode(
            x=alt.X("datetime", axis=alt.Axis(title="Image Time")),
            y=alt.Y(
                parameters["column-name"],
                axis=alt.Axis(
                    title=f"iView {parameters['axis-name']} (mm) [Field - BB]"
                ),
            ),
            color=alt.Color("algorithm", legend=alt.Legend(title="Algorithm")),
            tooltip=["time", "diff_x", "diff_y", "filename", "algorithm"],
        )
    ).properties(title=parameters["plot-type"])

    return raw_chart
