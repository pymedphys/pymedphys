import collections
import logging

from pymedphys.cli import run_logging_basic_config

Args = collections.namedtuple("Args", ["logging_verbose", "logging_debug"])


def test_setting_logging():
    args = Args(logging_verbose=False, logging_debug=False)
    run_logging_basic_config(args, {"level": logging.DEBUG})

    assert logging.root.getEffectiveLevel() == 10

    run_logging_basic_config(args, {"level": "error"})

    assert logging.root.getEffectiveLevel() == 40

    run_logging_basic_config(args, {})

    assert logging.root.getEffectiveLevel() == 30

    args = Args(logging_verbose=True, logging_debug=False)
    run_logging_basic_config(args, {})

    assert logging.root.getEffectiveLevel() == 20

    args = Args(logging_verbose=False, logging_debug=True)
    run_logging_basic_config(args, {})

    assert logging.root.getEffectiveLevel() == 10

    args = Args(logging_verbose=True, logging_debug=True)
    run_logging_basic_config(args, {})

    assert logging.root.getEffectiveLevel() == 10
