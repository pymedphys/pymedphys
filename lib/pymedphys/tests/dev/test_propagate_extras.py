# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""How ``pymedphys dev propagate`` lists the packages in each extra."""

import pytest

from pymedphys._dev import propagate


def test_versions_and_markers_are_dropped():
    packages = propagate.packages_by_extra(
        {"user": ["numpy>=1.26", "altair>=6.0.0; python_version >= '3.14'"]}
    )

    assert packages == {"user": ["altair", "numpy"]}


def test_an_extra_that_names_other_extras_lists_their_packages():
    # An extra can require PyMedPhys itself with other extras, as
    # ``all = ["pymedphys[user,tests]"]`` does. The hint for a missing
    # package needs the packages, not the name "pymedphys".
    packages = propagate.packages_by_extra(
        {
            "user": ["numpy", "pydicom"],
            "tests": ["pymedphys[user]", "pytest"],
            "all": ["pymedphys[user,tests]"],
            "dicom": ["pymedphys[user]"],
        }
    )

    assert packages["tests"] == ["numpy", "pydicom", "pytest"]
    assert packages["all"] == ["numpy", "pydicom", "pytest"]
    assert packages["dicom"] == ["numpy", "pydicom"]


def test_extras_that_name_each_other_terminate():
    packages = propagate.packages_by_extra(
        {"a": ["numpy", "pymedphys[b]"], "b": ["scipy", "pymedphys[a]"]}
    )

    assert packages == {"a": ["numpy", "scipy"], "b": ["numpy", "scipy"]}


def test_naming_an_undefined_extra_fails():
    with pytest.raises(ValueError, match="missing"):
        propagate.packages_by_extra({"all": ["pymedphys[missing]"]})
