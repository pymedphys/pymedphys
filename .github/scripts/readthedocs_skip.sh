#!/usr/bin/env bash
# Copyright (C) 2026 Matthew Jennings
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Cancel a Read the Docs pull-request build that cannot change the site.
#
# Read the Docs runs this after checkout; exit code 183 cancels the build.
# Only pull-request builds are cancelled, and only when every path that
# differs from main is one the documentation build never reads: CI
# configuration and tooling, the tests (autodoc and the notebooks import only
# package modules), and agent and security guidance that no page includes.
# Any other path, or a comparison that fails, builds as usual. CI's
# documentation job still builds every pull request that changes a
# documentation input.
set -u

if [[ "${READTHEDOCS_VERSION_TYPE:-}" != "external" ]]; then
  exit 0
fi

# Read the Docs clones main before fetching the pull request, so origin/main
# is available. Exit status 0 means no difference outside the listed paths.
if git diff --quiet origin/main -- . \
  ':(exclude).github' \
  ':(exclude)lib/pymedphys/tests' \
  ':(exclude)AGENTS.md' \
  ':(exclude)CLAUDE.md' \
  ':(exclude)SECURITY.md' \
  ':(exclude).pre-commit-config.yaml' \
  ':(exclude)claude_created_workflows_preview'; then
  echo "No documentation input differs from main, so this preview build is cancelled."
  exit 183
fi
