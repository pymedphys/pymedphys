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
iCOM evaluation for two demo patients. One of them goes on to run the
comparison, which is where the app calls ``pymedphys.gamma``.
"""

import re

from pymedphys._imports import pytest

from . import apptest_utilities as utl

pytest.importorskip("streamlit")

pytestmark = pytest.mark.usefixtures("demo_working_directory")

ICOM_TIMESTAMPS_LABEL = "Select iCOM delivery timestamp(s)"
GAMMA_SUMMARY = re.compile(
    r"Local Gamma \(2%/0\.5mm, 20% dose cutoff\) \| Passed: (?P<percent>[\d.]+)% "
    r"\((?P<passed>\d+) of (?P<analysed>\d+) points\)"
)


def _load_demo_metersetmap():
    app_test = utl.load_app("metersetmap", timeout=utl.DEMO_TIMEOUT_SECONDS)
    utl.widget(app_test.sidebar.radio, "Config Mode").set_value("Demo Data").run()
    utl.assert_no_exception(app_test)

    return app_test


def _raised_apart_from_missing_imagemagick(app_test) -> list[str]:
    """What the app raised, leaving out its notice that ImageMagick is missing.

    After a comparison the app converts its report to PDF with ImageMagick.
    Where that program is not installed, the app shows this one notice in
    place of the PDF, and the comparison is complete.
    """
    return [
        element.value
        for element in app_test.exception
        if "Please install Image Magick" not in element.value
    ]


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


def test_advanced_mode_offers_the_configured_gamma_options():
    app_test = _load_demo_metersetmap()
    utl.widget(app_test.sidebar.checkbox, "Run in Advanced Mode").check().run()
    utl.assert_no_exception(app_test)

    # The demo configuration's 2%, 0.5 mm, local gamma, capped at 5.
    number_inputs = app_test.sidebar.number_input
    assert utl.widget(number_inputs, "MU criterion (%)").value == 2
    assert utl.widget(number_inputs, "Distance criterion (mm)").value == 0.5
    assert utl.widget(app_test.sidebar.checkbox, "Local normalisation").value is True
    assert utl.widget(number_inputs, "Gamma cap").value == 5


def test_running_the_comparison_reports_gamma_with_its_counts():
    app_test = _load_demo_metersetmap()

    utl.widget(app_test.text_input, "Patient ID").input("989898").run()
    plan = utl.widget(app_test.radio, "Select a Monaco plan")
    plan.set_value(utl.option_containing(plan.options, "3ABUT")).run()
    utl.widget(app_test.multiselect, ICOM_TIMESTAMPS_LABEL).set_value(
        ["2020-04-29 07:47:29"]
    ).run()
    utl.widget(app_test.button, "Run Calculation").click().run()
    raised = _raised_apart_from_missing_imagemagick(app_test)
    assert not raised, f"The app raised: {raised}"

    # The demo configuration names its gamma options as they were before
    # version 0.42.0: 2%, 0.5 mm, local normalisation, a 20% dose cutoff.
    summaries = [
        match
        for text in utl.markdown_values(app_test)
        if (match := GAMMA_SUMMARY.search(text))
    ]
    assert len(summaries) == 1, utl.markdown_values(app_test)
    passed, analysed = int(summaries[0]["passed"]), int(summaries[0]["analysed"])
    assert 0 < passed <= analysed
    assert float(summaries[0]["percent"]) == pytest.approx(
        100 * passed / analysed, abs=0.005
    )
    assert utl.count_containing(app_test, "Saved:") == 1
