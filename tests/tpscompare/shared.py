# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pathlib import Path

HERE = Path(__file__).parent.resolve()
DATA_DIR = HERE.joinpath("data")

DICOM_DIR = DATA_DIR.joinpath("DICOM")
DICOM_DOSE_FILEPATHS = {
    "05x05": DICOM_DIR.joinpath("06MV_05x05.dcm.xz"),
    "10x10": DICOM_DIR.joinpath("06MV_10x10.dcm.xz"),
}
DICOM_PLAN_FILEPATH = DICOM_DIR.joinpath("06MV_plan.dcm")

MEASUREMENTS_DIR = DATA_DIR.joinpath("measurements")


BASELINES_DIR = DATA_DIR.joinpath("baselines")
