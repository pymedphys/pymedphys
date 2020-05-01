"""PyTest local plugins."""


import os

import pytest

SKIPPING_CONFIG = {
    "slow": {
        "option": "--run-only-slow",
        "help": "run only the slow tests",
        "description": "mark test as slow to run",
        "skip_otherwise": True,
    },
    "yarn": {
        "option": "--run-only-yarn",
        "help": "run only the tests that need yarn",
        "description": "mark test as needing yarn",
        "skip_otherwise": True,
    },
    "pydicom": {
        "option": "--run-only-pydicom",
        "help": "run only the tests that use pydicom",
        "description": "mark test as using pydicom",
        "skip_otherwise": False,
    },
    "pylinac": {
        "option": "--run-only-pylinac",
        "help": "run only the tests that use pylinac",
        "description": "mark test as using pylinac",
        "skip_otherwise": False,
    },
}


# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_addoption(parser):
    for _, skip_item in SKIPPING_CONFIG.items():
        parser.addoption(
            skip_item["option"],
            action="store_true",
            default=False,
            help=skip_item["help"],
        )


def pytest_configure(config):
    for key, skip_item in SKIPPING_CONFIG.items():
        config.addinivalue_line("markers", f"{key}: {skip_item['description']}")


def pytest_collection_modifyitems(config, items):
    for key, skip_item in SKIPPING_CONFIG.items():
        if not config.getoption(skip_item["option"]):
            if skip_item["skip_otherwise"]:
                skip = pytest.mark.skip(
                    reason=f"need {skip_item['option']} option to run"
                )

                for item in items:
                    if key in item.keywords:
                        item.add_marker(skip)
        else:
            skip = pytest.mark.skip(reason=f"since {skip_item['option']} was passed")
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
        or ("_bundle" in relative_path_list and "python" in relative_path_list)
        or config.getoption("--doctest-modules")
        and "streamlit" in relative_path_list
    )
