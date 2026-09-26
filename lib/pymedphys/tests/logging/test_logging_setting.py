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

from pymedphys.cli import run_logging_basic_config

Args = collections.namedtuple("Args", ["logging_verbose", "logging_debug"])


def test_setting_logging():
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
