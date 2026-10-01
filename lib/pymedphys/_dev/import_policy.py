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

"""Which extra, if any, each PyMedPhys module needs just to be imported.

Library code imports optional dependencies through ``pymedphys._imports``,
which defers each import until first use, so a module imports with only the
base dependencies and says which extra to install when a feature is used.
The modules in ``REQUIRED_EXTRAS`` cannot do that: the Streamlit apps call
Streamlit at import time, for example in decorators such as
``@st.cache_data``, and the AI modules import Anthropic's SDK directly.
They are only reached through the GUI or their tests.
"""

from pymedphys._dev.paths import LIBRARY_PATH

# Module prefixes and the extra each needs at import time. The longest
# matching prefix applies.
REQUIRED_EXTRAS = {
    "pymedphys._app": "user",
    "pymedphys._streamlit": "user",
    "pymedphys._experimental.streamlit": "user",
    "pymedphys._ai": "ai",
    "pymedphys._experimental.streamlit.apps.mosaiq_claude_chat.app": "ai",
    "pymedphys.conftest": "tests",
    "pymedphys.tests": "tests",
}

# Never imported as modules: the registry is parsed rather than run, ``docs``
# holds the documentation sources, and the DICOM RT viewer is a script for
# ``streamlit run`` that runs its app when imported.
NOT_IMPORTED = (
    "pymedphys._imports.imports",
    "pymedphys.docs",
    "pymedphys._experimental.dicomrtvisualisation.visualise",
)


def _is_within(module_name: str, prefix: str) -> bool:
    return module_name == prefix or module_name.startswith(prefix + ".")


def module_names() -> list[str]:
    """Return the dotted name of every PyMedPhys module that can be imported."""
    names = []
    for path in sorted(LIBRARY_PATH.rglob("*.py")):
        parts = path.relative_to(LIBRARY_PATH.parent).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]

        name = ".".join(parts)
        if not any(_is_within(name, prefix) for prefix in NOT_IMPORTED):
            names.append(name)

    return names


def required_extra(module_name: str) -> str | None:
    """Return the extra needed to import a module, or None for the base install."""
    matches = [prefix for prefix in REQUIRED_EXTRAS if _is_within(module_name, prefix)]
    if not matches:
        return None

    return REQUIRED_EXTRAS[max(matches, key=len)]
