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

"""Regression tests for the merge-blocking workflow summary policy."""

import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_workflow_status
from check_workflow_status import check_jobs, make_summary


class WorkflowStatusTests(unittest.TestCase):
    def setUp(self):
        self.conditional = {
            "lint": "run-python",
            "type-check": "run-python",
            "unit-tests": "run-python",
            "script-tests": "run-scripts",
            "integration-tests": "run-integration",
            "mosaiq-db-tests": "run-database",
            "docs-check": "run-docs",
        }
        self.needs = {
            "changes": {
                "result": "success",
                "outputs": dict.fromkeys(self.conditional.values(), "false"),
            },
            "pre-commit": {"result": "success", "outputs": {}},
            **{job: {"result": "skipped"} for job in self.conditional},
        }

    def test_intentionally_skipped_extended_jobs_pass(self):
        self.assertEqual(check_jobs(self.needs, self.conditional), [])

    def test_every_core_job_must_succeed(self):
        for job in self.needs.keys() - self.conditional.keys():
            for result in ("failure", "cancelled", "skipped", None):
                with self.subTest(job=job, result=result):
                    needs = copy.deepcopy(self.needs)
                    needs[job]["result"] = result
                    self.assertTrue(check_jobs(needs, self.conditional))

    def test_selected_extended_jobs_must_succeed(self):
        for job, output in self.conditional.items():
            for result in ("failure", "cancelled", "skipped", None, "success"):
                with self.subTest(job=job, result=result):
                    needs = copy.deepcopy(self.needs)
                    needs["changes"]["outputs"][output] = "true"
                    for selected_job, selected_output in self.conditional.items():
                        if selected_output == output:
                            needs[selected_job]["result"] = "success"
                    needs[job]["result"] = result
                    self.assertEqual(
                        bool(check_jobs(needs, self.conditional)), result != "success"
                    )

    def test_unselected_jobs_cannot_hide_a_failure(self):
        for job in self.conditional:
            for result in ("failure", "cancelled", "success"):
                with self.subTest(job=job, result=result):
                    needs = copy.deepcopy(self.needs)
                    needs[job]["result"] = result
                    self.assertEqual(
                        bool(check_jobs(needs, self.conditional)), result != "success"
                    )

    def test_missing_or_invalid_selection_cannot_authorize_skip(self):
        for output in self.conditional.values():
            for value in (None, "", "TRUE", True):
                with self.subTest(output=output, value=value):
                    needs = copy.deepcopy(self.needs)
                    needs["changes"]["outputs"][output] = value
                    self.assertTrue(check_jobs(needs, self.conditional))

    def test_missing_dependencies_fail(self):
        for job in ("changes", *self.conditional):
            with self.subTest(job=job):
                needs = copy.deepcopy(self.needs)
                del needs[job]
                self.assertTrue(check_jobs(needs, self.conditional))

    def test_new_dependencies_are_required_by_default(self):
        self.needs["new-check"] = {"result": "skipped"}
        self.assertTrue(check_jobs(self.needs, self.conditional))

    def test_autofix_does_not_make_unverified_commit_green(self):
        # A Python change selects these jobs; the auto-fix push skips them.
        self.needs["changes"]["outputs"]["run-python"] = "true"
        self.needs["pre-commit"] = {
            "result": "failure",
            "outputs": {"autofix-pushed": "true"},
        }
        for job in ("lint", "type-check", "unit-tests"):
            self.needs[job]["result"] = "skipped"
        failures = check_jobs(self.needs, self.conditional)
        for job in ("pre-commit", "lint", "type-check", "unit-tests"):
            with self.subTest(job=job):
                self.assertTrue(any(f.startswith(f"{job}:") for f in failures))
        summary = make_summary("CI Results", self.needs, self.conditional, failures)
        self.assertIn("new CI run must pass", summary)
        self.assertNotIn("All required checks passed", summary)

    def test_security_scans_follow_independent_selection(self):
        scans = ("dependency-audit", "python-security", "workflow-audit")
        conditional = {job: f"run-{job}" for job in scans}
        for selection in ("true", "false"):
            for result in ("success", "failure", "cancelled", "skipped"):
                with self.subTest(selection=selection, result=result):
                    needs = {
                        "changes": {
                            "result": "success",
                            "outputs": dict.fromkeys(conditional.values(), selection),
                        },
                        **{job: {"result": result} for job in scans},
                    }
                    should_pass = result == "success" or (
                        result == "skipped" and selection == "false"
                    )
                    self.assertEqual(not check_jobs(needs, conditional), should_pass)


class MergeGroupTests(unittest.TestCase):
    """A merge group skips the changes job and must run every other job."""

    def setUp(self):
        self.conditional = {
            "lint": "run-python",
            "unit-tests": "run-python",
            "docs-check": "run-docs",
        }
        self.needs = {
            "changes": {"result": "skipped", "outputs": {}},
            "pre-commit": {"result": "success", "outputs": {}},
            **{job: {"result": "success"} for job in self.conditional},
        }

    def test_every_job_succeeding_passes(self):
        self.assertEqual(check_jobs(self.needs, self.conditional, merge_group=True), [])
        summary = make_summary(
            "CI Results", self.needs, self.conditional, [], merge_group=True
        )
        self.assertIn("| changes | no | skipped |", summary)
        self.assertIn("| docs-check | yes | success |", summary)
        self.assertIn("All required checks passed", summary)

    def test_no_conditional_job_may_be_skipped(self):
        for job in ("pre-commit", *self.conditional):
            for result in ("skipped", "failure", "cancelled", None):
                with self.subTest(job=job, result=result):
                    needs = copy.deepcopy(self.needs)
                    needs[job]["result"] = result
                    failures = check_jobs(needs, self.conditional, merge_group=True)
                    self.assertTrue(any(f.startswith(f"{job}:") for f in failures))

    def test_the_changes_job_must_have_been_skipped(self):
        # A changes job that ran means the workflow's conditions and this
        # rule disagree; its selection could have skipped a check.
        for result in ("success", "failure", "cancelled", None):
            with self.subTest(result=result):
                needs = copy.deepcopy(self.needs)
                needs["changes"]["result"] = result
                self.assertTrue(check_jobs(needs, self.conditional, merge_group=True))

    def test_missing_dependencies_fail(self):
        for job in ("changes", *self.conditional):
            with self.subTest(job=job):
                needs = copy.deepcopy(self.needs)
                del needs[job]
                self.assertTrue(check_jobs(needs, self.conditional, merge_group=True))

    def test_the_option_applies_only_to_merge_groups(self):
        def summarise(event: str, *options: str) -> int:
            with tempfile.TemporaryDirectory() as directory:
                environ = {
                    "NEEDS_JSON": json.dumps(self.needs),
                    "GITHUB_STEP_SUMMARY": str(Path(directory) / "summary.md"),
                    "GITHUB_EVENT_NAME": event,
                }
                argv = [
                    "check_workflow_status.py",
                    "--title",
                    "CI Results",
                    *options,
                    *(
                        f"--conditional={job}={output}"
                        for job, output in self.conditional.items()
                    ),
                ]
                with (
                    mock.patch.dict(os.environ, environ, clear=True),
                    mock.patch("sys.argv", argv),
                    mock.patch("sys.stdout", new_callable=io.StringIO),
                ):
                    return check_workflow_status.main()

        option = "--merge-group-runs-every-check"
        self.assertEqual(summarise("merge_group", option), 0)
        # Without the option, or outside a merge group, a skipped changes
        # job with no selection fails closed, as before.
        self.assertEqual(summarise("merge_group"), 1)
        self.assertEqual(summarise("pull_request", option), 1)
        self.assertEqual(summarise("push", option), 1)


class UnconditionalSummaryTests(unittest.TestCase):
    """A summary without change selection, such as the release workflow's."""

    def setUp(self):
        self.needs = {
            "build": {"result": "success"},
            "publish-pypi": {"result": "success"},
        }

    def test_every_job_succeeding_passes_without_a_changes_job(self):
        self.assertEqual(check_jobs(self.needs, {}), [])
        summary = make_summary("Release Summary", self.needs, {}, [])
        self.assertIn("| publish-pypi | yes | success |", summary)
        self.assertIn("All required checks passed", summary)

    def test_every_job_must_succeed(self):
        for result in ("failure", "cancelled", "skipped", None):
            with self.subTest(result=result):
                needs = copy.deepcopy(self.needs)
                needs["publish-pypi"]["result"] = result
                self.assertTrue(check_jobs(needs, {}))


if __name__ == "__main__":
    unittest.main()
