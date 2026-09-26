# Contributing to PyMedPhys

Use a branch based on `main`, or on the branch of an open pull request that your
change depends on, and open a pull request for your changes.
The older `master` and release-maintenance branches are retained as read-only
history.

## Set up a development environment

Start with the [workstation setup guides](https://docs.pymedphys.com/en/latest/contrib/setups/index.html)
for Windows, Linux, or macOS. With Git and
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed, run:

```bash
git clone https://github.com/pymedphys/pymedphys.git
cd pymedphys
uv python install 3.12
uv sync --python 3.12 --locked --extra all --group dev
uv run pre-commit install
```

If you do not have permission to push to this repository, fork it first and
clone your fork instead. Create a working branch before committing.

The development environment uses the dependencies recorded in `uv.lock`.
The current source supports Python 3.10–3.12; Python 3.12 matches the quick CI
run. See the [repository guide](https://docs.pymedphys.com/en/latest/contrib/info/file-structure.html)
for the source layout.

## Check your changes

From the repository root:

```bash
uv run pre-commit run --all-files
uv run pymedphys dev tests -m "not slow"
uv run pymedphys dev docs
```

The [documentation guide](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html)
explains where to edit pages and how to inspect the built site.
The [workflow guide](https://docs.pymedphys.com/en/latest/contrib/info/workflows.html)
describes additional checks, conditional coverage, and troubleshooting.

## Open and review a pull request

These rules apply to every pull request. `CLAUDE.md` refers to them rather
than restating them.

- **Scope.** Keep each pull request small, digestible, and focused on one
  concern. As a sizing guide, aim for no more than about 400 lines of
  hand-written change, excluding tests and documentation; all files still need
  to be reviewable. Split larger work before requesting review. Keep generated
  data (lock files, generated tables, propagated requirements) separate from
  hand-written logic where possible, so reviewers check the generator and its
  tests rather than the generated lines.
- **Documentation and evidence.** Ship relevant tests and evidence with the
  change: NumPy-style docstrings for new or changed public functions, classes,
  and CLI options (behaviour, failure modes, and any standard clause they
  implement), user documentation for user-visible changes, and a
  `CHANGELOG.md` entry. Documentation-only changes need documentation checks,
  such as a documentation build with warnings as errors, not invented runtime
  tests or docstrings.
- **Changelog.** Consolidate related entries made on the same branch: update
  the existing entry to describe the final effect rather than the sequence of
  edits. File each entry under the section for its main effect; a change that
  can break existing code or installations belongs under breaking changes.
- **Description.** State the scope, what is deferred, how the change was
  verified, and what reviewers should check first.
- **Stacked pull requests.** When a change depends on another open pull
  request, open it against that pull request's branch and name the parent in
  the description. Merge (do not rebase) the parent's changes into it before
  review and before merge, and retarget it to `main` once the parent merges.
- **Deprecation.** Do not deprecate an interface until its replacement and
  migration guidance are released. Until then, disclose known limitations or
  risks in the documentation, and with runtime warnings that are not
  deprecations where the risk warrants them, so that a stalled replacement
  never leaves users on a deprecated interface with nowhere to go.
- **Dependencies.** Add a new third-party dependency with, or immediately
  before, its first verified consumer. Correcting a declared constraint to
  match what CI tests is not a new dependency.

For a programme of changes, keep a living design document with active decisions,
superseded history, actual PR progress, an outcome-based roadmap, and a rolling
near-term queue. Milestones may need many small PRs; do not preallocate a fixed
count or future PR numbers. Each pull request adds and maintains only its own
progress entry; concurrent pull requests conflict trivially there, so keep both
entries. Re-assess the plan at the start and end of each pull request, and
reconcile shared planning, user docs, and PR descriptions as decisions change.
Distinguish planned, under-review, merged, and released behaviour. Tests,
traceability, and conformance evidence belong with the implementation, even
when a later milestone consolidates them.
The [DICOM de-identification design](https://docs.pymedphys.com/en/latest/contrib/info/deidentification-design.html)
records that programme's current plan and distinguishes planned capabilities
from available features.

Explain the problem, the change, and how you checked it. Ask a maintainer to add
the `full-test` label when broader OS/Python coverage and integration tests are
needed; the `database` label requests the database tests.

`CI Summary` and `Security Summary` are the required checks. The individual
jobs remain visible in the PR's checks list and **Checks** tab. A green summary
means the checks selected for that run passed, not that every possible test ran.

Contributors with Write access can merge once the branch is up to date, the
required checks pass, review conversations are resolved, and an eligible
reviewer has approved. Admins may explicitly bypass the review requirement;
review is encouraged for their PRs too. The CI requirements still apply.
Approvals are not automatically dismissed by later commits, so request another
review when making substantive changes after approval.

For help with Git and GitHub, see
[GitHub's pull request documentation](https://docs.github.com/en/pull-requests).
Use [Discussions](https://github.com/pymedphys/pymedphys/discussions) for questions
and [Issues](https://github.com/pymedphys/pymedphys/issues) for reproducible bugs.
Follow the [security policy](https://github.com/pymedphys/pymedphys/blob/main/SECURITY.md)
when reporting a suspected vulnerability.

## Language

Use Australian/British English in prose, documentation, comments, and user-facing
text. Preserve code identifiers, command/API names, official product names, and
exact quotations where their spelling must remain unchanged.
