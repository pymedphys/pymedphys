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

"""Test that only runs of dropped merge groups are cancelled."""

from __future__ import annotations

import io
import unittest
import urllib.error
from typing import Any
from unittest import mock

import cancel_dropped_merge_groups as cleanup

LIVE = "gh-readonly-queue/main/pr-1-aaaa"
DROPPED = "gh-readonly-queue/main/pr-2-bbbb"
CI = ".github/workflows/ci.yml"
SECURITY = ".github/workflows/security.yml"


def run(run_id: int, branch: str, path: str = CI, **extra: Any) -> dict[str, Any]:
    return {
        "id": run_id,
        "event": "merge_group",
        "path": path,
        "head_branch": branch,
        **extra,
    }


class FakeApi:
    """Answer the listing, branch and cancel requests the script makes."""

    def __init__(
        self,
        runs: dict[str, list[dict[str, Any]]],
        branches: dict[str, int],
        cancel_status: int = 202,
    ) -> None:
        self.runs = runs
        self.branches = {"main": 200, **branches}
        self.cancel_status = cancel_status
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, path: str) -> tuple[int, Any]:
        self.calls.append((method, path))
        if method == "GET" and path.startswith("actions/runs?"):
            query = dict(
                part.split("=", 1) for part in path.split("?", 1)[1].split("&")
            )
            assert query["event"] == "merge_group"
            items = self.runs.get(query["status"], [])
            size, page = int(query["per_page"]), int(query["page"])
            return 200, {"workflow_runs": items[(page - 1) * size : page * size]}
        if method == "GET" and path.startswith("git/ref/heads/"):
            branch = path.removeprefix("git/ref/heads/")
            return self.branches.get(branch, 404), None
        if method == "POST" and path.endswith("/cancel"):
            return self.cancel_status, None
        raise AssertionError(f"Unexpected request {method} {path}")

    def cancelled(self) -> list[str]:
        return [path for method, path in self.calls if method == "POST"]


class ActiveRunsTests(unittest.TestCase):
    def test_every_unfinished_status_is_listed_once(self):
        api = FakeApi(
            {
                "queued": [run(3, LIVE)],
                "in_progress": [run(1, LIVE), run(2, DROPPED, SECURITY)],
                "waiting": [run(1, LIVE)],
            },
            {},
        )
        runs = cleanup.active_runs(api)
        self.assertEqual([r.id for r in runs], [1, 2, 3])
        listed = {
            path.split("status=", 1)[1].split("&", 1)[0]
            for method, path in api.calls
            if path.startswith("actions/runs?")
        }
        self.assertEqual(listed, set(cleanup.ACTIVE_STATUSES))

    def test_other_workflows_events_and_branches_are_ignored(self):
        api = FakeApi(
            {
                "in_progress": [
                    run(1, DROPPED, ".github/workflows/midi-b-benchmark.yml"),
                    run(2, DROPPED, event="pull_request"),
                    run(3, "main"),
                    run(4, None),
                    run(True, DROPPED),
                    run("5", DROPPED),
                    {"id": 6},
                    "not a run",
                ]
            },
            {},
        )
        self.assertEqual(cleanup.active_runs(api), [])

    def test_every_page_is_read(self):
        many = [run(i, LIVE) for i in range(1, cleanup.PER_PAGE + 2)]
        api = FakeApi({"in_progress": many}, {})
        self.assertEqual(len(cleanup.active_runs(api)), cleanup.PER_PAGE + 1)

    def test_a_failed_listing_stops_the_run(self):
        def request(method: str, path: str) -> tuple[int, Any]:
            return 500, None

        with self.assertRaises(RuntimeError):
            cleanup.active_runs(request)

    def test_a_listing_without_runs_stops_the_run(self):
        def request(method: str, path: str) -> tuple[int, Any]:
            return 200, {"message": "no runs here"}

        with self.assertRaises(RuntimeError):
            cleanup.active_runs(request)


class DroppedRunsTests(unittest.TestCase):
    def test_only_runs_without_their_branch_are_dropped(self):
        api = FakeApi({}, {LIVE: 200})
        runs = [
            cleanup.Run(1, CI, LIVE),
            cleanup.Run(2, CI, DROPPED),
            cleanup.Run(3, SECURITY, DROPPED),
        ]
        dropped = cleanup.dropped_runs(api, runs, "main")
        self.assertEqual([r.id for r in dropped], [2, 3])
        # Each branch is looked up once.
        lookups = [path for _, path in api.calls if path.startswith("git/ref/")]
        self.assertEqual(
            lookups,
            ["git/ref/heads/main", f"git/ref/heads/{LIVE}", f"git/ref/heads/{DROPPED}"],
        )

    def test_a_failed_branch_lookup_keeps_the_run(self):
        for status in (401, 403, 500, 502):
            with self.subTest(status=status):
                api = FakeApi({}, {DROPPED: status})
                runs = [cleanup.Run(1, CI, DROPPED)]
                self.assertEqual(cleanup.dropped_runs(api, runs, "main"), [])

    def test_a_token_that_cannot_read_branches_cancels_nothing(self):
        # Every lookup would answer 404, which would look like every group
        # had been dropped.
        api = FakeApi({}, {"main": 404})
        with self.assertRaises(RuntimeError):
            cleanup.dropped_runs(api, [cleanup.Run(1, CI, DROPPED)], "main")

    def test_branch_names_are_quoted(self):
        api = FakeApi({}, {})
        cleanup.branch_exists(api, "gh-readonly-queue/main/pr-1-a b?c")
        self.assertEqual(
            api.calls, [("GET", "git/ref/heads/gh-readonly-queue/main/pr-1-a%20b%3Fc")]
        )


class CancelTests(unittest.TestCase):
    def test_accepted_and_already_finished(self):
        for status, expected in ((202, True), (409, False)):
            with self.subTest(status=status):
                api = FakeApi({}, {}, cancel_status=status)
                self.assertIs(
                    cleanup.cancel(api, cleanup.Run(7, CI, DROPPED)), expected
                )
                self.assertEqual(api.cancelled(), ["actions/runs/7/cancel"])

    def test_other_answers_fail(self):
        api = FakeApi({}, {}, cancel_status=403)
        with self.assertRaises(RuntimeError):
            cleanup.cancel(api, cleanup.Run(7, CI, DROPPED))


class MainTests(unittest.TestCase):
    def test_cancels_only_the_dropped_groups_runs(self):
        api = FakeApi(
            {"in_progress": [run(1, LIVE), run(2, DROPPED), run(3, DROPPED, SECURITY)]},
            {LIVE: 200},
        )
        environ = {"GH_TOKEN": "t", "REPOSITORY": "o/r", "DEFAULT_BRANCH": "main"}
        with (
            mock.patch.dict(cleanup.os.environ, environ, clear=True),
            mock.patch.object(cleanup, "github_request", return_value=api),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            self.assertEqual(cleanup.main(), 0)
        self.assertEqual(
            api.cancelled(), ["actions/runs/2/cancel", "actions/runs/3/cancel"]
        )
        self.assertIn("3 unfinished merge group runs; 2 dropped.", out.getvalue())


class GithubRequestTests(unittest.TestCase):
    def test_only_https_is_accepted(self):
        for url in ("http://api.github.com", "file:///etc/passwd", "api.github.com"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                cleanup.github_request(url, "o/r", "t")

    def test_requests_carry_the_token_and_decode_errors(self):
        request = cleanup.github_request("https://api.example.com/", "o/r", "secret")
        seen = []

        class Response(io.BytesIO):
            status = 200

        def urlopen(call, timeout):
            seen.append(call)
            if call.get_method() == "POST":
                raise urllib.error.HTTPError(
                    call.full_url, 409, "Conflict", {}, io.BytesIO(b'{"m": 1}')
                )
            return Response(b'{"workflow_runs": []}')

        with mock.patch.object(cleanup.urllib.request, "urlopen", urlopen):
            self.assertEqual(
                request("GET", "actions/runs?x=1"), (200, {"workflow_runs": []})
            )
            self.assertEqual(request("POST", "actions/runs/1/cancel"), (409, {"m": 1}))
        self.assertEqual(
            seen[0].full_url, "https://api.example.com/repos/o/r/actions/runs?x=1"
        )
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer secret")
        self.assertEqual(seen[1].get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
