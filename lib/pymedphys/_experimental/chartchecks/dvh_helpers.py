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

from pymedphys._imports import dicomparser, dvh, dvhcalc
from pymedphys._imports import pandas as pd
from pymedphys._imports import plotly, plt, pydicom
from pymedphys._imports import streamlit as st


def plot_dvh(rs_file, rd_file):

    ds_input: pydicom.FileDataset = pydicom.dcmread(rs_file, force=True)

    dd_input: pydicom.FileDataset = pydicom.dcmread(rd_file, force=True)

    rs = dicomparser.DicomParser(ds_input)
    # rd = dicomparser.DicomParser(rd_file)
    # rp = dicomparser.DicomParser(rp_file)

    structures = rs.GetStructures()
    dvh_structures = {"name": [], "bincenters": [], "counts": [], "volume": []}
    # traces = []
    fig = plt.subplots()[0]
    for i in range(1, len(structures) + 1):
        calcdvh = dvhcalc.get_dvh(ds_input, dd_input, i)
        dvh_structures["name"].append(calcdvh.name)
        dvh_structures["bincenters"].append(calcdvh.bincenters[0::20])
        dvh_structures["counts"].append(calcdvh.counts[0::20])
        dvh_structures["volume"].append(calcdvh.volume)
    #     ax.plot(structures[i]['bincenters'], structures[i]['counts']/structures[i]['volume'], label = calcdvh.name)
    #     ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    # ax.set(ylim=(0,1))
    # st.pyplot(fig)
    data = pd.DataFrame.from_dict(dvh_structures)
    data["rel_volume"] = data["counts"] / data["volume"]
    d1 = data.explode("bincenters").drop(columns=["counts", "rel_volume"])
    d2 = data.explode("rel_volume").drop(columns=["name", "bincenters", "volume"])

    data2 = pd.concat([d1, d2], axis=1)
    # df = px.data.gapminder().query('name')
    # st.write(df)
    fig = plotly.express.line(
        data2, x="bincenters", y="rel_volume", color="name", range_y=[0, 1]
    )
    fig.update_layout(
        title="DVH", yaxis_title="Relative Volume", xaxis_title="Dose [Gy]"
    )
    st.plotly_chart(fig, use_container_width=True)
