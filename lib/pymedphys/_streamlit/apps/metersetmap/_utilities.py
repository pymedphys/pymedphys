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


def filter_patient_names(patient_names):
    patient_names = list(set(patient_names))

    if len(patient_names) == 1:
        patient_name = patient_names[0]
    elif len(patient_names) == 0:
        patient_name = ""
    else:
        patient_name = f"Multiple Names Found: f{', '.join(patient_names)}"

    return patient_name
