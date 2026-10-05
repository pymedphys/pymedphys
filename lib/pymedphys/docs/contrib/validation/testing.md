# Run and write tests

This guide is for contributors with a [development checkout](../start/setup.md)
and an intended result to check. It describes the current pytest runner and
test patterns. The outcome is a selected suite that actually exercises the
change, and regression evidence a reviewer can understand.

For scientific calculations, use [independent expected values](scientific.md).
For downloaded or native-format inputs, choose [appropriate fixtures](data.md).

## Choose checks for your change

| Change | Useful checks before review |
| --- | --- |
| Prose or navigation only | Documentation build, rendered page inspection, and changed-link checks. |
| Notebook code or documentation dependencies | Fresh-kernel execution and an appropriate fresh-cache docs build. |
| Library behaviour | Focused feature tests and a regression case that distinguishes the intended behaviour. |
| Numerical result, coordinates, or a standard interpretation | Independent reference/analytic cases and boundary cases, plus relevant feature tests. |
| CLI arguments or output | Parser/default checks and a synthetic command workflow, including failure behaviour. |
| GUI interaction | AppTest scenarios and rendered inspection for visual changes, plus tests for underlying calculations. |
| Dependency, import, or package selection | Consumer tests and the appropriate narrow-extra, floor, import, or distribution checks. |
| External system integration | The approved mock/integration setup and a clear statement of which boundary was exercised. |

Run focused local checks while developing. During review, use CI evidence for
the exact reviewed revision rather than routinely repeating checks CI already
demonstrates. Spend additional effort on independent calculations or scenarios
CI does not exercise. [PR checks](../maintainers/pr-checks.md) explains selection,
labels, and reading the resulting jobs.

## Select and run tests

Run commands from the repository root:

```shell
uv run pymedphys dev tests
uv run pymedphys dev tests tests/dicom/test_orientation_invariance.py
uv run pymedphys dev tests lib/pymedphys/tests/dicom/test_orientation_invariance.py
uv run pymedphys dev tests tests/dicom -k "orientation" -v
```

The first command collects the package and uses the default marker selection.
The next two identify the same file: paths may be relative to `lib/pymedphys`
or to the directory from which you invoked the command. A `path::test_name`
selector can narrow a file further. Other pytest arguments, including plugin
options, are passed through to pytest.

The runner changes its working directory to `lib/pymedphys`. Relative output
paths such as `--junitxml=report.xml` are written there. Use an absolute report
path in CI or whenever another tool needs to find it. Positional test paths are
resolved after pytest parses its arguments, through `_dev/pytest_paths.py`, in
the controller and pytest-xdist workers.

## Request opt-in tests explicitly

The package's root `conftest.py` registers markers and skips opt-in tests until
requested. Pytest's `-m` expression alone does not enable them.

| Selection | Command arguments after `dev tests` |
| --- | --- |
| Default suite | No marker flag; slow, database, and Anthropic-key tests are skipped. |
| Default suite plus slow tests | `--include-slow` |
| Slow tests only | `--slow` |
| Default suite plus mock Mosaiq database tests | `--include-mosaiqdb` |
| Mosaiq database tests only | `--mosaiqdb` |
| Default suite plus Anthropic-key tests | `--include-anthropic` |
| Anthropic-key tests only | `--anthropic` |
| Tests marked as using pydicom | `--pydicom` |
| Every test, including opt-in markers | `--all` |

Multiple “only” flags select the union of their markers. A test carrying an
additional opt-in marker still needs that marker requested. A `-m` expression
or `-k` filter further narrows the selected tests. For example,
`-m slow` on its own finds slow tests but leaves them skipped; use `--slow`.

Slow tests may download approved datasets. Database tests need the mock SQL
Server and its dependencies; Anthropic tests need an authorised API key and
make external API calls. Prepare the required infrastructure before requesting
these suites. Do not treat `--all` as an environment-independent smoke check.

```shell
uv run pymedphys dev tests --slow -n auto
uv run pymedphys dev tests --include-slow
uv run pymedphys dev doctests
```

CI runs slow tests with one worker per CPU. Keep outputs and mutable state
independent across tests; use `tmp_path`, unique resources, and no ordering
assumptions. Shared data downloads/extraction are locked by the data cache,
but test-owned files still need isolation.

The pytest configuration enforces strict markers and strict xfail: a misspelt
marker or an unexpectedly passing xfail fails the run. The default per-test
timeout is 900 seconds and can be overridden with pytest's timeout options.
Register new project selection markers in root `conftest.py`'s `MARKER_CONFIG`.
When adding/removing a slow-test or doctest module, also update the corresponding
selection inventory described in [CI maintenance](../maintainers/ci.md).

## Write a useful regression test

1. Identify the public effect that can be wrong and the smallest input exposing
   it. For a bug fix, demonstrate the failure against the old behaviour where
   practical and the corrected result against the change.
2. Put the test beside the feature's tests under `lib/pymedphys/tests/`.
   Reuse fixtures that represent the scenario; read their assumptions first.
3. Establish the expected result independently. A stored snapshot generated by
   the same implementation can preserve its error.
4. Assert the behaviour the caller relies on: values and units, shape/order,
   appropriate exception, file output, or rendered message.
5. Include relevant malformed, boundary, and asymmetric cases. Add only cases
   that address a meaningful failure mode.
6. Record a random seed when randomisation helps, and make a failing case
   replayable. Keep fixture generation local and deterministic where possible.

Use `pytest.approx` or numerical assertions with an explained tolerance for
floating-point results. Use exact assertions for properties that should be
exact, such as a named exception or a metadata field. The
[scientific guide](scientific.md#choose-and-explain-tolerances) explains how to
justify an absolute or relative numerical tolerance.

Write test outputs to `tmp_path`, never next to shared cached data. The root
conftest redirects `HOME` and `USERPROFILE` to a temporary directory for the
session, so normal tests do not read or write the real `~/.pymedphys` or
`~/.streamlit`. The verified data cache remains shared via
`PYMEDPHYS_DATA_DIR`. CLI startup also bypasses user logging configuration for
`dev tests` and `dev doctests`, before pytest can isolate home; preserve that
boundary when changing startup or the runner.

Do not write tests that merely restate a dependency constraint or mirror an
implementation. A low-impact prose correction needs documentation evidence,
not an unrelated runtime test.

## Test DICOM encoding changes

Tests involving DICOM encoding should use the `pydicom_behaviour` fixture in
`tests/dicom/conftest.py` when applicable. It runs the case with current and
future pydicom behaviour, catching deprecated APIs that do not always warn.
The suite also treats pydicom warnings for APIs removed in v4 as errors.

Read/write code should use the supported encoding APIs and file-meta Transfer
Syntax UID. The fixture is scoped: in pydicom 3.0, `Dataset.pixel_array` itself
fails with future behaviour, so enabling `PYDICOM_FUTURE` for the whole suite
does not establish useful coverage. Explain what the selected cases exercise.

## Test a Streamlit app

GUI tests in `tests/streamlit/` use `streamlit.testing.v1.AppTest` against the
installed package's `_app.py`. They run without a browser or Node toolchain.
The shared helpers select an app through query parameters, find widgets by
label, and read rendered Markdown.

For example, the existing index test uses the following interaction pattern:

```python
from . import apptest_utilities as utl

def test_filter_narrows_the_index():
    app_test = utl.load_app()
    utl.widget(app_test.text_input, "Filter").input("dicom").run()
    utl.assert_no_exception(app_test)
    labels = [button.label for button in app_test.button]
    assert labels
    assert all("dicom" in label.lower() for label in labels)
```

Adapt a nearby app test for the workflow you change. Confirm both absence of
exceptions and the meaningful output or interaction; “the app loaded” does not
check a dose calculation or exported file.

Data-driven app tests use the approved `metersetmap-gui-e2e-data.zip` demo.
The `demo_working_directory` fixture runs from a temporary directory because
apps extract demo data in the current directory. `demo_config_on_disk` serves
the demo configuration and clears `st.cache_data` on entry and exit: app
configuration is memoised for the pytest process, so another test's cache
can otherwise change the result.

The root conftest defaults `MPLBACKEND` to `Agg`, and the GUI fixtures also
select that non-interactive backend. AppTest runs on a worker thread; GUI
matplotlib backends can abort the interpreter there. Preserve the headless
setup when adding tests. Keep screenshots, logs, fixtures, and app outputs free
of patient identifiers. Live clinical connections are not regression fixtures.

## Test the mock database

Read `docker/mosaiq/docker-compose.yml` and the nearby database test fixtures
before running a database case. The current `pymedphys dev mssql` helper invokes
`docker-compose`, so it needs Docker and that Compose command available:

```shell
uv run pymedphys dev mssql --daemon
uv run pymedphys dev tests tests/mosaiq --mosaiqdb
uv run pymedphys dev mssql --stop
```

Use the local mock server and configured fixture connection. Confirm the server
accepts connections before interpreting a test failure as library behaviour.
The [CI guide](../maintainers/ci.md) describes the database jobs and their
minimal-extra environment; a broad checkout run alone cannot prove that extra
contains all required dependencies.

## Keep tests runnable from an installed wheel

Published-release checks run the suite shipped in the installed package.
Tests therefore need to read fixtures inside the package and obtain package
metadata from `importlib.metadata`. They cannot assume a repository root,
`pyproject.toml`, `.github/`, or an editable installation exists.

For a packaging change, use the maintained distribution checker rather than
an ad hoc import from the checkout:

```shell
uv build
uv run python .github/scripts/check_distributions.py dist
```

Use a `dist` directory containing only the intended build's wheel and sdist.
[Distribution checks](../maintainers/release.md#verify-packaging-before-a-release) explains
the checker, isolated installs, licence/content checks, and published-package
tests. Report which archive and environment were tested; importing the source
checkout is not evidence for the installed wheel.

## Check style and report the evidence

For local checks that do not rewrite Python files:

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pymedphys dev lint
```

`uv run pre-commit run --all-files` runs the configured hooks and can rewrite
files. Inspect any rewrites before committing. Choose the checks relevant to
the change and complete any required ones.

In the PR, state the command, revision, environment/input, and result. Separate
checks run locally, CI inspected for the reviewed revision, and results merely
reported by someone else. Identify skipped tests and the property left
unverified. A short, specific limitation is more useful than describing an
unselected suite as passing.
