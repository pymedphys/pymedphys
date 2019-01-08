"""PyTest local plugins.
"""


import os


def pytest_ignore_collect(path, config):
    """ return True to prevent considering this path for collection.
    This hook is consulted for all files and directories prior to calling
    more specific hooks.
    """

    relative_path = os.path.relpath(str(path), os.path.dirname(__file__))

    build_dir = os.path.join('docs', '_build')

    return (
        relative_path.startswith('experimentation') or
        relative_path.startswith(build_dir) or
        relative_path.startswith('test_all')
    )
