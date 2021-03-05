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
from pymedphys._imports import plotly, pydicom
from pymedphys._imports import streamlit as st


@st.cache(ttl=3600, suppress_st_warning=True)
def calc_dvh(rs_file, rd_file):
    ds_input: pydicom.FileDataset = pydicom.dcmread(rs_file, force=True)

    dd_input: pydicom.FileDataset = pydicom.dcmread(rd_file, force=True)

    rs = dicomparser.DicomParser(ds_input)

    structures = rs.GetStructures()
    progress_bar = st.progress(0)
    dvh_dict = {}

    for i in range(1, len(structures) + 1):
        calcdvh = dvhcalc.get_dvh(ds_input, dd_input, i)
        dvh_dict[calcdvh.name] = calcdvh
        progress_bar.progress(i / len(structures))

    return dvh_dict


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


# def plot_dvh(rs_file, rd_file):
#     ds_input: pydicom.FileDataset = pydicom.dcmread(rs_file, force=True)
#
#     dd_input: pydicom.FileDataset = pydicom.dcmread(rd_file, force=True)
#     ds_input.save_as('temp_rs_file')
#     dd_input.save_as('temp_rd_file')
#     rs_file_name = os.path.abspath('temp_rs_file')
#     rd_file_name = os.path.abspath('temp_rd_file')
#
#     # dd_input = dvh.DVH.from_data(dd_input.pixel_array, binsize=10)
#
#     rs = dicomparser.DicomParser(ds_input)
#     # rd = dicomparser.DicomParser(rd_file)
#     # rp = dicomparser.DicomParser(rp_file)
#
#     structures = rs.GetStructures()
#     progress_bar = st.progress(0)
#
#     def calculate_dvhs(rs_file, rd_file, i):
#         ds_input: pydicom.FileDataset = pydicom.dcmread(rs_file, force=True)
#
#         dd_input: pydicom.FileDataset = pydicom.dcmread(rd_file, force=True)
#
#         # dd_input = dvh.DVH.from_data(dd_input.pixel_array, binsize=10)
#
#         rs = dicomparser.DicomParser(ds_input)
#         # rd = dicomparser.DicomParser(rd_file)
#         # rp = dicomparser.DicomParser(rp_file)
#
#         structures = rs.GetStructures()
#         dvh_structures = {"name": [], "bincenters": [], "counts": [], "volume": []}
#         # traces = []
#         # fig = plt.subplots()[0]
#         calcdvh = dvhcalc.get_dvh(ds_input, dd_input, i)
#         dvh_structures["name"].append(calcdvh.name)
#         dvh_structures["bincenters"].append(calcdvh.bincenters)
#         dvh_structures["counts"].append(calcdvh.counts)
#         dvh_structures["volume"].append(calcdvh.volume)
#         return dvh_structures
#         # progress_bar.progress(i/len(structures))
#     #     ax.plot(structures[i]['bincenters'], structures[i]['counts']/structures[i]['volume'], label = calcdvh.name)
#     #     ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
#     # ax.set(ylim=(0,1))
#     # st.pyplot(fig)
#     # progress_bar.empty()
#     num_cores= multiprocessing.cpu_count()
#     testing = Parallel(n_jobs=num_cores)(delayed(calculate_dvhs)(rs_file=rs_file_name, rd_file=rd_file_name, i=val) for val in range(1, len(structures) + 1))
#     st.write(testing[7])
#     data = pd.DataFrame.from_dict(dvh_structures)
#     data["rel_volume"] = data["counts"] / data["volume"]
#     d1 = data.explode("bincenters").drop(columns=["counts", "rel_volume"])
#     d2 = data.explode("rel_volume").drop(columns=["name", "bincenters", "volume"])
#
#     data2 = pd.concat([d1, d2], axis=1)
#     # df = px.data.gapminder().query('name')
#     # st.write(df)
#     fig = plotly.express.line(
#         data2, x="bincenters", y="rel_volume", color="name", range_y=[0, 1]
#     )
#     fig.update_layout(
#         title="DVH", yaxis_title="Relative Volume", xaxis_title="Dose [Gy]"
#     )
#     st.plotly_chart(fig, use_container_width=True)
