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

"""The MetersetMap Comparison app driven through ``AppTest``.

These scenarios reproduce the retired Cypress specification against the demo
configuration: the status indicators, then a Monaco reference paired with an
iCOM evaluation for two demo patients.
"""

from pymedphys._imports import pytest

from . import apptest_utilities as utl

pytest.importorskip("streamlit")

pytestmark = pytest.mark.usefixtures("demo_working_directory")

ICOM_TIMESTAMPS_LABEL = "Select iCOM delivery timestamp(s)"


def _load_demo_metersetmap():
    app_test = utl.load_app("metersetmap", timeout=utl.DEMO_TIMEOUT_SECONDS)
    utl.widget(app_test.sidebar.radio, "Config Mode").set_value("Demo Data").run()
    utl.assert_no_exception(app_test)

    return app_test


def _assert_overview(app_test, total_mu: str, patient_name: str) -> None:
    """The reference panel, evaluation panel, and sidebar overview agree."""
    totals = utl.code_values(app_test, "Total MU")
    names = utl.code_values(app_test, "Patient Name")

    assert len(totals) >= 2, totals
    assert set(totals) == {total_mu}, totals
    assert len(names) >= 2, names
    assert set(names) == {patient_name}, names


def test_status_indicators_report_each_linac():
    app_test = _load_demo_metersetmap()
    utl.widget(
        app_test.sidebar.button, "Check status of iCOM and backups"
    ).click().run()
    utl.assert_no_exception(app_test)

    # One line under "Last recorded iCOM stream", one under "Last indexed backup".
    for linac in ("George", "MacDonald"):
        assert utl.count_containing(app_test, linac) == 2


def test_patient_979797_from_blue_with_one_icom_record():
    app_test = _load_demo_metersetmap()

    location = utl.widget(app_test.radio, "Monaco Plan Location")
    location.set_value(utl.option_containing(location.options, "BLUE")).run()
    utl.widget(app_test.text_input, "Patient ID").input("979797").run()
    utl.widget(app_test.multiselect, ICOM_TIMESTAMPS_LABEL).set_value(
        ["2020-04-29 07:50:43"]
    ).run()
    utl.assert_no_exception(app_test)

    _assert_overview(app_test, "426.7", "PHYSICS, Test")


def test_patient_989898_plan_3abut_with_one_icom_record():
    app_test = _load_demo_metersetmap()

    utl.widget(app_test.text_input, "Patient ID").input("989898").run()
    plan = utl.widget(app_test.radio, "Select a Monaco plan")
    plan.set_value(utl.option_containing(plan.options, "3ABUT")).run()
    utl.widget(app_test.multiselect, ICOM_TIMESTAMPS_LABEL).set_value(
        ["2020-04-29 07:47:29"]
    ).run()
    utl.assert_no_exception(app_test)

    _assert_overview(app_test, "150.0", "PHYSICS, Mock")


def test_patient_989898_plan_3abut_with_two_icom_records():
    app_test = _load_demo_metersetmap()

    utl.widget(app_test.text_input, "Patient ID").input("989898").run()
    plan = utl.widget(app_test.radio, "Select a Monaco plan")
    plan.set_value(utl.option_containing(plan.options, "3ABUT")).run()
    utl.widget(app_test.multiselect, ICOM_TIMESTAMPS_LABEL).set_value(
        ["2020-04-29 07:45:59", "2020-04-29 07:44:44"]
    ).run()
    utl.assert_no_exception(app_test)

    _assert_overview(app_test, "150.0", "PHYSICS, Mock")
