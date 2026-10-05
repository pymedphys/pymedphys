# Make your first contribution

This tutorial is for a contributor with a [working development checkout](setup.md)
and a GitHub fork. It follows the current `main` branch and uses a small
documentation correction as a complete example. At the end you will have a
reviewable pull request whose source, preview, and checks agree.

Choose one unclear sentence, incorrect link, or missing step in an existing
guide. Describe what a reader currently gets wrong and what your change should
help them do. Discuss larger changes with maintainers before starting; the
[contribution policy](https://github.com/pymedphys/pymedphys/blob/main/CONTRIBUTING.md#open-and-review-a-pull-request)
explains scope and review expectations.

## 1. Create a focused branch

Run from the repository root with a clean working tree:

```shell
git status --short
git fetch upstream
git switch -c docs/clarify-quick-start upstream/main
```

If `git status` lists existing work, finish or preserve it before choosing a
base for this tutorial. Do not discard it to obtain a clean checkout. Use a
different branch name if the example name already exists. Contributors who
cloned the main repository directly use `origin/main` as the base.

You should now be on your new branch, based on the project's current source.

## 2. Edit the source a reader needs

For this example, edit `lib/pymedphys/docs/users/get-started/quick-start.rst`.
Make the sentence or link change you identified, keeping the page's existing
reStructuredText formatting. Read [Author documentation](../guides/authoring.md)
if you need a new page, notebook, or API reference.

Check where the text originates before editing. The homepage's imported
introduction, contributor policy, and release notes are generated from root
files; [the documentation build guide](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html#source-files-and-publishing)
identifies their sources. Edit those root files when changing their text.

Add or update the relevant entry in root `CHANGELOG.md` as required by the
contribution policy. Describe the final reader-visible effect and later add
the PR link once the pull request exists.

## 3. Check and preview the result

```shell
uv run pre-commit run --files lib/pymedphys/docs/users/get-started/quick-start.rst CHANGELOG.md
uv run pymedphys dev docs
uv run python -m http.server 8000 --bind 127.0.0.1 --directory lib/pymedphys/docs/_build/html
```

Open `http://localhost:8000/users/get-started/quick-start.html`. Read the changed
passage as a new user, follow its links, and inspect code blocks and navigation.
Stop the server with Ctrl+C. A successful build exits without warnings or
unexpected notebook errors; it does not replace this visual check.

Hooks may rewrite files. Review their changes and run the hook command again
until it passes. This prose-only example needs documentation checks. Add runtime
tests when the contribution changes runtime behaviour, using
[the testing guide](../validation/testing.md).

For a changed external link, verify its destination and run
`uv run pymedphys dev docs --linkcheck`. Inspect the report as described in
[the build guide](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html#previewing-and-checking-the-site).

## 4. Review, commit, and push

```shell
git diff --check
git diff
git add lib/pymedphys/docs/users/get-started/quick-start.rst CHANGELOG.md
git commit -m "Clarify the quick-start instructions"
git push -u origin docs/clarify-quick-start
```

Stage only the files belonging to the change. Confirm the diff contains your
intended source edits and no generated documentation, notebook cache, private
data, or unrelated files. If the commit hooks change a file and stop the commit,
inspect the rewrite, re-stage that file, and retry the commit.

The push should create your branch on your fork. The command's output normally
offers a link to open a pull request.

## 5. Open a pull request

On GitHub, choose base repository `pymedphys/pymedphys`, base branch `main`, and
your fork's working branch as the head. A stacked change uses its parent PR's
branch instead; follow the contribution policy for that workflow.

Use a title describing the final change. In the body explain:

- what a reader could not follow before, with a concrete example;
- what the changed instructions now help them do;
- which checks you ran and which page you inspected;
- anything relevant that remains outside the change's scope.

Use the repository's PR template. Add the PR link to the changelog entry and
push that update to the same branch. The pull request should show only your
intended changes in **Files changed**.

## 6. Respond to checks and review

Read individual jobs in **Checks**, including any failure annotations. A green
summary describes the checks selected for that run; it does not mean every
optional suite ran. For this example, inspect the documentation artefact using
[the preview instructions](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html#checking-a-pull-request-s-documentation).
Fork authors apply and push hook fixes themselves.

Respond to a review comment with the corrected behaviour and, where useful,
the check that demonstrates it. Push new commits to the same branch and update
the PR description to describe the final result. Ask for another review after
substantive changes. Keep patient data and credentials out of all discussion
and attachments.

The tutorial is complete when the PR contains the intended change, its selected
checks pass, and a reviewer can inspect the rendered result and evidence.
Maintainers handle approval and merge according to
[the review and merge guidance](../maintainers/review.md).
