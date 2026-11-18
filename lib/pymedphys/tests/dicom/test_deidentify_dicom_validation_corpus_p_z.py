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

"""The second half of the policies' runs checked by independent validators.

:mod:`~pymedphys.tests.dicom.test_deidentify_dicom_validation_corpus` runs
and validates each policy whose name begins with a letter from a to o, and
holds every check of a policy's validated run. This module runs the other
policies, from p to z, through the same checks: each test here calls the
first half's test of the same name. CI runs the two halves on two runners,
so that neither reaches the time limit. Like the first half's, these tests
are marked ``dicom_validators`` and run only when asked for.
"""

import inspect

from pymedphys._imports import pytest

from . import test_deidentify_dicom_validation_corpus as first_half
from .corpus_runs import SECOND_HALF

# The first half's fixtures, which pytest finds here by their names.
from .test_deidentify_dicom_validation_corpus import (  # noqa: F401  # pylint: disable = unused-import
    fixture_comparison,
    fixture_published,
    fixture_toolset,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.dicom_validators]

# The fixtures through which a test reads a policy's validated run.
RUN_FIXTURES = frozenset({"validated", "comparison"})


@pytest.fixture(
    name="validated",
    scope="module",
    params=[corpus_run.param() for corpus_run in SECOND_HALF],
)
def fixture_validated(request, toolset, published):  # pylint: disable = unused-argument
    return first_half._validate(  # pylint: disable = protected-access
        request.param, toolset
    )


def test_the_output_introduces_no_unexplained_finding(comparison):
    first_half.test_the_output_introduces_no_unexplained_finding(comparison)


def test_every_validator_ran_over_every_released_instance(comparison):
    first_half.test_every_validator_ran_over_every_released_instance(comparison)


def test_each_patients_outputs_are_consistent(validated):
    first_half.test_each_patients_outputs_are_consistent(validated)


def test_the_results_hold_no_marker(comparison):
    first_half.test_the_results_hold_no_marker(comparison)


def _checks(namespace):
    """Return the tests in ``namespace`` that read a policy's run, by name."""
    return {
        name: function
        for name, function in namespace.items()
        if name.startswith("test")
        and callable(function)
        and RUN_FIXTURES & set(inspect.signature(function).parameters)
    }


def _signature(function):
    return list(inspect.signature(function).parameters)


def _marks(function):
    return [
        (mark.name, mark.args, mark.kwargs)
        for mark in getattr(function, "pytestmark", [])
    ]


def test_each_check_of_a_policys_run_runs_in_both_halves(monkeypatch):
    """A check added to the first half fails here until this half runs it too."""
    first, here = _checks(vars(first_half)), _checks(globals())

    assert first
    assert sorted(here) == sorted(first)
    for name, function in here.items():
        assert _signature(function) == _signature(first[name]), name
        assert _marks(function) == _marks(first[name]), name
        # Each test here runs the first half's check on its own policy's run.
        calls = []
        monkeypatch.setattr(first_half, name, calls.append)
        sentinel = object()
        function(sentinel)
        assert calls == [sentinel], name
