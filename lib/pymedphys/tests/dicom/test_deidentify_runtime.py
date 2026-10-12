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

"""The runtime environment that de-identification records as provenance.

The values are compared with the sources they are read from, which each test
changes by monkeypatching, as an upgrade or another interpreter would, so
that each value is shown to be read from its own source at each call.
"""

import dataclasses
import platform

from pymedphys._imports import pydicom, pytest, tomlkit

from pymedphys import _version
from pymedphys._dicom.deidentify import runtime

# The structured fields of a release report's runtime section, in order.
RUNTIME_FIELDS = (
    "pymedphys_version",
    "python_implementation",
    "python_version",
    "pydicom_version",
    "tomlkit_version",
)


def test_the_runtime_environment_holds_the_fields_a_release_report_records():
    fields = dataclasses.fields(runtime.RuntimeEnvironment)

    assert tuple(field.name for field in fields) == RUNTIME_FIELDS


def test_the_runtime_environment_is_the_running_one():
    assert runtime.runtime_environment() == runtime.RuntimeEnvironment(
        pymedphys_version=_version.__version__,
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        pydicom_version=pydicom.__version__,
        tomlkit_version=tomlkit.__version__,
    )


def test_software_versions_give_pymedphys_then_python_pydicom_and_tomlkit():
    environment = runtime.RuntimeEnvironment(
        pymedphys_version="0.42.0.dev1",
        python_implementation="PyPy",
        python_version="3.11.9",
        pydicom_version="3.0.2",
        tomlkit_version="0.15.1",
    )

    assert environment.software_versions == (
        "0.42.0.dev1",
        "PyPy 3.11.9",
        "pydicom 3.0.2",
        "tomlkit 0.15.1",
    )


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "module, attribute, value, field",
    [
        (_version, "__version__", "0.42.0+local", "pymedphys_version"),
        (platform, "python_implementation", lambda: "PyPy", "python_implementation"),
        (platform, "python_version", lambda: "3.99.0", "python_version"),
        (pydicom, "__version__", "9.9.9", "pydicom_version"),
        (tomlkit, "__version__", "9.9.9", "tomlkit_version"),
    ],
    ids=list(RUNTIME_FIELDS),
)
def test_each_value_is_read_from_its_source_at_each_call(
    monkeypatch, module, attribute, value, field
):
    before = runtime.runtime_environment()
    monkeypatch.setattr(module, attribute, value)
    after = runtime.runtime_environment()

    expected = value() if callable(value) else value
    assert getattr(after, field) == expected
    assert dataclasses.replace(after, **{field: getattr(before, field)}) == before


def test_the_runtime_environment_is_read_only():
    environment = runtime.runtime_environment()

    with pytest.raises(dataclasses.FrozenInstanceError):
        environment.pydicom_version = "9.9.9"  # type: ignore[misc]
