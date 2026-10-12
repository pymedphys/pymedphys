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

"""Pytest plugin that resolves test paths relative to the caller's directory.

``pymedphys dev tests`` runs pytest from the library directory and loads this
module with ``-p``. pytest-xdist workers parse the original arguments again,
load the same plugin, and inherit the environment, so they resolve each path
exactly as the controller does. Nothing imports this module before pytest
does, so pytest can rewrite its assertions without warning.
"""

import os

from .tests import CALLER_DIRECTORY_VARIABLE, resolve_test_paths


def _caller_directory():
    return os.environ.get(CALLER_DIRECTORY_VARIABLE)


def pytest_load_initial_conftests(early_config):
    """Resolve positional paths after pytest has parsed its own options."""
    original_cwd = _caller_directory()
    if original_cwd is None:
        return
    # Pytest's own implementation of this hook runs trylast. Updating its
    # parsed paths first lets it find caller-relative conftests and register
    # their options before the final argument parse.
    namespace = early_config.known_args_namespace
    namespace.file_or_dir = resolve_test_paths(
        namespace.file_or_dir, original_cwd, pyargs=namespace.pyargs
    )


def pytest_configure(config):
    original_cwd = _caller_directory()
    if original_cwd is None:
        return
    # The final parse includes options registered by initial conftests.
    # Do not rewrite argv: the same text may be both a path and a value.
    config.args = resolve_test_paths(
        config.getoption("file_or_dir"),
        original_cwd,
        pyargs=config.getoption("pyargs"),
    )
