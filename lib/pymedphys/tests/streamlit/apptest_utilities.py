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

"""Helpers for driving the PyMedPhys GUI through Streamlit's ``AppTest``.

``AppTest`` runs ``lib/pymedphys/_app.py`` in-process, so these tests need
neither a browser nor a Node toolchain. Widgets are found by their labels,
and assertions read the rendered markdown, which is where the apps write
their results.
"""

import pathlib
import re
from typing import TYPE_CHECKING, Any, List, Optional, Sequence

import pymedphys

if TYPE_CHECKING:
    from streamlit.testing.v1 import AppTest

APP_PATH = pathlib.Path(pymedphys.__file__).parent.joinpath("_app.py")

DEMO_DATA_ZIP = "metersetmap-gui-e2e-data.zip"
DEMO_DIRECTORY_NAME = "pymedphys-gui-demo"

# Data-driven runs extract the demo archive and read its plans on first use.
DEMO_TIMEOUT_SECONDS = 600
INDEX_TIMEOUT_SECONDS = 120


def load_app(
    app_key: Optional[str] = None, *, timeout: float = INDEX_TIMEOUT_SECONDS
) -> "AppTest":
    """Run the GUI script once, optionally opened on ``app_key``."""
    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=timeout)
    if app_key is not None:
        app_test.query_params["app"] = app_key

    return app_test.run()


def assert_no_exception(app_test: "AppTest") -> None:
    exceptions = [element.value for element in app_test.exception]
    assert not exceptions, f"The app raised: {exceptions}"


def widget(elements: Sequence[Any], label: str) -> Any:
    """Return the single widget in ``elements`` carrying ``label``."""
    matches = [element for element in elements if element.label == label]
    labels = [element.label for element in elements]
    assert len(matches) == 1, f"Expected one widget labelled {label!r}, found {labels}"

    return matches[0]


def option_containing(options: Sequence[Any], text: str) -> Any:
    """Return the first option whose text contains ``text``."""
    matches = [option for option in options if text in str(option)]
    assert matches, f"No option contains {text!r}; the options were {list(options)}"

    return matches[0]


def markdown_values(app_test: "AppTest") -> List[str]:
    """The text of every markdown element, sidebar included."""
    return [element.value for element in app_test.markdown]


def code_values(app_test: "AppTest", label: str) -> List[str]:
    """Values the apps write as ``label: `value``` through ``st.write``."""
    pattern = re.compile(rf"{re.escape(label)}: `([^`]*)`")

    return [
        value for text in markdown_values(app_test) for value in pattern.findall(text)
    ]


def count_containing(app_test: "AppTest", text: str) -> int:
    return sum(text in value for value in markdown_values(app_test))
