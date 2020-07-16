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


# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name
""

import pathlib
import shutil
import tempfile

import streamlit as st

from pymedphys._streamlit import monaco as st_monaco

HERE = pathlib.Path(__file__).parent.resolve()
ANON_DEMOGRAPHIC_FILE = HERE.joinpath("demographic.000000")

"# Anonymise Monaco Files"

(
    monaco_directory,
    patient_id,
    plan_directory,
    patient_directory,
) = st_monaco.monaco_patient_directory_picker(advanced_mode_local=True)

patient_directory

# TODO: Determine output directory


if st.button("Copy and Anonymise"):
    with tempfile.TemporaryDirectory() as temp_dir:
        pl_temp_dir = pathlib.Path(temp_dir)
        new_temp_location = pl_temp_dir.joinpath(patient_directory.name)

        "Copying to temp directory, skipping DICOM files..."

        shutil.copytree(
            patient_directory,
            new_temp_location,
            ignore=shutil.ignore_patterns("*.DCM", "demographic.*"),
        )

        "Creating anonymised demographic file..."

        new_demographic_file = new_temp_location.joinpath(f"demographic.{patient_id}")

        shutil.copy2(ANON_DEMOGRAPHIC_FILE, new_demographic_file)
        with open(new_demographic_file, "r") as f:
            demographic_data = f.readlines()

        demographic_data[3] = demographic_data[3].replace("000000", patient_id)

        with open(new_demographic_file, "w") as f:
            f.writelines(demographic_data)

        "Creating zip file..."

        new_temp_zip_file = pl_temp_dir.joinpath(f"{patient_id}.zip")

        shutil.make_archive(
            str(new_temp_zip_file.with_suffix("")),
            "zip",
            root_dir=str(pl_temp_dir.resolve()),
            base_dir=f"{patient_directory.name}",
        )
