# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import collections
import logging
import sys

from pymedphys import _config
from pymedphys._vendor import patchlogging
from pymedphys.cli import run_logging_basic_config

Args = collections.namedtuple("Args", ["logging_verbose", "logging_debug"])


def apply_patch_if_needed_and_test_it():
    if sys.version_info.major > 3 or (
        sys.version_info.major == 3 and sys.version_info.minor >= 8
    ):
        patchlogging.apply_logging_patch()
        assert not patchlogging._patch_applied  # pylint: disable = protected-access

        return

    try:
        patchlogging.apply_logging_patch()
    except ValueError:
        pass
    else:
        raise AssertionError("Logging patch should raise an error if not within CLI")

    _config.is_cli = True
    patchlogging.apply_logging_patch()

    try:
        patchlogging.apply_logging_patch()
    except ValueError:
        pass
    else:
        raise AssertionError("Logging patch should not be able to be run twice")

    _config.is_cli = False


def test_setting_logging():
    apply_patch_if_needed_and_test_it()

    args = Args(logging_verbose=False, logging_debug=False)
    run_logging_basic_config(args, {"level": logging.DEBUG})

    assert logging.root.getEffectiveLevel() == logging.DEBUG

    run_logging_basic_config(args, {"level": "error"})

    assert logging.root.getEffectiveLevel() == logging.ERROR

    run_logging_basic_config(args, {})

    assert logging.root.getEffectiveLevel() == logging.WARNING

    args_verbose = Args(logging_verbose=True, logging_debug=False)
    run_logging_basic_config(args_verbose, {})

    assert logging.root.getEffectiveLevel() == logging.INFO

    args_debug = Args(logging_verbose=False, logging_debug=True)
    run_logging_basic_config(args_debug, {})

    assert logging.root.getEffectiveLevel() == logging.DEBUG

    run_logging_basic_config(args, {"level": 5})

    assert logging.root.getEffectiveLevel() == 5

    args_both = Args(logging_verbose=True, logging_debug=True)
    run_logging_basic_config(args_both, {})

    assert logging.root.getEffectiveLevel() == logging.DEBUG
