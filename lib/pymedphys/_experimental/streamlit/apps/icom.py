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


from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc

from pymedphys._experimental.streamlit.utilities import icom as _icom

CATEGORY = categories.PLANNING
TITLE = "iCom Logs Explorer"


def main():
    config = _config.get_config()

    site_directories = _config.get_site_directories(config)
    chosen_site = misc.site_picker(config, "Site")
    icom_directory = site_directories[chosen_site]["icom"]
    icom_patients_directory = icom_directory.joinpath("patients")
    st.write(icom_patients_directory)

    selected_paths_by_date = _icom.get_paths_by_date(icom_patients_directory)

    st.write("## Service mode beam utilisation")

    all_relevant_times = _icom.get_relevant_times_for_filepaths(
        selected_paths_by_date["filepath"]
    )
    _icom.plot_all_relevant_times(all_relevant_times)

    st.write("## Select a time to view specific iCom data")

    times = selected_paths_by_date["datetime"].dt.time
    selected_time = st.selectbox("Time", list(times))

    selected_path_by_time = selected_paths_by_date.loc[selected_time == times]

    if len(selected_path_by_time["filepath"]) != 1:
        raise ValueError("Only one filepath per time supported")

    filepath = selected_path_by_time["filepath"].iloc[0]

    st.write(filepath)

    icom_dataset = _icom.get_icom_dataset(filepath).copy()
    icom_dataset["time"] = icom_dataset["datetime"].dt.time

    st.write(icom_dataset)
