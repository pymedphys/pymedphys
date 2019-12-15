"""PyTest local plugins."""


import os

import pytest


# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False, help="run slow tests"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        # --run-slow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --run-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


def pytest_ignore_collect(path, config):  # pylint: disable = unused-argument
    """return True to prevent considering this path for collection.

    This hook is consulted for all files and directories prior to
    calling more specific hooks.
    """

    relative_path = os.path.relpath(str(path), os.path.dirname(__file__))
    relative_path_list = relative_path.split(os.path.sep)

    return (
        (
            len(relative_path_list) > 1
            and relative_path_list[0] == "examples"
            and relative_path_list[1] == "labs"
        )
        or "node_modules" in relative_path_list
        or "site-packages" in relative_path_list
        or ("_bundle" in relative_path_list and "python" in relative_path_list)
    )
