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

import json
import pathlib
import subprocess
import tempfile

from pymedphys._imports import pydicom, pytest

import pymedphys
import pymedphys._utilities.test as pmp_test_utils


@pytest.mark.pydicom
def test_structure_dedupe():
    data_paths = pymedphys.zip_data_paths("structure-deduplication.zip")

    input_paths = [path for path in data_paths if path.parent.name == "input"]

    for input_path in input_paths:
        input_dcm = pydicom.read_file(str(input_path), force=True)

        baseline_path = input_path.parent.parent.joinpath("baseline", input_path.name)
        baseline_dcm = pydicom.read_file(str(baseline_path), force=True)

        input_dcm = _sort_ds(input_dcm)
        baseline_dcm = _sort_ds(baseline_dcm)

        assert str(input_dcm) != str(baseline_dcm)

        roi_contour_sequences = input_dcm.ROIContourSequence

        for item in roi_contour_sequences:
            pymedphys.dicom.merge_contours(item, inplace=True)

        input_dcm = _sort_ds(input_dcm)
        assert str(input_dcm) == str(baseline_dcm)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_filename = str(pathlib.Path(temp_dir).joinpath("temp.dcm"))

            command = pmp_test_utils.get_pymedphys_dicom_cli() + [
                "merge-contours",
                str(input_path),
                output_filename,
            ]
            subprocess.check_call(command)

            cli_dcm = pydicom.read_file(output_filename, force=True)

        cli_dcm = _sort_ds(cli_dcm)
        assert str(cli_dcm) == str(baseline_dcm)


def _sort_ds(ds: "pydicom.Dataset"):
    json_dict = ds.to_json_dict()
    sorted_json_str = json.dumps(json_dict, sort_keys=True)
    return pydicom.dataset.Dataset.from_json(sorted_json_str)
