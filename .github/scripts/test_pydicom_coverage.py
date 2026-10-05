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

"""Prove that reuse cannot hide an untested version or missing source evidence."""

import json
import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pydicom_coverage as coverage

COMMIT = "a" * 40
LOCK = {
    "package": [
        {
            "name": "pydicom",
            "version": "3.0.2",
            "source": {"registry": "https://pypi.org/simple"},
        }
    ]
}
PASSED = '<testsuites><testsuite><testcase name="case" /></testsuite></testsuites>'


class CoveragePlanMixin:
    def plan(self, **kwargs):
        inputs = {
            "lock": LOCK,
            "role": "minimum",
            "requested": "3.0.2",
            "quick": False,
            "python_matrix": ["3.11", "3.12", "3.13", "3.14"],
            "extra_args": "",
            "commit": COMMIT,
        }
        return coverage.make_plan(**(inputs | kwargs))


class CoveragePlanningTests(CoveragePlanMixin, unittest.TestCase):
    def test_both_roles_can_reference_the_complete_locked_suite(self):
        for role in ("minimum", "latest"):
            with self.subTest(role=role):
                plan = self.plan(role=role)
                self.assertEqual(plan["mode"], "reuse")
                self.assertEqual(plan["artifact"], coverage.BASELINE_ARTIFACT)
                self.assertEqual(plan["metadata"], coverage.BASELINE_METADATA)
                self.assertEqual(plan["commit"], COMMIT)

    def test_quick_always_selects_the_baseline_despite_a_custom_full_matrix(self):
        self.assertEqual(self.plan(quick=True, python_matrix=["3.11"])["mode"], "reuse")

    def test_unproven_equivalence_executes_each_requested_role(self):
        cases = (
            {"requested": "3.1.0"},
            {"python_matrix": ["3.11", "3.12"]},
            {"python_matrix": ["3.14.1"]},
            {"extra_args": "-k selected"},
            {"extra_args": " "},
            {"lock": {}},
            {"lock": {"package": LOCK["package"] * 2}},
            {"lock": {"package": [{**LOCK["package"][0], "source": {"git": "url"}}]}},
            {
                "lock": {
                    "package": [
                        {
                            **LOCK["package"][0],
                            "source": {"registry": "https://other.invalid/simple"},
                        }
                    ]
                }
            },
            {"lock": {"package": [{**LOCK["package"][0], "version": ""}]}},
        )
        for case in cases:
            for role in ("minimum", "latest"):
                with self.subTest(case=case, role=role):
                    plan = self.plan(role=role, **case)
                    self.assertEqual(plan["mode"], "execute")
                    self.assertEqual(plan["artifact"], f"junit-pydicom-{role}")

    def test_bad_inputs_cannot_select_reuse(self):
        for case in (
            {"requested": ""},
            {"requested": "3.0.2\nreuse=true"},
            {"requested": "pydicom==3.0.2"},
            {"requested": "3.0.2\nnumpy==2"},
            {"role": "other"},
            {"quick": "false"},
            {"python_matrix": "3.14"},
            {"python_matrix": [3.14]},
            {"commit": ""},
        ):
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.plan(**case)

    def test_minimum_drift_in_any_declaration_blocks_planning(self):
        project = {
            "project": {"optional-dependencies": {"user": ["pydicom>=3.0.2"]}},
            "dependency-groups": {
                "docs": ["pydicom>=3.0.2", {"include-group": "other"}]
            },
        }
        self.assertEqual(coverage.minimum_version(project, "3.0.2"), "3.0.2")
        for requirement in ("pydicom>=3.1.0", "pydicom>=3.0.2,<4"):
            project["dependency-groups"]["docs"][0] = requirement
            with self.subTest(requirement=requirement), self.assertRaises(ValueError):
                coverage.minimum_version(project, "3.0.2")
        with self.assertRaises(ValueError):
            coverage.minimum_version(
                {"project": {"optional-dependencies": {}}}, "3.0.2"
            )

    def test_coverage_sha_must_be_the_actual_checkout(self):
        with mock.patch.object(
            coverage.subprocess, "check_output", return_value=COMMIT + "\n"
        ) as command:
            self.assertEqual(coverage.checked_commit(COMMIT), COMMIT)
            command.assert_called_once_with(["git", "rev-parse", "HEAD"], text=True)
        with mock.patch.object(
            coverage.subprocess, "check_output", return_value="b" * 40
        ):
            with self.assertRaises(ValueError):
                coverage.checked_commit(COMMIT)


class CoverageEvidenceTests(CoveragePlanMixin, unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.results = Path(self.temporary.name)

    def report(self, name=coverage.BASELINE_ARTIFACT, text=PASSED):
        path = self.results / f"{name}.xml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_reuse_creates_a_reference_and_no_synthetic_junit(self):
        plan = coverage.record_coverage(self.plan(), None, self.results)
        self.assertEqual(list(self.results.glob("*.xml")), [])
        self.assertNotIn("actual_version", plan)
        self.assertEqual(plan["coverage_job_python_version"], platform.python_version())
        self.assertEqual(
            json.loads((self.results / "pydicom-coverage-minimum.json").read_text()),
            plan,
        )

    def test_baseline_binds_real_junit_to_the_imported_version_and_commit(self):
        self.report()
        metadata = coverage.record_baseline(LOCK, "3.0.2", COMMIT, self.results)
        self.assertEqual(metadata["actual_version"], "3.0.2")
        self.assertEqual(metadata["actual_python_version"], platform.python_version())
        self.assertEqual(metadata["commit"], COMMIT)
        self.assertEqual(
            json.loads((self.results / coverage.BASELINE_METADATA).read_text()),
            metadata,
        )

    def test_baseline_mismatch_or_bad_sha_cannot_create_metadata(self):
        self.report()
        for actual, commit in (("3.1.0", COMMIT), ("3.0.2", "")):
            with (
                self.subTest(actual=actual, commit=commit),
                self.assertRaises(ValueError),
            ):
                coverage.record_baseline(LOCK, actual, commit, self.results)
            self.assertFalse((self.results / coverage.BASELINE_METADATA).exists())

    def test_missing_or_failed_baseline_cannot_create_metadata(self):
        with self.assertRaises(FileNotFoundError):
            coverage.record_baseline(LOCK, "3.0.2", COMMIT, self.results)
        for text in (
            "<testsuites />",
            "<testsuite><testcase><failure /></testcase></testsuite>",
            "<testsuite><testcase><error /></testcase></testsuite>",
            '<testsuites failures="1"><testcase /></testsuites>',
            '<testsuite errors="1"><testcase /></testsuite>',
            '<testsuite failures="invalid"><testcase /></testsuite>',
        ):
            self.report(text=text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                coverage.record_baseline(LOCK, "3.0.2", COMMIT, self.results)
            self.assertFalse((self.results / coverage.BASELINE_METADATA).exists())

    def test_overlay_needs_its_real_report_and_actual_requested_version(self):
        plan = self.plan(role="latest", requested="3.1.0")
        with self.assertRaises(FileNotFoundError):
            coverage.record_coverage(plan, "3.1.0", self.results)
        self.report(name=plan["artifact"])
        with self.assertRaises(ValueError):
            coverage.record_coverage(plan, "3.0.2", self.results)
        recorded = coverage.record_coverage(plan, "3.1.0", self.results)
        self.assertEqual(recorded["actual_version"], "3.1.0")
        self.assertEqual(recorded["actual_python_version"], platform.python_version())
        self.assertEqual(recorded["artifact"], "junit-pydicom-latest")

    def test_malformed_reuse_references_fail_before_recording(self):
        for changes in (
            {"mode": "unknown"},
            {"locked_version": "3.1.0"},
            {"artifact": "wrong-report"},
            {"junit": "wrong.xml"},
            {"metadata": "wrong.json"},
            {"metadata_artifact": "wrong-artifact"},
            {"format": "unknown"},
            {"commit": ""},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                coverage.record_coverage(self.plan() | changes, None, self.results)
            self.assertFalse((self.results / "pydicom-coverage-minimum.json").exists())


class CoverageCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = {
            "PYDICOM": "latest",
            "PYDICOM_VERSION": "3.0.2",
            "QUICK": "false",
            "PYTHON_MATRIX": '["3.14"]',
            "EXTRA_PYTEST_ARGS": "",
            "CI_COMMIT": COMMIT,
            "GITHUB_OUTPUT": str(self.directory / "outputs"),
        }

    def run_plan(self, environment):
        with (
            mock.patch.object(coverage, "RESULTS", self.directory / "results"),
            mock.patch.object(coverage, "read_toml", return_value=LOCK),
            mock.patch.object(
                coverage, "checked_commit", side_effect=coverage.commit_sha
            ),
            mock.patch.object(coverage.sys, "argv", ["pydicom_coverage.py", "plan"]),
            mock.patch.dict(os.environ, environment, clear=True),
        ):
            coverage.main()

    def test_validated_plan_emits_only_explicit_selection_outputs(self):
        self.run_plan(self.environment)
        self.assertEqual(
            (self.directory / "outputs").read_text(), "version=3.0.2\nreuse=true\n"
        )
        manifest = json.loads(
            (self.directory / "results/pydicom-plan-latest.json").read_text()
        )
        self.assertEqual(manifest["artifact"], coverage.BASELINE_ARTIFACT)

    def test_missing_environment_fails_without_a_successful_selection(self):
        for field in self.environment:
            environment = self.environment.copy()
            del environment[field]
            with self.subTest(field=field), self.assertRaises((KeyError, ValueError)):
                self.run_plan(environment)
            self.assertFalse((self.directory / "outputs").exists())

    def test_invalid_environment_and_malformed_lookup_output_fail_closed(self):
        for changes in (
            {"QUICK": ""},
            {"QUICK": "False"},
            {"PYTHON_MATRIX": "invalid json"},
            {"PYTHON_MATRIX": "null"},
            {"PYDICOM_VERSION": "3.0.2\nreuse=true"},
            {"PYDICOM_VERSION": "pydicom==3.0.2"},
            {"PYDICOM": "unknown"},
            {"CI_COMMIT": "not a SHA"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.run_plan(self.environment | changes)
            self.assertFalse((self.directory / "outputs").exists())


if __name__ == "__main__":
    unittest.main()
