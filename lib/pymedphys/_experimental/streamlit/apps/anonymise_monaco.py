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

""

import pathlib
import shutil
import tempfile

from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories
from pymedphys._streamlit.utilities import config as _config
from pymedphys._streamlit.utilities import misc as st_misc
from pymedphys._streamlit.utilities import monaco as st_monaco

CATEGORY = categories.PRE_ALPHA
TITLE = "Anonymising Monaco Backend Files"

HERE = pathlib.Path(__file__).parent.resolve()
ANON_DEMOGRAPHIC_FILE = HERE.joinpath("data", "demographic.000000")


def main():
    config = _config.get_config()

    st.write("## Select Patient")

    (
        monaco_site,
        _,
        patient_id,
        _,
        patient_directory,
    ) = st_monaco.monaco_patient_directory_picker(config, advanced_mode=True)

    st.write(f"Directory to anonymise: `{patient_directory}`")

    st.write("## Select Export Location")

    _, export_directory = st_misc.get_site_and_directory(
        config,
        "Site to save anonymised zip file",
        "anonymised_monaco",
        default=monaco_site,
        key="export_site",
    )

    st.write(f"Export directory: `{export_directory}`")

    zip_path = pathlib.Path(export_directory).joinpath(f"{patient_id}.zip")

    st.write(f"Zip file to be created: `{zip_path}`")

    if zip_path.exists():
        st.write(FileExistsError("This zip file already exists."))
        if st.button("Delete zip file"):
            zip_path.unlink()
            st.experimental_rerun()

        st.stop()

    if st.button("Copy and Anonymise"):
        with tempfile.TemporaryDirectory() as temp_dir:
            pl_temp_dir = pathlib.Path(temp_dir)
            new_temp_location = pl_temp_dir.joinpath(patient_directory.name)

            st.write("Copying to temp directory, skipping DICOM files...")

            shutil.copytree(
                patient_directory,
                new_temp_location,
                ignore=shutil.ignore_patterns("*.DCM", "demographic.*"),
            )

            st.write("Creating anonymised demographic file...")

            new_demographic_file = new_temp_location.joinpath(
                f"demographic.{patient_id}"
            )

            shutil.copy2(ANON_DEMOGRAPHIC_FILE, new_demographic_file)
            with open(new_demographic_file, "r") as f:
                demographic_data = f.readlines()

            demographic_data[3] = demographic_data[3].replace("000000", patient_id)

            with open(new_demographic_file, "w") as f:
                f.writelines(demographic_data)

            st.write("Creating zip file...")

            shutil.make_archive(
                str(zip_path.with_suffix("")),
                "zip",
                root_dir=str(pl_temp_dir.resolve()),
                base_dir=f"{patient_directory.name}",
            )

            st.write("Complete!")
