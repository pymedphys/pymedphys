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

"""The GUI index and the first screen of every registered app."""

# pylint: disable = protected-access

from pymedphys._imports import pytest

from . import apptest_utilities as utl

pytest.importorskip("streamlit")

# The app registry imports every app, and the apps use Streamlit at import
# time, so these imports must come after the skip guard.
from pymedphys._experimental.streamlit import apps as _experimental_apps  # noqa: E402
from pymedphys._streamlit import apps as _stable_apps  # noqa: E402
from pymedphys._streamlit import index as _index  # noqa: E402


def _registered_apps():
    return {
        **_index._get_apps_from_module(_stable_apps),
        **_index._get_apps_from_module(_experimental_apps),
    }


def test_index_lists_every_registered_app():
    app_test = utl.load_app()
    utl.assert_no_exception(app_test)

    expected_titles = sorted(app.TITLE for app in _registered_apps().values())
    assert sorted(button.label for button in app_test.button) == expected_titles


def test_filter_narrows_the_index():
    app_test = utl.load_app()
    utl.widget(app_test.text_input, "Filter").input("dicom").run()
    utl.assert_no_exception(app_test)

    labels = [button.label for button in app_test.button]
    assert labels
    assert all("dicom" in label.lower() for label in labels)


def test_index_button_opens_the_app():
    app_test = utl.load_app()
    utl.widget(app_test.button, "DICOM Pseudonymisation").click().run()
    utl.assert_no_exception(app_test)

    assert [title.value for title in app_test.title] == ["DICOM Pseudonymisation"]


@pytest.mark.usefixtures("demo_working_directory", "demo_config_on_disk")
@pytest.mark.parametrize("app_key", sorted(_registered_apps()))
def test_every_app_renders_its_first_screen(app_key):
    """Each app draws its first screen against the demo configuration."""
    app_test = utl.load_app(app_key, timeout=utl.DEMO_TIMEOUT_SECONDS)
    utl.assert_no_exception(app_test)

    expected_title = _registered_apps()[app_key].TITLE
    assert [title.value for title in app_test.title] == [expected_title]
