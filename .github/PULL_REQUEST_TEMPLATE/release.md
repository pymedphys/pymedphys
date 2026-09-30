<!-- markdownlint-disable-file MD041 -->
<!-- Template for a stable release pull request. Set VERSION and NEXT below, then follow https://docs.pymedphys.com/en/latest/contrib/info/release-guide.html. Write for readers who are physicists rather than full-time software developers: CONTRIBUTING.md, under "Open and review a pull request", has the rules. A development release needs no release pull request. -->

## Summary

<!-- In plain words: what users get in this release, and what they should check before upgrading. Link the version's section of CHANGELOG.md. -->

Releases `VERSION` (replace with the version).

## Versions

<!-- See "Choose the versions" in the release guide. Write versions without a leading "v". -->

| | Value |
| --- | --- |
| `VERSION` | |
| `NEXT` (the development version `main` carries afterwards) | |
| Previous stable release | |
| Release type | Minor / patch, and why |

- [ ] Neither `VERSION` nor `NEXT` is on [PyPI](https://pypi.org/project/pymedphys/#history); PyPI never accepts a filename again
- [ ] `version` in `pyproject.toml` is `VERSION`, in canonical form (`0.42.0`, not `0.42.0-dev0`)

## Preparation

<!-- Each step is in "Prepare the release pull request" in the release guide. -->

- [ ] Version set, and `uv lock`, `uv sync`, and `pymedphys dev propagate` run
- [ ] The diff outside `CHANGELOG.md` is only the version and the files those commands regenerate
- [ ] Dependency upgrades are not included, or are described under Reviewer focus
- [ ] The `full-test` label is on this pull request
- [ ] `CI Summary` and `Security Summary` pass, and their constituent checks have been inspected

## Changelog review

<!-- The criteria are in "Review the changelog" in the release guide. Record what you changed and anything you left for later. -->

- [ ] `## Unreleased` is renamed `## [VERSION]` and unused sections are removed
- [ ] Every entry describes the change relative to the previous stable release, ends with links to its pull requests, and states its effect and what users should do
- [ ] Results that earlier versions returned without an error are flagged at the top of the section and listed under (Potentially) breaking changes
- [ ] Related entries are consolidated, and the sections are ordered for the reader who is deciding whether to upgrade
- [ ] The pull request links check in the release guide prints nothing
- [ ] The GitHub release notes are a short summary of this section that links to it

## Reviewer focus

<!-- What to check first. For the changelog: entries that read unclearly, overstate or understate an effect, or sit under the wrong section. Do not repeat what CI checks. -->

## After merge

<!-- Steps in "Publish the release" and "Start the next development version" in the release guide. -->

- [ ] Tag the merge commit `vVERSION`, publish the GitHub release, and approve the `pypi` deployment
- [ ] **Release Summary** passes, and its record is pasted in a comment on this pull request
- [ ] A pull request sets `main` to `NEXT` and adds an empty `## Unreleased` heading
