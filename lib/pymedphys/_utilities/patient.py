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


def convert_patient_name_from_split(last_name, first_name):
    patient_name = f"{str(last_name).upper()}, {str(first_name).lower().capitalize()}"

    return patient_name


def convert_patient_name(original_patient_name):
    original_patient_name = str(original_patient_name)

    if "^" in original_patient_name:
        patient_split = original_patient_name.split("^")
    elif ", " in original_patient_name:
        patient_split = original_patient_name.split(", ")
    else:
        raise ValueError(
            "Expected input to be either "
            "LASTNAME^FIRSTNAME or LASTNAME, FIRSTNAME. "
            f"Instead got {original_patient_name}"
        )

    patient_name = convert_patient_name_from_split(*patient_split)

    return patient_name
