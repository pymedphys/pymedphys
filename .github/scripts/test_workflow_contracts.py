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

"""Protect the workflow gates and release dependency graph from regressions.

Read the small structural subset used by these workflows without adding a
runtime dependency to CI's bootstrap checks. Actionlint validates YAML and
GitHub expressions separately through pre-commit.
"""

import re
import unittest
from pathlib import Path

from select_checks import OUTPUTS

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"


def jobs(filename):
    text = (WORKFLOWS / filename).read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    starts = list(re.finditer(r"^  ([a-z][a-z0-9-]*):$", body, re.MULTILINE))
    return {
        match[1]: body[
            match.end() : starts[i + 1].start() if i + 1 < len(starts) else len(body)
        ]
        for i, match in enumerate(starts)
    }


def needs(job):
    match = re.search(
        r"^    needs: *(\[[^\]]*\]|(?:\n      - [^\n]+)+)", job, re.MULTILINE
    )
    return set(re.findall(r"[a-z][a-z0-9-]*", match[1])) if match else set()


class WorkflowContractTests(unittest.TestCase):
    def test_summaries_always_cover_every_job(self):
        for filename, summary_id, name in (
            ("ci.yml", "summary", "CI Summary"),
            ("security.yml", "security-summary", "Security Summary"),
            ("release.yml", "summary", "Release Summary"),
        ):
            with self.subTest(workflow=filename):
                workflow = jobs(filename)
                summary = workflow[summary_id]
                self.assertEqual(needs(summary), set(workflow) - {summary_id})
                self.assertIn("    if: always()", summary)
                self.assertIn(f"    name: {name}", summary)
                self.assertIn(
                    "python .github/scripts/check_workflow_status.py", summary
                )

    def test_conditional_jobs_and_gates_use_identical_selection(self):
        for filename, summary_id in (
            ("ci.yml", "summary"),
            ("security.yml", "security-summary"),
        ):
            workflow = jobs(filename)
            conditions = dict(
                re.findall(r"--conditional ([a-z-]+)=([a-z-]+)", workflow[summary_id])
            )
            selected_jobs = {
                job: re.search(r"needs.changes.outputs.([a-z-]+) == 'true'", body)[1]
                for job, body in workflow.items()
                if re.search(r"needs.changes.outputs.([a-z-]+) == 'true'", body)
            }
            self.assertEqual(conditions, selected_jobs)
            for job, output in conditions.items():
                with self.subTest(workflow=filename, job=job):
                    self.assertIn("changes", needs(workflow[job]))
                    self.assertIn(output, OUTPUTS)
                    self.assertIn(
                        f"{output}: ${{{{ steps.select.outputs.{output} }}}}",
                        workflow["changes"],
                    )
            self.assertIn("fetch-depth: 2", workflow["changes"])

    def test_publishing_waits_for_all_original_quality_gates(self):
        workflow = jobs("release.yml")
        pending = list(needs(workflow["publish-pypi"]))
        ancestors = set()
        while pending:
            job = pending.pop()
            if job not in ancestors:
                ancestors.add(job)
                pending.extend(needs(workflow[job]))
        self.assertTrue(
            {"lint", "type-check", "unit-tests", "integration-tests", "build"}
            <= ancestors
        )
        # Default success() is essential: never publish after a failed gate.
        self.assertNotRegex(workflow["publish-pypi"], r"(?m)^    if:")
        self.assertIn("      name: pypi", workflow["publish-pypi"])
        self.assertIn("skip-existing: true", workflow["publish-pypi"])
        self.assertIn("quick: false", workflow["unit-tests"])
        self.assertIn("run-slow: true", workflow["integration-tests"])
        self.assertIn("run-wheel-build: false", workflow["integration-tests"])
        self.assertIn("uv build", workflow["build"])
        self.assertIn(
            "check_distributions.py dist --expected-version", workflow["build"]
        )
        self.assertIn("uvx twine==7.0.0 check dist/*", workflow["build"])

    def test_release_assets_require_published_verification(self):
        workflow = jobs("release.yml")
        upload = workflow["upload-release-assets"]
        self.assertIn("verify-published", needs(upload))
        self.assertIn("needs.verify-published.result == 'success'", upload)
        self.assertIn("diff built.sha256 assets.sha256", upload)
        # Published tests resolve dependencies and datasets that change outside
        # the repository. They report to the summary but never hold back assets.
        self.assertNotIn("test-published", upload)
        self.assertNotIn("--tests", workflow["verify-published"])
        self.assertIn("--tests", workflow["test-published"])
        for job in ("verify-published", "test-published"):
            with self.subTest(job=job):
                body = workflow[job]
                self.assertIn("--published", body)
                self.assertIn("--compare-with dist", body)
                self.assertIn("publish-pypi", needs(body))
                self.assertIn("os: [ubuntu-latest, windows-latest, macos-latest]", body)
                self.assertIn("fail-fast: false", body)
                # Fresh environments, as a user's installation would be.
                self.assertNotIn("setup-project", body)
                self.assertNotIn("actions/cache", body)


if __name__ == "__main__":
    unittest.main()
