# Make a change

Use this guide after [setting up a checkout](../start/setup.md) and creating a
working branch. It covers the current library, CLI, GUI, dependencies, and data.
The outcome is a change whose public behaviour, tests, documentation, and
generated files agree. Follow the
[contribution policy](https://github.com/pymedphys/pymedphys/blob/main/CONTRIBUTING.md#open-and-review-a-pull-request)
for scope, compatibility, and changelog requirements.

## Before editing

1. Write one concrete expected result: an input and output, a command's result,
   or the action a reader should be able to complete.
2. Find the public entry point and trace its implementation using
   [the feature anatomy guide](../architecture/feature-anatomy.md).
3. Read the nearby tests, relevant design decisions, and existing discussion.
4. Choose [appropriate evidence](../validation/index.md) before changing a
   scientific result, supported format, or standards interpretation.
5. Keep generated output separate from hand-written logic in the review.

## Change a public function

Implementation usually lives in an underscored directory, with the public name
exported by a package-root module. For example, `pymedphys.gamma` is exported
from `lib/pymedphys/__init__.py` and implemented in `_gamma/implementation/shell.py`.
Read both ends and callers before changing the signature or result.

1. Put the implementation in the existing feature directory. A helper can
   remain private; exporting every helper increases the public surface.
2. Export an intended public name from the feature's public module or package
   root, following its existing pattern.
3. Add a NumPy-style docstring describing inputs, units, dimensions, results,
   supported conditions, and failure modes. Include a standard's edition and
   clause when the behaviour implements it.
4. Add behavioural tests near the feature's tests. Use independent expected
   values for numerical results, including asymmetric inputs where order matters.
5. Add the public name to its API reference page and explain any changed usage
   in a user guide. See [API documentation](authoring.md#document-a-public-api).

Use optional dependencies through `pymedphys._imports` and defer their use until
runtime. [Lazy imports](../info/lazy-imports.md) explains the registration and
import-time rules, including defaults, decorators, and annotations.

The change is ready for review when a caller can use the documented public
name, its ordinary and error cases are checked, and the result's units and array
ordering are unambiguous. A changed result or shape may require migration advice
and a breaking-change entry; follow the contribution policy.

## Add or change a command

The top-level parser is `pymedphys.cli.define_parser`. Feature parsers live in
`lib/pymedphys/cli/`; their `set_defaults(func=...)` connects parsed arguments
to an implementation. Existing wrappers in `_dicom/` show how a command can
reuse feature code without putting scientific calculations in the parser.

1. Add the argument definitions to the feature's parser, or register a new
   feature parser in `define_parser` when a new command group is needed.
2. Keep conversion, calculation, and validation in reusable implementation
   functions. The command wrapper handles arguments, files, and reporting.
3. Test parsed defaults and user-visible behaviour: output, exit status,
   invalid input, and any output-file handling that the change affects.
4. Review logs and errors for inappropriate disclosure of input identifiers.
5. Update the command's user how-to. The generated CLI reference reads the
   parser; check the rendered arguments and help as well.

For a DICOM command, inspect
[the existing parser](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/cli/dicom.py)
and [its generated reference](../../users/ref/cli/dicom.rst).
Run the relevant command's `--help` in the checkout and one synthetic end-to-end
case. Success means the documented invocation reaches the intended behaviour
and reports an understandable error for invalid input.

## Add or change a Streamlit app

The GUI loads modules exported by `_streamlit/apps/__init__.py` and
`_experimental/streamlit/apps/__init__.py`. Each app supplies a `TITLE`,
`CATEGORY`, and `main()`; the index derives its URL key by replacing underscores
in its module name with hyphens. Existing apps may set `SIMPLE` to alter layout.

1. Put the app in the appropriate stable or experimental app directory and
   export its module from that directory's `__init__.py`.
2. Use a category from `_streamlit/categories.py` and a clear title. Explain
   prerequisites and limitations in the app's `main()` docstring or user guide.
3. Keep transformations in library functions so they can be tested without
   a GUI. Restrict the app to configuration, input, interaction, and presentation.
4. Add AppTest scenarios for its initial screen, a useful workflow, and a
   failure the user needs to understand. Reuse
   [the GUI test fixtures](../validation/testing.md#test-a-streamlit-app).
5. Launch `uv run pymedphys gui` against synthetic or approved demo data and
   inspect the screen when visual behaviour changes.

The GUI has no login. It listens on loopback by default; network serving through
`--address` lets anyone who can reach it use its apps. Preserve that supported
option and explain the exposure in deployment instructions. Experimental AI
apps use Anthropic's API and the opt-in `ai` extra; make API access explicit and
keep other apps loadable without that extra.

Success means the app appears in the index, its URL selects it, its tested
workflow renders the expected result, and its dependencies and infrastructure
requirements are documented. A skipped infrastructure-dependent screen test
does not establish that the workflow itself was exercised.

## Add or update a dependency

Use [the environment map](../architecture/index.md#dependencies-and-environments)
to choose between a published extra and a checkout-only group. Add a new package
with, or immediately before, its first verified consumer.

1. Update the appropriate constraint in `pyproject.toml`.
2. For a feature package, follow
   [Add a new optional dependency](../info/lazy-imports.md#add-a-new-optional-dependency)
   to update `user`, any relevant narrow extra, the import registry, and the
   import-to-distribution name map.
3. Regenerate the lock and propagated files from the repository root:

   ```shell
   uv lock
   uv sync --python 3.14 --locked
   uv run pymedphys dev propagate
   ```

4. Inspect `uv.lock` and the generated `requirements.txt`, `pyproject.hash`,
   `lib/pymedphys/dependency-extra.txt`, and `_version.py`. Commit the outputs
   that changed; never hand-edit the lock or propagated files.
5. Exercise the verified consumer and affected feature tests. When raising a
   tested minimum, update its CI floor together with the declared minimum.
   [Dependency maintenance](../maintainers/dependencies.md) describes these jobs
   and the automated update process.

Use `uv lock --upgrade` for an intentional broad upgrade, or a targeted uv
upgrade for a particular package. Do not mix an incidental environment refresh
with an unrelated fix. A narrow feature extra must include all packages its
public functions and commands need, rather than relying on another package to
install them transitively. Add a new narrow extra with its CI matrix entry.
Contributor-only tools belong in a group.

Success means the locked environment imports and exercises the consumer, the
generated files reproduce without further changes, and the relevant minimal
extra or dependency-floor checks cover the declared support. Do not add tests
that merely repeat a dependency constraint; test the affected behaviour.

## Add a dataset or fixture

Begin with [Fixtures and external data](../validation/data.md). Prefer a small,
deterministic fixture generated locally when it represents the property being
tested. For a native-format compatibility claim, identify which exporter or
format characteristics require approved authentic data.

Include provenance, licence, transformations, recorded hash, and the checked
expected result. Update the data registry and test together. A successful
download is only a transport check; the fixture still needs to establish the
behaviour named by the test.

## Prepare the final change for review

Choose checks from [the testing guide](../validation/testing.md#choose-checks-for-your-change).
Inspect generated documentation for changed interfaces, including examples
and links. Use `git diff --check` and review the final diff before committing.

The PR description should explain the final behaviour and its evidence, with
any deferred work stated plainly. Keep implementation history and one-off
investigations on the PR; keep guides focused on the current procedure.
For multi-PR programmes, update the [design document](../design/index.md) and
tracking issue when the change revises a decision.
