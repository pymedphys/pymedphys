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

"""The Electron Insert Factor Modelling app driven through ``AppTest``."""

from pymedphys._imports import pytest

from . import apptest_utilities as utl

pytest.importorskip("streamlit")

pytestmark = pytest.mark.usefixtures("demo_working_directory")


def test_demo_plan_factor_matches_the_baseline():
    """The retired Cypress scenario: the demo electron plan models to 1.0618."""
    app_test = utl.load_app("electrons", timeout=utl.DEMO_TIMEOUT_SECONDS)

    config = utl.widget(app_test.sidebar.radio, "Config file to use")
    config.set_value(utl.option_containing(config.options, "Demo")).run()
    utl.assert_no_exception(app_test)

    location = utl.widget(app_test.radio, "Monaco Plan Location")
    location.set_value(utl.option_containing(location.options, "RED")).run()
    utl.widget(app_test.text_input, "Patient ID").input("989898").run()
    plan = utl.widget(app_test.radio, "Select a Monaco plan")
    plan.set_value(utl.option_containing(plan.options, "Electron")).run()
    utl.widget(app_test.button, "Calculate").click().run()
    utl.assert_no_exception(app_test)

    assert utl.code_values(app_test, "Factor") == ["1.0618"]
