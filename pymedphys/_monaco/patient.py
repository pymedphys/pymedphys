# Copyright (C) 2019 Cancer Care Associates and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pathlib

from pymedphys._utilities import patient as pmp_util_patient

from . import utility


def read_patient_name(patient_directory):
    patient_directory = pathlib.Path(patient_directory)
    patient_id = str(patient_directory.name).split("~")[1]
    demographic_file = patient_directory.joinpath(f"demographic.{patient_id}")

    if not demographic_file.exists():
        raise ValueError(
            f"Could not find demographic file at the location {str(demographic_file)}"
        )

    read_monaco_file = utility.create_read_monaco_file()

    contents = read_monaco_file(demographic_file)
    patient_name = contents.split("\n")[2]

    try:
        patient_name = pmp_util_patient.convert_patient_name(patient_name)
    except:  # pylint: disable = bare-except
        pass

    return patient_name
