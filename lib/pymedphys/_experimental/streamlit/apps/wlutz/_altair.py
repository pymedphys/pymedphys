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


def build_both_axis_altair_charts(table, plot_x_axis, quiet, xlim=None, ylim=None):
    chart_bucket = {}

    for axis in ["y", "x"]:
        raw_chart = _build_altair_chart(table, axis, plot_x_axis, quiet, xlim, ylim)
        chart_bucket[axis] = st.altair_chart(
            altair_chart=raw_chart, use_container_width=True
        )

    return chart_bucket


def _build_altair_chart(table, axis, plot_x_axis, quiet, xlim, ylim):
    parameters = {
        "x": {
            "column-name": "diff_x",
            "axis-name": "X-axis",
            "plot-type": "Transverse",
        },
        "y": {"column-name": "diff_y", "axis-name": "Y-axis", "plot-type": "Radial"},
    }[axis]

    x_axis_properties = {
        "shorthand": plot_x_axis.lower(),
        "axis": alt.Axis(title=plot_x_axis),
    }

    if xlim is not None:
        x_axis_properties["scale"] = alt.Scale(domain=xlim)

    y_axis_properties = {
        "shorthand": parameters["column-name"],
        "axis": alt.Axis(title=f"iView {parameters['axis-name']} (mm) [Field - BB]"),
    }

    if ylim is not None:
        y_axis_properties["scale"] = alt.Scale(domain=ylim)

    encoding_properties = {
        "x": alt.X(**x_axis_properties),
        "y": alt.Y(**y_axis_properties),
        "color": alt.Color("algorithm", legend=alt.Legend(title="Algorithm")),
        "tooltip": [
            "time",
            "diff_x",
            "diff_y",
            "gantry",
            "collimator",
            "turn_table",
            "filename",
            "algorithm",
        ],
    }

    if quiet:
        del encoding_properties["color"]

    base = alt.Chart(table)

    lines = base.mark_line(point=True, clip=True).encode(**encoding_properties)
    raw_chart = lines.properties(title=parameters["plot-type"]).interactive(
        bind_x=False
    )

    return raw_chart
