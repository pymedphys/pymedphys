# Copyright (C) 2026 Matthew Jennings (modifications)

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PyTest local plugins."""

import dataclasses
import os
import pathlib
import shutil
import tempfile
from collections.abc import Set

# Matplotlib reads MPLBACKEND once, when it is first imported. The GUI
# backends it would otherwise pick on macOS and Windows (macosx, TkAgg) abort
# the interpreter when a figure is created off the main thread, which is what
# the Streamlit AppTest suite does, so the whole test run draws with Agg.
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest  # noqa: E402


@dataclasses.dataclass(frozen=True)
class Marker:
    """A configured pytest marker and the flags that select it.

    Attributes
    ----------
    only_options
        Flags that run only the tests with this marker. The last one is the
        name used in messages.
    include_option
        For an opt-in marker, the flag that adds its tests to the default
        selection. None for a marker whose tests run by default.
    description
        The marker's description, registered with pytest.
    noun
        How messages refer to the marked tests.
    """

    only_options: tuple[str, ...]
    include_option: str | None
    description: str
    noun: str


# Each marker below can be selected with a "run only" flag. The opt-in markers
# are also skipped unless they are requested, either with their "run only"
# flag or with an additive "--include-..." flag that keeps the default
# selection and adds the marked tests to it.
MARKER_CONFIG: dict[str, Marker] = {
    "slow": Marker(
        only_options=("--run-only-slow", "--slow"),
        include_option="--include-slow",
        description="mark test as slow to run",
        noun="the slow tests",
    ),
    "pydicom": Marker(
        only_options=("--run-only-pydicom", "--pydicom"),
        include_option=None,
        description="mark test as using pydicom",
        noun="the tests that use pydicom",
    ),
    "mosaiqdb": Marker(
        only_options=("--run-only-mosaiqdb", "--mosaiqdb"),
        include_option="--include-mosaiqdb",
        description="mark test as using mosaiq db",
        noun="the tests that use a Mosaiq database",
    ),
    "anthropic_key": Marker(
        only_options=("--run-only-anthropic", "--anthropic"),
        include_option="--include-anthropic",
        description="mark test as requiring an Anthropic API key",
        noun="the tests that use the Anthropic API",
    ),
}

OPT_IN_MARKERS = frozenset(
    key for key, marker in MARKER_CONFIG.items() if marker.include_option
)

RUN_ALL_OPTIONS = ["--run-all-tests", "--all"]

DATA_DIR_ENVIRONMENT_VARIABLE = "PYMEDPHYS_DATA_DIR"
HOME_ENVIRONMENT_VARIABLES = ("HOME", "USERPROFILE")

# Set by pytest_configure. REAL_HOME is the home directory the session
# started with; SHARED_DATA_DIR is the data cache the tests keep sharing with
# it so that downloads are not repeated.
REAL_HOME: pathlib.Path | None = None
SHARED_DATA_DIR: pathlib.Path | None = None

_SAVED_ENVIRONMENT = pytest.StashKey[dict[str, str | None]]()
_TEMPORARY_HOME = pytest.StashKey[pathlib.Path]()


def skip_reason(
    markers: Set[str],
    *,
    only: Set[str],
    include: Set[str],
    run_all: bool,
) -> str | None:
    """Return why a test with ``markers`` is skipped, or None to run it.

    Parameters
    ----------
    markers
        The names of the configured markers the test carries.
    only
        Markers selected with a "run only" flag. When any are given, only
        tests carrying at least one of them run.
    include
        Opt-in markers added to the selection with an "--include-..." flag.
    run_all
        Whether "--all" was passed, which runs every test.
    """
    if run_all:
        return None

    if only and not markers & only:
        flags = ", ".join(sorted(MARKER_CONFIG[key].only_options[-1] for key in only))
        return f"not selected by {flags}"

    not_requested = sorted((markers & OPT_IN_MARKERS) - only - include)
    if not_requested:
        marker = MARKER_CONFIG[not_requested[0]]
        return (
            f"needs {marker.include_option} to run, "
            f"or {marker.only_options[-1]} to run only {marker.noun}"
        )

    return None


# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_addoption(parser):
    for marker in MARKER_CONFIG.values():
        for option in marker.only_options:
            parser.addoption(
                option,
                action="store_true",
                default=False,
                help=f"run only {marker.noun}",
            )
        if marker.include_option:
            parser.addoption(
                marker.include_option,
                action="store_true",
                default=False,
                help=f"also run {marker.noun}",
            )

    for option in RUN_ALL_OPTIONS:
        parser.addoption(
            option,
            action="store_true",
            default=False,
            help="run all tests, including every opt-in marker",
        )


def pytest_configure(config):
    for key, marker in MARKER_CONFIG.items():
        config.addinivalue_line("markers", f"{key}: {marker.description}")

    _isolate_home_directory(config)


def pytest_unconfigure(config):
    _restore_home_directory(config)


def _isolate_home_directory(config):
    """Point the home directory at a throwaway directory for the session.

    Code under test reads and writes ``~/.pymedphys`` (the pseudonymisation
    strategy, for example, stores its secret in ``config.toml``), and the
    Streamlit apps read ``~/.streamlit``. Redirecting the home directory
    through the environment also covers subprocess-based CLI tests. The data
    cache stays shared with the real home directory through
    ``PYMEDPHYS_DATA_DIR`` so that downloads are not repeated.
    """
    global REAL_HOME, SHARED_DATA_DIR  # pylint: disable = global-statement

    if _SAVED_ENVIRONMENT in config.stash:
        return

    real_home = pathlib.Path.home()
    saved_environment = {
        name: os.environ.get(name)
        for name in (*HOME_ENVIRONMENT_VARIABLES, DATA_DIR_ENVIRONMENT_VARIABLE)
    }

    shared_data_dir = os.environ.setdefault(
        DATA_DIR_ENVIRONMENT_VARIABLE, str(real_home / ".pymedphys" / "data")
    )

    temporary_home = pathlib.Path(tempfile.mkdtemp(prefix="pymedphys-test-home-"))
    for name in HOME_ENVIRONMENT_VARIABLES:
        os.environ[name] = str(temporary_home)

    config.stash[_SAVED_ENVIRONMENT] = saved_environment
    config.stash[_TEMPORARY_HOME] = temporary_home

    REAL_HOME = real_home
    SHARED_DATA_DIR = pathlib.Path(shared_data_dir)


def _restore_home_directory(config):
    saved_environment = config.stash.get(_SAVED_ENVIRONMENT, None)
    if saved_environment is None:
        return

    for name, value in saved_environment.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    shutil.rmtree(config.stash[_TEMPORARY_HOME], ignore_errors=True)
    del config.stash[_SAVED_ENVIRONMENT]


def pytest_collection_modifyitems(config, items):
    run_all = any(config.getoption(option) for option in RUN_ALL_OPTIONS)
    only = {
        key
        for key, marker in MARKER_CONFIG.items()
        if any(config.getoption(option) for option in marker.only_options)
    }
    include = {
        key
        for key, marker in MARKER_CONFIG.items()
        if marker.include_option and config.getoption(marker.include_option)
    }

    for item in items:
        markers = {key for key in MARKER_CONFIG if key in item.keywords}
        reason = skip_reason(markers, only=only, include=include, run_all=run_all)
        if reason is not None:
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_ignore_collect(collection_path, config):  # pylint: disable = unused-argument
    """return True to prevent considering this collection_path for collection.

    This hook is consulted for all files and directories prior to
    calling more specific hooks.
    """

    relative_path = os.path.relpath(str(collection_path), os.path.dirname(__file__))
    relative_path_list = relative_path.split(os.path.sep)

    return (
        (len(relative_path_list) > 1 and relative_path_list[0] == "examples")
        or "node_modules" in relative_path_list
        or "site-packages" in relative_path_list
        or "_build" in relative_path_list
        or ("_bundle" in relative_path_list and "python" in relative_path_list)
        or (
            config.getoption("--doctest-modules")
            and (
                "_gamma" in relative_path_list
                or "tests" in relative_path_list
                or "_imports" in relative_path_list
                or "_experimental" in relative_path_list
            )
        )
    )
