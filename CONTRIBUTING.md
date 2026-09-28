# Contributing to PyMedPhys

Use a branch based on `main`, or on the branch of an open pull request that your
change depends on, and open a pull request for your changes.
The older `master` and release-maintenance branches are retained as read-only
history.

## Keep patient data out of public posts

Issues, pull requests, discussions, and their comments are public, and anyone can download the files attached to them. Never post anything that identifies a patient: clinical DICOM files, treatment or delivery records, logs, screenshots, or file names that show a patient's name, ID, or date of birth. Use anonymised or synthetic data instead.

If identifying information is posted, tell the maintainers privately, by the email address in the [security policy](https://github.com/pymedphys/pymedphys/blob/main/SECURITY.md), rather than in a comment.

Maintainers then remove it:

1. Edit the post to replace the information with `[REDACTED]`, or delete the comment. Hiding a comment is not enough, because anyone can expand it again.
2. Open the post's edit history (**edited**), and delete each revision that contains the information (**Options**, then **Delete revision from history**).
3. If the information is in a title, or cannot be removed by editing, an admin deletes the issue or archives the pull request, because GitHub keeps every earlier title. An organisation owner must first allow admins to delete issues. Archiving hides a pull request from everyone except admins; to remove it permanently, ask GitHub Support.
4. If the information was committed to a branch or pull request, follow GitHub's guide to [removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
5. Ask GitHub Support to remove any files that were attached to the post.
6. Tell the person who posted it, so that they can follow their organisation's privacy procedures.

Then check while signed out of GitHub: the information must no longer appear in the post, its edit history, its earlier titles, its attachments, or the repository's history. Copies in forks and clones, and emails that GitHub has already sent to people watching the repository, cannot be recalled.

## Set up a development environment

Start with the [workstation setup guides](https://docs.pymedphys.com/en/latest/contrib/setups/index.html)
for Windows, Linux, or macOS. With Git and
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed, run:

```bash
git clone https://github.com/pymedphys/pymedphys.git
cd pymedphys
uv python install 3.14
uv sync --python 3.14 --locked
uv run pre-commit install
```

If you do not have permission to push to this repository, fork it first and
clone your fork instead. Create a working branch before committing.

The development environment uses the dependencies recorded in `uv.lock`.
The current source supports Python 3.11–3.14; Python 3.14 matches the quick CI
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

These rules apply to every pull request.

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
  can break existing code or installations belongs under breaking changes. Describe changes relative to the last stable release, since development releases are not recorded: fold a change to something added since that release into that thing's entry, remove the entry when the thing itself is removed, and compare with the stable release, never a development one. End each entry with links to the pull requests that make the change.
- **Description.** State the scope, what is deferred, how the change was
  verified, and what reviewers should check first. Describe the state being
  merged, not the revisions made during review.
- **Readers.** Many PyMedPhys users, contributors, and reviewers are
  physicists and other scientists rather than full-time software developers.
  Write pull request descriptions, issues, and reviews so that they can follow
  them:
  - start with a plain summary of what changes for users and why;
  - explain the problem with a concrete example of what went wrong, and each
    change by its effect, not only by the code it touches;
  - explain or avoid jargon, and show before-and-after examples, such as an
    error message, where they help;
  - keep the detail a reviewer needs to check the implementation, in a
    clearly labelled later section such as "Reviewer focus".
- **Reviews.** Explain each finding by what would go wrong and for whom, then
  give the evidence and a suggested fix, and say plainly which findings must be
  fixed before approval. Rely on CI's results for the commit under review
  instead of re-running the tests, linters, and builds that CI runs. Spend
  review effort on what CI does not check, such as independent reference
  values, counterexamples, and configurations that CI does not exercise.
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
- **Programmes of work.** Record the scope, decisions, and roadmap of work
  that spans many pull requests in a design document, and list its pull
  requests in a tracking issue, where each pull request maintains its own
  entry. A pull request that changes a decision updates the design document,
  the user documentation, and affected code together. Plan milestones by
  outcome rather than by a fixed number of pull requests, and distinguish
  planned, merged, and released behaviour. Tests, traceability, and evidence
  ship with each implementation, even when a later milestone consolidates
  them.

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
