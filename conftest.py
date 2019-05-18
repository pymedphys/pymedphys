"""PyTest local plugins."""


import os


def pytest_ignore_collect(path, config):
    """return True to prevent considering this path for collection.

    This hook is consulted for all files and directories prior to
    calling more specific hooks.
    """

    relative_path = os.path.relpath(str(path), os.path.dirname(__file__))

    return (
        relative_path.startswith('notebooks') or
        relative_path.startswith('docs') or
        'node_modules' in relative_path or
        'xlwings' in relative_path or
        relative_path.startswith('scripts') or
        relative_path.startswith('app') or
    )
