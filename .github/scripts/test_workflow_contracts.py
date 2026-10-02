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

import fnmatch
import json
import re
import unittest
from pathlib import Path

from select_checks import OUTPUTS

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"


def jobs(filename: str) -> dict[str, str]:
    """Map each job ID in a workflow to the text of its definition."""
    text = (WORKFLOWS / filename).read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    starts = list(re.finditer(r"^  ([a-z][a-z0-9-]*):$", body, re.MULTILINE))
    return {
        match[1]: body[
            match.end() : starts[i + 1].start() if i + 1 < len(starts) else len(body)
        ]
        for i, match in enumerate(starts)
    }


def needs(job: str) -> set[str]:
    """Return the job IDs in a job definition's needs, inline or as a list."""
    match = re.search(
        r"^    needs: *(\[[^\]]*\]|(?:\n      - [^\n]+)+)", job, re.MULTILINE
    )
    return set(re.findall(r"[a-z][a-z0-9-]*", match[1])) if match else set()


class WorkflowContractTests(unittest.TestCase):
    def test_merge_groups_run_both_required_workflows(self):
        for filename, summary_id, name in (
            ("ci.yml", "summary", "CI Summary"),
            ("security.yml", "security-summary", "Security Summary"),
        ):
            with self.subTest(workflow=filename):
                text = (WORKFLOWS / filename).read_text(encoding="utf-8")
                triggers = text.split("\npermissions:\n", 1)[0]
                for event in ("push", "pull_request", "merge_group"):
                    self.assertRegex(triggers, rf"(?m)^  {event}:$")
                self.assertEqual(
                    re.findall(r"(?m)^    name: (.+)$", jobs(filename)[summary_id]),
                    [name],
                )

    def test_merge_group_dependency_audit_is_advisory(self):
        audit = jobs("security.yml")["dependency-audit"]
        self.assertEqual(
            re.findall(r"(?m)^        continue-on-error: (.+)$", audit),
            [
                "${{ github.event_name == 'pull_request' || "
                "github.event_name == 'push' || "
                "github.event_name == 'merge_group' }}"
            ],
        )

    def test_weekly_updates_share_one_branch_and_base(self):
        # A manual run on a feature branch must not repurpose the shared PR.
        update = jobs("deps.yml")["update"]
        self.assertIn("    if: github.ref == 'refs/heads/main'", update)
        self.assertIn("          branch: deps/weekly-update", update)
        workflow = (WORKFLOWS / "deps.yml").read_text(encoding="utf-8")
        self.assertIn(
            "concurrency:\n  group: weekly-dependency-update\n"
            "  cancel-in-progress: false",
            workflow,
        )

    def test_summaries_always_cover_every_job(self):
        for filename, summary_id, name in (
            ("ci.yml", "summary", "CI Summary"),
            ("security.yml", "security-summary", "Security Summary"),
            ("release.yml", "summary", "Release Summary"),
        ):
            with self.subTest(workflow=filename):
                workflow = jobs(filename)
                summary = workflow[summary_id]
                # Only jobs that report the summary's result may follow it.
                reporters = {
                    job for job, body in workflow.items() if summary_id in needs(body)
                }
                self.assertEqual(
                    needs(summary), set(workflow) - {summary_id} - reporters
                )
                self.assertIn("    if: always()", summary)
                self.assertIn(f"    name: {name}", summary)
                self.assertIn(
                    "python .github/scripts/check_workflow_status.py", summary
                )

    def test_only_the_main_failure_report_follows_the_ci_summary(self):
        workflow = jobs("ci.yml")
        reporters = {job for job, body in workflow.items() if "summary" in needs(body)}
        self.assertEqual(reporters, {"report-main-failure"})
        report = workflow["report-main-failure"]
        # It must never run for pull requests, and needs only to write issues.
        self.assertIn(
            "    if: failure() && github.event_name == 'push' && "
            "github.ref == 'refs/heads/main'",
            report,
        )
        self.assertIn("    permissions:\n      issues: write\n    steps:", report)
        self.assertIn('title="CI failed on main"', report)

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

    def test_selected_jobs_do_not_wait_for_pre_commit(self):
        # Selected checks start alongside pre-commit and run whatever its
        # result, so contributors get every result in one run. The summary
        # still waits for pre-commit and fails on its failure.
        workflow = jobs("ci.yml")
        selected = [
            job for job, body in workflow.items() if "needs.changes.outputs." in body
        ]
        self.assertTrue(selected)
        for job in selected:
            with self.subTest(job=job):
                self.assertEqual(needs(workflow[job]), {"changes"})
        self.assertIn("pre-commit", needs(workflow["summary"]))

    def test_the_selector_alone_reads_labels_and_the_matrix_fails_closed(self):
        for filename in ("ci.yml", "security.yml"):
            with self.subTest(workflow=filename):
                text = (WORKFLOWS / filename).read_text(encoding="utf-8")
                self.assertNotIn("pull_request.labels", text)
        workflow = jobs("ci.yml")
        self.assertIn(
            "run-full-matrix: ${{ steps.select.outputs.run-full-matrix }}",
            workflow["changes"],
        )
        self.assertIn("run-full-matrix", OUTPUTS)
        self.assertRegex(
            workflow["unit-tests"],
            r"\n      quick: \$\{\{ needs\.changes\.outputs\.run-full-matrix "
            r"== 'false' \}\}\n",
        )

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

    def test_the_deid_matrix_reads_every_full_unit_test_report(self):
        workflow = jobs("release.yml")
        render = workflow["deid-matrix"]
        self.assertIn("unit-tests", needs(render))
        self.assertIn("    if: ${{ !cancelled() }}", render)
        pattern = re.search(r"(?m)^          pattern: (\S+)$", render)[1]
        # Each environment of the OS and Python matrix, but not the narrow
        # extras', the dependency floors', or the pydicom versions' reports,
        # which run only some tests or would make the others partly run.
        names = re.findall(
            r"(?m)^          name: (junit-.+)$",
            (WORKFLOWS / "unit-tests.yml").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            names,
            [
                "junit-${{ matrix.os }}-${{ matrix.python-version }}",
                "junit-extra-${{ matrix.extra }}",
                "junit-dependency-floors",
                "junit-pydicom-${{ matrix.pydicom }}",
            ],
        )
        for os_name in ("ubuntu-latest", "windows-latest", "macos-latest"):
            with self.subTest(os=os_name):
                self.assertTrue(fnmatch.fnmatchcase(f"junit-{os_name}-3.11", pattern))
        for name in (
            "junit-extra-dicom",
            "junit-dependency-floors",
            "junit-pydicom-minimum",
            "junit-pydicom-latest",
        ):
            with self.subTest(name=name):
                self.assertFalse(fnmatch.fnmatchcase(name, pattern))
        self.assertIn("merge-multiple: true", render)
        # A report that never arrived fails the check: the expected reports
        # are the unit-test matrix's operating systems and Python versions.
        unit_tests = (WORKFLOWS / "unit-tests.yml").read_text(encoding="utf-8")
        oses = re.search(
            r"\|\| fromJSON\('(\[[^\]]*\])'\) \}\}\n *python-version:", unit_tests
        )[1]
        pythons = re.search(r"default: '(\[[^\]]*\])'", unit_tests)[1]
        for key, value in (("OSES", oses), ("PYTHONS", pythons)):
            with self.subTest(key=key):
                listed = " ".join(json.loads(value))
                self.assertIn(f"          {key}: {listed}\n", render)
        self.assertIn('[ -f "junit/junit-${os}-${python}.xml" ]', render)
        self.assertIn("pymedphys dev deid-matrix", render)
        self.assertIn("--check", render)
        # A failed check fails the job once the matrix is uploaded.
        self.assertIn("|| status=$?", render)
        self.assertIn(
            "      - name: Fail if a traced test did not pass\n"
            "        if: ${{ steps.matrix.outputs.status != '0' }}\n"
            "        run: exit 1\n",
            render,
        )
        # The job that runs the package reads only; a separate job attaches
        # the matrix to the release.
        self.assertIn("    permissions:\n      contents: read\n", render)
        self.assertNotIn(": write", render)
        upload = workflow["upload-deid-matrix"]
        self.assertEqual(needs(upload), {"build", "deid-matrix"})
        # Whenever a matrix was written, including when the check failed, for
        # a release whose tag and build passed.
        self.assertIn(
            "    if: >-\n      !cancelled() && needs.build.result == 'success' &&\n"
            "      needs.deid-matrix.outputs.written == 'true'\n",
            upload,
        )
        self.assertIn("    permissions:\n      contents: write\n", upload)
        for code in ("actions/checkout", "setup-project", "uv run"):
            with self.subTest(code=code):
                self.assertNotIn(code, upload)
        self.assertIn("gh release upload", upload)
        # Requirements evidence never holds back publishing.
        for job in ("deid-matrix", "upload-deid-matrix"):
            with self.subTest(job=job):
                self.assertNotIn(job, needs(workflow["publish-pypi"]))
                self.assertNotIn(job, needs(workflow["upload-release-assets"]))


if __name__ == "__main__":
    unittest.main()
