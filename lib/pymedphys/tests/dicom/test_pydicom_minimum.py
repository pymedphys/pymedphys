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

"""PyMedPhys requires pydicom 3.0 or later (decision D-004).

The checks read the installed distribution's metadata rather than
``pyproject.toml``, so they also hold for an installed wheel. An editable
install's metadata is only as current as its last installation, so reinstall
or sync the environment after changing the constraint (``uv run`` and CI do
this).
"""

from importlib import metadata

from packaging.requirements import Requirement
from packaging.version import Version

from pymedphys._imports import pydicom, pytest

MINIMUM = Version("3.0")
# Later than any pydicom 2 release, so every 2.x release is excluded with it.
LATEST_POSSIBLE_PYDICOM_2 = Version("2.999")


def _declared_pydicom_requirements():
    declared = [Requirement(line) for line in metadata.requires("pymedphys") or []]
    return [requirement for requirement in declared if requirement.name == "pydicom"]


def test_every_declared_pydicom_requirement_excludes_pydicom_2():
    requirements = _declared_pydicom_requirements()

    assert requirements, "No extra declares pydicom"
    for requirement in requirements:
        assert not requirement.specifier.contains(LATEST_POSSIBLE_PYDICOM_2), str(
            requirement
        )
        assert requirement.specifier.contains(MINIMUM), str(requirement)


@pytest.mark.pydicom
def test_installed_pydicom_meets_the_minimum():
    assert Version(pydicom.__version__) >= MINIMUM
