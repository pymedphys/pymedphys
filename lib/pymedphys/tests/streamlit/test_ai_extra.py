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

"""The GUI without the optional ``ai`` extra.

The Mosaiq chat app is the only GUI consumer of the ``ai`` extra. Without it,
the rest of the GUI must still load, and the chat app must say how to add it.
"""

import subprocess
import sys

from pymedphys._imports import pytest

from . import apptest_utilities as utl

pytest.importorskip("streamlit")

AI_MODULES = ("anthropic", "httpx2", "trio")
CHAT_APP_KEY = "mosaiq-claude-chat"


def _block_ai_modules(monkeypatch):
    # A None entry makes ``import name`` raise ModuleNotFoundError, as it
    # would for a package that is not installed.
    for name in AI_MODULES:
        monkeypatch.setitem(sys.modules, name, None)
    cached = [
        name
        for name in sys.modules
        if name.startswith("pymedphys._ai")
        or name.startswith("pymedphys._experimental.streamlit.apps.mosaiq_claude_chat.")
    ]
    for name in cached:
        monkeypatch.delitem(sys.modules, name)


def test_gui_index_imports_without_the_ai_extra():
    blocked = "; ".join(f"sys.modules[{name!r}] = None" for name in AI_MODULES)
    code = f"import sys; {blocked}; import pymedphys._streamlit.index"

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_chat_app_explains_how_to_install_the_ai_extra(monkeypatch):
    _block_ai_modules(monkeypatch)

    app_test = utl.load_app(CHAT_APP_KEY, timeout=utl.DEMO_TIMEOUT_SECONDS)

    utl.assert_no_exception(app_test)
    assert any("pymedphys[ai]" in error.value for error in app_test.error)
