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

"""Keep deprecated Pinnacle imports from changing the public API."""

import importlib
import warnings

import pytest

from pymedphys import pinnacle


@pytest.mark.parametrize(
    "name", ["PinnacleExport", "PinnaclePlan", "PinnacleImage", "export_cli"]
)
def test_legacy_import_preserves_public_name(name):
    public_object = getattr(pinnacle, name)

    importlib.import_module("pymedphys.experimental.pinnacle")

    assert getattr(pinnacle, name) is public_object
    assert public_object.__name__ == name


@pytest.mark.parametrize("name", ["PinnacleExport", "PinnaclePlan", "PinnacleImage"])
def test_legacy_class_warns_and_forwards_arguments(name, monkeypatch):
    legacy = importlib.import_module("pymedphys.experimental.pinnacle")
    public_class = getattr(pinnacle, name)

    # Exercise the compatibility wrapper without reading patient data.
    def capture_arguments(instance, *args, **kwargs):
        instance.arguments = (args, kwargs)

    monkeypatch.setattr(public_class, "__init__", capture_arguments)
    args = (object(),)
    kwargs = {"logger": object()}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        direct = public_class(*args, **kwargs)

    assert not caught
    assert direct.arguments == (args, kwargs)

    with pytest.warns(DeprecationWarning, match=rf"pymedphys\.pinnacle\.{name}"):
        instance = getattr(legacy, name)(*args, **kwargs)

    assert isinstance(instance, public_class)
    assert instance.arguments == (args, kwargs)
