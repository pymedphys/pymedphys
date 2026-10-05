# Understand PR checks

For contributors interpreting a pull request's checks and maintainers choosing additional coverage.

**Prerequisites:** an open PR and access to its Checks tab. **Inputs:** changed files, labels, event and tested SHA. **Outputs:** a record of selected checks and any failure needing action. **Success:** `CI Summary` and `Security Summary` pass for the reviewed revision, and the author understands which suites actually ran.

## Find what ran

Open the run's Summary and the `changes` job summary. Its reasons identify a path, event or label that selected each check. In the PR's Checks tab, expand the reusable workflows to see constituent jobs; the two required summaries do not hide the individual results. Compare the tested SHA with the current PR head, including any formatting commit pushed by automation.

`CI Summary` requires pre-commit, selector tests and every selected CI job. `Security Summary` requires the selected dependency audit, Bandit and zizmor jobs. A green summary establishes the coverage selected for that event, rather than every possible suite. External documentation link checking is advisory; inspect `docs-linkcheck` when a link matters.

## Selection and labels

| PR changes | Selected checks, in addition to policy checks and pre-commit |
|------------|-------------------------------------------------------------|
| Known documentation prose, notebooks and rendered assets only | Documentation |
| Package Python modules | Lint, type checks, unit tests, generated documentation and all security scans |
| Python tests only | Lint, type checks, unit tests and all security scans |
| Other CI configuration or any unclassified path | Every standard check: lint, type checks, unit tests, script tests, documentation and all security scans |
| Dependency or build metadata (`pyproject.toml`, `uv.lock`, the exported requirements, `pyproject.hash`, `dependency-extra.txt`, `_version.py`), `ci.yml` or `.github/actions/` | Standard checks, plus integration and database tests |
| `.github/scripts/`, `integration-tests.yml`, `examples/`, or packaging filters (`.gitignore`, `.gitattributes`, `.hgignore`, including nested files) | Standard checks, plus integration tests |
| Slow-test modules, modules with doctests, or non-Python test fixtures | Adds integration tests |
| Any path naming Mosaiq or a database (except documentation) | Adds database tests |
| `conftest.py`, top-level package modules, or `_imports/`, `_data/`, `_utilities/` and `_base/` | Adds integration and database tests |
| A symlink, a submodule or an unverifiable merge diff | Every check a changed path can select, including integration and database tests |
| `full-test` label | Every check and the full unit-test matrix |
| `database` label | Adds database tests |

Recognised prose and rendered assets under `lib/pymedphys/docs/`, and the
named root documentation files in `ROOT_DOCS`, are exempt from Python checks;
a Python file or new configuration format inside the docs tree is not exempt.
The repository-root `docs` is a symlink to that directory,
so git reports only the link itself, which selects every check that a changed
path can select. A symlink or submodule is never exempt, whatever its name,
because it can stand in for any content. Package modules still select
documentation because autodoc and notebooks import them. The full OS/Python
matrix and integration checks run on merge groups and main pushes. Read the Docs
publishes main documentation independently; see
[Publish documentation](publishing.md#read-the-docs).

Integration tests, database tests and the full unit-test matrix are too costly
for every PR. Apart from merge groups, main pushes and the labels, integration
and database tests run only when a PR changes an input that no standard check
validates, as the table lists: an input of the generated-file drift check, the wheel build, the
Windows and macOS tooling tests, the example scripts, the slow tests, the
doctests and their shared inputs, or the database code and its locked drivers.
An unclassified path selects every standard check, but not these. Unit tests
use the quick matrix unless the PR has the `full-test` label.

Unit runs skip the slow tests and never run doctests. `SLOW_TEST_FILES` and
`DOCTEST_FILES` in `select_checks.py` list the package modules that apply the
slow marker or hold doctests. The policy tests in the always-required `changes`
job scan the package and fail unless each list equals what they find, naming
each module to add or remove, so update the list in the PR that adds, removes
or renames such a module. Shared test data, including `_data/urls.json` and
`_data/hashes.json`, also selects integration tests because ordinary unit runs
exclude the slow tests that consume some datasets.

Changes outside the integration and database inputs listed above, such as
TRF decoding, Pinnacle export or gamma implementation code, leave those tests
unselected on a pull request. Add `full-test` to request both suites and the
full unit-test matrix; `database` requests only the database suite. Modules
with doctests, including `_metersetmap/metersetmap.py`, already select
integration tests through the existing path rules. Every push to `main` runs
both suites, and the release workflow runs the slow tests before publishing.
Add `full-test` to a pull request that substantially changes code exercised by
slow tests. Merge groups run both suites before merging. When CI fails on a
push to `main`, the `report-main-failure` job
opens or comments on the issue titled "CI failed on main", linking to the run.
Close the issue once `main` is green again.

Selected jobs need only `changes`, so they start alongside pre-commit and run
whatever its result, and one run reports every result. The summary waits for
pre-commit and fails when it fails. An auto-fix pushed with the bot's token
starts a new run, which cancels the run for the superseded commit; either way,
the summary fails until a fresh run passes on the new commit. The summaries
reject any other unexpected skip. Integration jobs run alongside unit tests.


The `rtd-preview` label asks Read the Docs to build later commits on that PR. It does not select GitHub CI; see [hosted previews](publishing.md#requesting-a-hosted-preview).

## Diagnose a failure

1. Open the failing constituent job and its first failing step, before later cancellation messages.
2. For formatting, run the [local checks](../guides/make-a-change.md) and push the resulting changes. On forks, automation cannot push them for you.
3. For a failing test, reproduce the named node with the [testing guide](../validation/testing.md). Read JUnit artefacts, skips and xfails as well as the exit code.
4. For documentation, download `docs-html` and inspect the warning or notebook error; follow [Publish documentation](publishing.md). An artefact may be uploaded even after failure, so its presence alone is not success.
5. For dependency, installation or download errors, inspect versions, network failures and the dataset hash. Retry a transient failure once; investigate repeated failures.
6. For a summary reporting an unexpected skip, involve a maintainer: the job's selector and gate must agree. See [Maintain CI](ci.md#maintaining-the-gates).

Useful artefacts include `junit-*`, `docs-html`, `docs-linkcheck`, distribution installation reports and de-identification traceability reports. Artefact availability follows each workflow's upload steps and retention settings.

Selection is authoritative in `.github/scripts/select_checks.py`; update this page whenever labels, selected paths, job names or summaries change.
