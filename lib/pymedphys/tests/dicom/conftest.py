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

from pymedphys._imports import pydicom, pytest


@pytest.fixture(name="pydicom_behaviour", params=["current", "future"])
def fixture_pydicom_behaviour(request):
    """Run a test with pydicom's current behaviour, then with its future one.

    pydicom's future behaviour imitates its next major version: the APIs that
    pydicom 3 deprecates for removal in pydicom 4 raise instead of warning.
    In pydicom 3.0, ``Dataset.pixel_array`` itself uses one of them, so a test
    that reads pixel data fails with the future behaviour.
    """
    # pydicom has no public getter for the current setting.
    was_future = pydicom.config._use_future  # pylint: disable = protected-access
    pydicom.config.future_behavior(request.param == "future")
    try:
        yield request.param
    finally:
        pydicom.config.future_behavior(was_future)
