# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2020 South Western Sydney Local Health District,
# University of New South Wales

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This work is derived from:
# https://github.com/AndrewWAlexander/Pinnacle-tar-DICOM
# which is released under the following license:

# Copyright (c) [2017] [Colleen Henschel, Andrew Alexander]

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# pylint: disable = redefined-outer-name

import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._data import download
from pymedphys._utilities import test as pmp_test_utils

working_path = tempfile.mkdtemp()
data_path = os.path.join(working_path, "data")


def get_online_data(filename):
    return download.get_file_within_data_zip("pinnacle_test_data.zip", filename)


@pytest.fixture(scope="session")
def data():
    zip_ref = ZipFile(get_online_data("pinnacle_16.0_test_data.zip"), "r")
    zip_ref.extractall(data_path)
    zip_ref.close()

    return Path(data_path)


@pytest.mark.slow
def test_pinnacle_cli_output(data):
    output_path = tempfile.mkdtemp()

    for pinn_dir in data.joinpath("Pt1").joinpath("Pinnacle").iterdir():
        command = (
            [str(pmp_test_utils.get_executable_even_when_embedded()), "-m"]
            + "pymedphys pinnacle export".split()
            + [
                "-o",
                output_path,
                "-m",
                "CT",
                "-m",
                "RTSTRUCT",
                "-m",
                "RTDOSE",
                "-m",
                "RTPLAN",
                "-t",
                "Trial_1",
                pinn_dir.as_posix(),
            ]
        )

        subprocess.check_call(command)

    # Just check that the number of output files is what we expect
    # The output itself is checked in the other function tests
    assert len(os.listdir(output_path)) == 119


@pytest.mark.slow
def test_pinnacle_cli_list(data):
    for pinn_dir in data.joinpath("Pt1").joinpath("Pinnacle").iterdir():
        command = (
            [str(pmp_test_utils.get_executable_even_when_embedded()), "-m"]
            + "pymedphys pinnacle export".split()
            + ["-l", pinn_dir.as_posix()]
        )

        cli_output = str(subprocess.check_output(command))
        cli_output_parts = cli_output.split("\\n")
        assert "Plans and Trials" in cli_output_parts[0]
        assert "Plan_0" in cli_output_parts[1]
        assert "Trial_1" in cli_output_parts[2]
        assert "Images" in cli_output_parts[3]
        assert (
            "CT: 1.2.826.0.1.3680043.9.7225.3631975141391052922211556418733774032"
            in cli_output_parts[4]
        )


@pytest.mark.slow
def test_pinnacle_cli_missing_trial(data):
    output_path = tempfile.mkdtemp()

    for pinn_dir in data.joinpath("Pt1").joinpath("Pinnacle").iterdir():
        command = (
            [str(pmp_test_utils.get_executable_even_when_embedded()), "-m"]
            + "pymedphys pinnacle export".split()
            + ["-o", output_path, "-t", "nonexistenttrial", pinn_dir.as_posix()]
        )

        cli_output = str(subprocess.check_output(command))
        assert "No Trial: nonexistenttrial found in Plan" in cli_output


@pytest.mark.slow
@pytest.mark.pydicom
def test_pinnacle_cli_skip_roi(data):
    output_path = tempfile.mkdtemp()

    skip_roi_name = "Target"

    for pinn_dir in data.joinpath("Pt1").joinpath("Pinnacle").iterdir():
        command = (
            [str(pmp_test_utils.get_executable_even_when_embedded()), "-m"]
            + "pymedphys pinnacle export".split()
            + [
                "-o",
                output_path,
                "-m",
                "RTSTRUCT",
                "-r",
                skip_roi_name,
                "-t",
                "Trial_1",
                pinn_dir.as_posix(),
            ]
        )

        subprocess.check_call(command)

    # Check that the ROI excluded is not in the resulting RTStruct
    rts_dcm = os.listdir(output_path)[0]
    ds = pydicom.dcmread(os.path.join(output_path, rts_dcm))
    for roi in ds.StructureSetROISequence:
        assert not roi.ROIName == skip_roi_name


@pytest.mark.slow
@pytest.mark.pydicom
def test_pinnacle_cli_native_tar(tmp_path):
    """Export the original Pinnacle TAR and compare its reference plan and dose."""
    # Chlap Phillip (2020), CC BY 4.0: https://doi.org/10.5281/zenodo.3900946.
    # Keep the native TAR unchanged, including its 33 names containing colons.
    paths = download.zip_data_paths("pinnacle_tar_test_data.zip")
    archive = next(path for path in paths if path.name == "test_pinnacle_16.0.tar.gz")
    output_path = tmp_path / "dicom"
    # Plan_2 is the plan used by the original Pinnacle export example.
    # Confine the CLI's extracted files to the test's temporary directory.
    result = subprocess.run(
        [
            str(pmp_test_utils.get_executable_even_when_embedded()),
            "-m",
            "pymedphys",
            "pinnacle",
            "export",
            str(archive),
            "-o",
            str(output_path),
            "-p",
            "Plan_2",
        ],
        env={
            **os.environ,
            **{name: str(tmp_path) for name in ("TMPDIR", "TMP", "TEMP")},
        },
        capture_output=True,
        check=False,
    )
    if result.returncode:
        # The CLI logs source identifiers; do not include its output in a failure.
        pytest.fail("The native Pinnacle TAR export command failed")

    datasets = [pydicom.dcmread(path) for path in output_path.iterdir()]
    assert Counter(dataset.Modality for dataset in datasets) == {
        "CT": 72,
        "RTSTRUCT": 1,
        "RTPLAN": 1,
        "RTDOSE": 1,
    }
    exported = {dataset.Modality: dataset for dataset in datasets}
    reference = {
        dataset.Modality: dataset
        for path in (archive.parent.parent / "dcm").glob("*.dcm")
        for dataset in [pydicom.dcmread(path)]
    }
    assert set(reference) == {"RTPLAN", "RTDOSE"}

    actual_dose = exported["RTDOSE"]
    reference_dose = reference["RTDOSE"]
    for attribute in (
        "ImageOrientationPatient",
        "ImagePositionPatient",
        "PixelSpacing",
        "GridFrameOffsetVector",
    ):
        assert np.allclose(
            getattr(actual_dose, attribute), getattr(reference_dose, attribute)
        )
    actual_values = actual_dose.pixel_array.astype(float) * actual_dose.DoseGridScaling
    reference_values = (
        reference_dose.pixel_array.astype(float) * reference_dose.DoseGridScaling
    )
    assert actual_values.shape == reference_values.shape
    assert np.allclose(actual_values, reference_values, atol=0.01, rtol=0)

    actual_beams = exported["RTPLAN"].BeamSequence
    reference_beams = reference["RTPLAN"].BeamSequence
    assert len(actual_beams) == len(reference_beams)
    assert [len(beam.ControlPointSequence) for beam in actual_beams] == [
        len(beam.ControlPointSequence) for beam in reference_beams
    ]
