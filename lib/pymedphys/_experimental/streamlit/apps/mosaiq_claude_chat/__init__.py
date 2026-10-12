# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2024 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import streamlit as st

from pymedphys._streamlit import categories

CATEGORY = categories.DRAFT
TITLE = "MOSAIQ Claude Chat"

# The app's dependencies are in the optional ``ai`` extra, so import it only
# when it is opened: the rest of the GUI must load without them.
_AI_MODULES = {"anthropic", "httpx2", "trio"}


def main():
    try:
        from .app import main as app_main  # pylint: disable = import-outside-toplevel
    except ModuleNotFoundError as error:
        missing_package = str(error.name or "").split(".", maxsplit=1)[0]
        if missing_package not in _AI_MODULES:
            raise
        st.error(
            "This app needs the optional AI dependencies. Install them with "
            '`pip install "pymedphys[ai]"`, then restart the GUI.'
        )
        return

    app_main()
