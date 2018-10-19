"""PyTest local plugins.
"""


import os


def pytest_ignore_collect(path, config):
    """ return True to prevent considering this path for collection.
    This hook is consulted for all files and directories prior to calling
    more specific hooks.
    """

    print(path)
    print(os.path.dirname(__file__))

    relative_path = os.path.relpath(path, os.path.dirname(__file__))

    return relative_path.startswith('experimentation')
