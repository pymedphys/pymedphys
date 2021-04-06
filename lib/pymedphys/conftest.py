"""PyTest local plugins."""


import os

import pytest

SKIPPING_CONFIG = {
    "slow": {
        "options": ["--run-only-slow", "--slow"],
        "help": "run the slow tests",
        "description": "mark test as slow to run",
        "skip_otherwise": True,
    },
    "cypress": {
        "options": ["--run-only-yarn", "--cypress"],
        "help": "run the cypress tests",
        "description": "mark test as using cypress",
        "skip_otherwise": True,
    },
    "pydicom": {
        "options": ["--run-only-pydicom", "--pydicom"],
        "help": "run only the tests that use pydicom",
        "description": "mark test as using pydicom",
        "skip_otherwise": False,
    },
    "pylinac": {
        "options": ["--run-only-pylinac", "--pylinac"],
        "help": "run only the tests that use pylinac",
        "description": "mark test as using pylinac",
        "skip_otherwise": False,
    },
    "mosaiqdb": {
        "options": ["--run-only-mosaiqdb", "--mosaiqdb"],
        "help": "run only the tests that use mosaiq db",
        "description": "mark test as using mosaiq db",
        "skip_otherwise": True,
    },
}


# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_addoption(parser):
    for _, skip_item in SKIPPING_CONFIG.items():
        for option in skip_item["options"]:
            parser.addoption(
                option, action="store_true", default=False, help=skip_item["help"]
            )


def pytest_configure(config):
    for key, skip_item in SKIPPING_CONFIG.items():
        config.addinivalue_line("markers", f"{key}: {skip_item['description']}")


def pytest_collection_modifyitems(config, items):
    for key, skip_item in SKIPPING_CONFIG.items():
        this_option_set = False
        provided_option = ""

        for option in skip_item["options"]:
            if config.getoption(option):
                this_option_set = True
                provided_option = option
                break

        if not this_option_set:
            if skip_item["skip_otherwise"]:
                skip = pytest.mark.skip(
                    reason=f"need {skip_item['options'][-1]} option to run"
                )

                for item in items:
                    if key in item.keywords:
                        item.add_marker(skip)
        else:
            skip = pytest.mark.skip(reason=f"since {provided_option} was passed")
            for item in items:
                if key not in item.keywords:
                    item.add_marker(skip)


def pytest_ignore_collect(path, config):  # pylint: disable = unused-argument
    """return True to prevent considering this path for collection.

    This hook is consulted for all files and directories prior to
    calling more specific hooks.
    """

    relative_path = os.path.relpath(str(path), os.path.dirname(__file__))
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
                "_streamlit" in relative_path_list
                or "tests" in relative_path_list
                or "_imports" in relative_path_list
                or "_experimental" in relative_path_list
            )
        )
    )
