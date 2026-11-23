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

"""Cancel the CI and security runs of merge groups that the queue has dropped.

The merge queue builds each entry on a branch of its own under
``gh-readonly-queue/``, and deletes that branch when it drops the group: when
a group ahead of it fails or times out, or its pull request leaves the queue.
The group's runs carry on regardless, since each group's ref is its own
concurrency group and GitHub does not cancel them, and they hold runners that
the rebuilt groups need.

So a run of a watched workflow, started by a merge group, still queued or in
progress, whose branch no longer exists, is cancelled. Anything uncertain
keeps the run: a branch that still exists, a lookup that fails, or a run of
another workflow or event. A run that finishes before its cancellation is
left as it ended.

Usage: ``python .github/scripts/cancel_dropped_merge_groups.py`` with
``GH_TOKEN``, ``REPOSITORY`` (``owner/name``), and ``DEFAULT_BRANCH`` set, and
``GITHUB_API_URL`` when the API is not github.com's.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

# The workflows whose runs the required checks come from.
WATCHED_PATHS = frozenset(
    {".github/workflows/ci.yml", ".github/workflows/security.yml"}
)
# Every status of a run that has not finished.
ACTIVE_STATUSES = ("queued", "in_progress", "waiting", "requested", "pending")
QUEUE_PREFIX = "gh-readonly-queue/"
PER_PAGE = 100

# A request takes a method and a path below the repository and returns the
# HTTP status and the decoded JSON body (None when there is none).
Request = Callable[[str, str], tuple[int, Any]]


@dataclass(frozen=True)
class Run:
    """A workflow run of a merge group: its ID, workflow path and branch."""

    id: int
    path: str
    branch: str


def active_runs(request: Request) -> list[Run]:
    """Return each unfinished run of a watched workflow on a merge group."""
    runs: dict[int, Run] = {}
    for status in ACTIVE_STATUSES:
        for item in _pages(request, f"actions/runs?event=merge_group&status={status}"):
            run = _merge_group_run(item)
            if run is not None:
                runs[run.id] = run
    return [runs[key] for key in sorted(runs)]


def _pages(request: Request, path: str) -> Iterator[dict[str, Any]]:
    page = 1
    while True:
        status, body = request("GET", f"{path}&per_page={PER_PAGE}&page={page}")
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"Listing workflow runs returned HTTP {status}.")
        items = body.get("workflow_runs")
        if not isinstance(items, list):
            raise RuntimeError("Listing workflow runs returned no list of runs.")
        yield from (item for item in items if isinstance(item, dict))
        if len(items) < PER_PAGE:
            return
        page += 1


def _merge_group_run(item: dict[str, Any]) -> Run | None:
    run_id, path, branch = item.get("id"), item.get("path"), item.get("head_branch")
    if (
        item.get("event") != "merge_group"
        or not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or path not in WATCHED_PATHS
        or not isinstance(branch, str)
        or not branch.startswith(QUEUE_PREFIX)
    ):
        return None
    return Run(run_id, path, branch)


def branch_exists(request: Request, branch: str) -> bool:
    """Return whether a branch exists; a failed lookup counts as existing."""
    status, _ = request("GET", f"git/ref/heads/{urllib.parse.quote(branch, safe='/')}")
    return status != 404


def dropped_runs(request: Request, runs: Iterable[Run], known_branch: str) -> list[Run]:
    """Return the runs whose merge group branch no longer exists.

    A branch that must exist, such as the default branch, is looked up first,
    so a token that cannot read branches cancels nothing rather than
    everything.
    """
    status, _ = request(
        "GET", f"git/ref/heads/{urllib.parse.quote(known_branch, safe='/')}"
    )
    if status != 200:
        raise RuntimeError(f"Looking up {known_branch} returned HTTP {status}.")
    exists: dict[str, bool] = {}
    dropped = []
    for run in runs:
        if run.branch not in exists:
            exists[run.branch] = branch_exists(request, run.branch)
        if not exists[run.branch]:
            dropped.append(run)
    return dropped


def cancel(request: Request, run: Run) -> bool:
    """Cancel a run; return False when it had finished already."""
    status, _ = request("POST", f"actions/runs/{run.id}/cancel")
    if status == 202:
        return True
    # GitHub answers 409 Conflict for a run that has already completed.
    if status == 409:
        return False
    raise RuntimeError(f"Cancelling run {run.id} returned HTTP {status}.")


def github_request(api_url: str, repository: str, token: str) -> Request:
    """Return a Request for one repository's REST API."""
    parsed = urllib.parse.urlsplit(api_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("The API URL must be an https URL.")
    base = f"{api_url.rstrip('/')}/repos/{repository}/"

    def request(method: str, path: str) -> tuple[int, Any]:
        call = urllib.request.Request(
            base + path,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            # The scheme is checked above, so this opens no local file.
            with urllib.request.urlopen(call, timeout=30) as response:  # nosec B310
                status, data = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, data = error.code, error.read()
        return status, json.loads(data) if data else None

    return request


def main() -> int:
    token = os.environ["GH_TOKEN"]
    repository = os.environ["REPOSITORY"]
    default_branch = os.environ["DEFAULT_BRANCH"]
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    request = github_request(api_url, repository, token)
    runs = active_runs(request)
    dropped = dropped_runs(request, runs, default_branch)
    print(f"{len(runs)} unfinished merge group runs; {len(dropped)} dropped.")
    for run in dropped:
        outcome = "cancelled" if cancel(request, run) else "had finished"
        print(f"Run {run.id} ({run.path}, {run.branch}): {outcome}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
