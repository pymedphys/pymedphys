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


def test_demo_plan_factor_matches_the_independent_reference():
    """The demo electron plan models to 1.0571.

    This replaces the retired Cypress baseline of 1.0618, which came from an
    optimiser that underestimated the largest circle in the demo insert.
    """
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

    # Independent reference for the 16-sided demo contour. Distances to the
    # contour segments bound the largest possible radius, and the model was
    # fitted to the 49 measurements matching the demo beam:
    #   width  = 3.098986 cm  (old optimiser: 2.851803 cm)
    #   length = 8.450195 cm  (old optimiser: 9.182625 cm)
    #   factor = 1.05707488   (old optimiser: 1.06182336)
    # Reference supplied by Matthew Jennings on PR #2527.
    assert utl.code_values(app_test, "Factor") == ["1.0571"]
