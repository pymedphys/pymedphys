# Copyright (C) 2021 Matthew Jennings
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" A test suite for DICOM display functions. """

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.utilities import pretty_patient_name


@pytest.mark.pydicom
def test_pretty_patient_name_all_params():

    ds = pydicom.Dataset()
    ds.PatientName = "last^first^middle^^hon"

    pretty_name_param_expected_combos = (
        (
            {
                "surname_first": True,
                "capitalise_surname": True,
                "include_honorific": True,
            },
            "Hon. LAST, First Middle",
        ),
        (
            {
                "surname_first": True,
                "capitalise_surname": True,
                "include_honorific": False,
            },
            "LAST, First Middle",
        ),
        (
            {
                "surname_first": True,
                "capitalise_surname": False,
                "include_honorific": True,
            },
            "Hon. Last, First Middle",
        ),
        (
            {
                "surname_first": True,
                "capitalise_surname": False,
                "include_honorific": False,
            },
            "Last, First Middle",
        ),
        (
            {
                "surname_first": False,
                "capitalise_surname": True,
                "include_honorific": True,
            },
            "Hon. First Middle LAST",
        ),
        (
            {
                "surname_first": False,
                "capitalise_surname": True,
                "include_honorific": False,
            },
            "First Middle LAST",
        ),
        (
            {
                "surname_first": False,
                "capitalise_surname": False,
                "include_honorific": True,
            },
            "Hon. First Middle Last",
        ),
        (
            {
                "surname_first": False,
                "capitalise_surname": False,
                "include_honorific": False,
            },
            "First Middle Last",
        ),
    )

    for params, expected in pretty_name_param_expected_combos:
        assert pretty_patient_name(ds, **params) == expected


@pytest.mark.pydicom
def test_pretty_patient_name_inputs():

    ds = pydicom.Dataset()

    ds.PatientName = "last^first^middle"
    with pytest.raises(ValueError):
        pretty_patient_name(ds, include_honorific=True)

    ds.PatientName = "last^first^^HON"
    assert pretty_patient_name(ds, include_honorific=True) == "Hon. First LAST"

    ds.PatientName = "last"
    assert pretty_patient_name(ds) == "LAST"
