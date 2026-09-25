"""Regression tests for the merge-blocking workflow summary policy."""

import copy
import unittest

from check_workflow_status import check_jobs, make_summary


class WorkflowStatusTests(unittest.TestCase):
    def setUp(self):
        self.conditional = {
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
            "lint": {"result": "success"},
            "type-check": {"result": "success"},
            "unit-tests": {"result": "success"},
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
        self.needs["pre-commit"] = {
            "result": "failure",
            "outputs": {"autofix-pushed": "true"},
        }
        for job in ("lint", "type-check", "unit-tests"):
            self.needs[job]["result"] = "skipped"
        failures = check_jobs(self.needs, self.conditional)
        self.assertTrue(failures)
        summary = make_summary("CI Results", self.needs, self.conditional, failures)
        self.assertIn("new CI run must pass", summary)
        self.assertNotIn("All required checks passed", summary)

    def test_security_scans_follow_shared_selection(self):
        scans = ("dependency-audit", "python-security", "workflow-audit")
        conditional = dict.fromkeys(scans, "security")
        for selection in ("true", "false"):
            for result in ("success", "failure", "cancelled", "skipped"):
                with self.subTest(selection=selection, result=result):
                    needs = {
                        "changes": {
                            "result": "success",
                            "outputs": {"security": selection},
                        },
                        **{job: {"result": result} for job in scans},
                    }
                    should_pass = result == "success" or (
                        result == "skipped" and selection == "false"
                    )
                    self.assertEqual(not check_jobs(needs, conditional), should_pass)


if __name__ == "__main__":
    unittest.main()
