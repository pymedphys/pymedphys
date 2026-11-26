# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Gamma's logging and its handling of default options."""

import logging

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys


def test_gamma_logs_to_its_module_logger(caplog):
    axis = np.array([0.0, 1.0, 2.0])
    with caplog.at_level(logging.INFO):
        pymedphys.gamma(axis, np.ones(3), axis, np.ones(3), [3, 2], 1.5)

    names = {record.name for record in caplog.records}
    assert names == {"pymedphys._gamma.implementation.shell"}
    # Every message must format; array criteria once failed under NumPy 2.
    messages = [record.getMessage() for record in caplog.records]
    assert "Normalisation dose set to 1.000" in messages
    assert (
        "Dose criterion set to 0.03, 0.02 (3, 2% of the normalisation dose)" in messages
    )
    assert "Distance criterion set to 1.5" in messages
    assert (
        "Lower dose cutoff set to 0.200 (20.0% of the normalisation dose)" in messages
    )


@pytest.mark.filterwarnings("ignore:.*outside the evaluation grid:UserWarning")
def test_memory_budget_of_none_uses_the_default():
    # The point at x = 5 is outside the evaluation grid, so the chunked
    # nearest-point comparison runs.
    arguments = (
        np.array([0.0, 1.0, 5.0]),
        np.ones(3),
        np.array([0.0, 1.0]),
        np.ones(2),
    )
    expected = pymedphys.gamma(*arguments, 3, 3)
    result = pymedphys.gamma(*arguments, 3, 3, memory_budget_bytes=None)
    np.testing.assert_array_equal(result.gamma, expected.gamma)
