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

"""The benchmark workers time revisions on either side of PyMedPhys 0.42.0.

That version renamed several options of ``pymedphys.gamma`` and made it
return a result in place of an array. The workers describe each case with
the earlier option names, and adapt the call to the revision they import.
"""

import importlib.util
import inspect
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import pymedphys

import gamma_performance

HERE = Path(__file__).parent

# Every option the workers pass, under the names from before 0.42.0.
EARLIER_OPTIONS = {
    "dose_percent_threshold": 3,
    "distance_mm_threshold": 2,
    "lower_percent_dose_cutoff": 10,
    "interp_fraction": 20,
    "global_normalisation": 2.0,
    "skip_once_passed": False,
    "random_subset": None,
    "ram_available": 2**28,
    "interp_algo": "scipy",
    "local_gamma": True,
    "max_gamma": 2,
}
RENAMED_OPTIONS = {
    "dose_criterion_percent": 3,
    "distance_criterion_mm": 2,
    "lower_dose_cutoff_percent": 10,
    "search_step_fraction": 1 / 20,
    "normalisation_dose": 2.0,
    "skip_once_passed": False,
    "random_subset": None,
    "memory_budget_bytes": 2**28,
    "interpolator": "scipy",
    "normalisation": "local",
    "gamma_cap": 2,
}


def earlier_gamma(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_percent_threshold,
    distance_mm_threshold,
    lower_percent_dose_cutoff=20,
    interp_fraction=10,
    max_gamma=None,
    local_gamma=False,
    global_normalisation=None,
    skip_once_passed=False,
    random_subset=None,
    ram_available=None,
    quiet=None,
    interp_algo="pymedphys",
):
    """The signature of ``pymedphys.gamma`` before version 0.42.0."""


def load_workers():
    performance = types.ModuleType("gamma_performance_worker")
    exec(  # pylint: disable = exec-used
        compile(gamma_performance.WORKER, "gamma_performance_worker.py", "exec"),
        performance.__dict__,
    )
    spec = importlib.util.spec_from_file_location(
        "gamma_scaling_worker", HERE / "gamma_scaling_worker.py"
    )
    scaling = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scaling)

    return {"performance": performance, "scaling": scaling}


class GammaCallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workers = load_workers()

    def test_a_revision_with_the_earlier_names_is_called_as_before(self):
        array = np.ones(3)
        for name, worker in self.workers.items():
            with self.subTest(worker=name):
                with mock.patch.object(pymedphys, "gamma", earlier_gamma):
                    options, interface, as_array = worker.gamma_call(EARLIER_OPTIONS)
                self.assertEqual(options, EARLIER_OPTIONS)
                self.assertEqual(interface, "array")
                self.assertIs(as_array(array), array)

    def test_options_are_renamed_for_a_revision_from_0_42_0(self):
        array = np.ones(3)
        for name, worker in self.workers.items():
            with self.subTest(worker=name):
                options, interface, as_array = worker.gamma_call(EARLIER_OPTIONS)
                self.assertEqual(options, RENAMED_OPTIONS)
                self.assertEqual(interface, "result")
                self.assertIs(as_array(types.SimpleNamespace(gamma=array)), array)

    def test_global_gamma_selects_global_normalisation(self):
        for name, worker in self.workers.items():
            with self.subTest(worker=name):
                options, _, _ = worker.gamma_call({"local_gamma": False})
                self.assertEqual(options, {"normalisation": "global"})

    def test_renamed_options_are_options_of_this_checkout(self):
        # Guards the tables above against a later change to the interface.
        parameters = inspect.signature(pymedphys.gamma).parameters
        self.assertLessEqual(set(RENAMED_OPTIONS), set(parameters))
        self.assertFalse(set(EARLIER_OPTIONS) & set(parameters) - set(RENAMED_OPTIONS))

    def test_a_translated_call_returns_the_array_of_the_result(self):
        axis = np.arange(6.0)
        reference = np.array([0.1, 1.0, 1.0, 1.0, 1.0, 1.0])
        evaluation = reference * 1.02
        options = {
            "dose_percent_threshold": 3,
            "distance_mm_threshold": 1,
            "lower_percent_dose_cutoff": 20,
            "max_gamma": 2,
            "local_gamma": True,
        }
        for name, worker in self.workers.items():
            with self.subTest(worker=name):
                call_options, _, as_array = worker.gamma_call(options)
                gamma = as_array(
                    pymedphys.gamma(axis, reference, axis, evaluation, **call_options)
                )
                # A 2% difference against a 3% local criterion at each of
                # the five points above the cutoff.
                self.assertTrue(np.isnan(gamma[0]))
                np.testing.assert_allclose(gamma[1:], 2 / 3, rtol=0, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
