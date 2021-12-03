# Copyright (C) 2020 Jacob Rembish

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import dicomparser, dvhcalc
from pymedphys._imports import pandas as pd
from pymedphys._imports import plotly
from pymedphys._imports import streamlit as st


@st.cache(ttl=3600, suppress_st_warning=True)
def calc_dvh(ds_input, dd_input):
    rs = dicomparser.DicomParser(ds_input)

    structures = rs.GetStructures()
    progress_bar = st.progress(0)
    dvh_dict = {}
    dose = st.number_input("Input RX dose in Gy: ")

    for i in range(1, len(structures) + 1):
        calcdvh = dvhcalc.get_dvh(ds_input, dd_input, i)
        calcdvh.rx_dose = dose
        dvh_dict[calcdvh.name] = calcdvh
        progress_bar.progress(i / len(structures))

    return dvh_dict


def calc_reference_isodose_volume(dd_input, reference_dose):

    points_at_reference = 0
    for i in range(0, dd_input.NumberOfFrames):
        points_at_reference += (
            dd_input.pixel_array[i] * dd_input.DoseGridScaling > reference_dose
        ).sum()

    volume_per_voxel = (
        dd_input.SliceThickness
        * dd_input.PixelSpacing[0]
        * dd_input.PixelSpacing[1]
        / 1000
    )
    isodose_volume = points_at_reference * volume_per_voxel

    return isodose_volume


def plot_dvh(dvh_dict):
    dvh_structures = {
        "name": [],
        "bincenters": [],
        "counts": [],
        "volume": [],
    }
    for calcdvh in dvh_dict.values():
        dvh_structures["name"].append(calcdvh.name)
        dvh_structures["bincenters"].append(calcdvh.bincenters)
        dvh_structures["counts"].append(calcdvh.counts)
        dvh_structures["volume"].append(calcdvh.volume)
    data = pd.DataFrame.from_dict(dvh_structures)
    data["rel_volume"] = data["counts"] / data["volume"]
    d1 = data.explode("bincenters").drop(columns=["counts", "rel_volume"])
    d2 = data.explode("rel_volume").drop(columns=["name", "bincenters", "volume"])

    data2 = pd.concat([d1, d2], axis=1)

    fig = plotly.express.line(
        data2, x="bincenters", y="rel_volume", color="name", range_y=[0, 1]
    )
    fig.update_layout(
        title="DVH",
        yaxis_title="Relative Volume",
        xaxis_title="Dose [Gy]",
    )
    st.plotly_chart(fig, use_container_width=True)
