# Trace a feature from interface to evidence

This guide is for a contributor locating the code affected by a change in the
current checkout. You need a working checkout and the
[repository map](index.md). The outcome is a list of public entry points,
implementations, dependencies, tests, and documentation to update together.

## Trace a library function: gamma

1. A user calls `pymedphys.gamma(...)`.
2. [`lib/pymedphys/__init__.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/__init__.py)
   exports `gamma_shell` under the public name `gamma`.
3. [`_gamma/implementation/shell.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_gamma/implementation/shell.py)
   defines the signature and NumPy-style docstring, validates inputs through
   gamma utilities, and performs interpolation/search using shared helpers.
4. Optional scientific packages arrive through `_imports`; the published
   `gamma` extra declares the feature's dependencies.
5. `tests/gamma/` exercises the calculation and its boundary cases; DICOM and
   GUI workflows can also call it.
6. [The API reference](../../users/ref/lib/gamma.rst) extracts the public
   docstring. User examples teach interpretation, while
   [gamma studies](../evidence/index.md) retain their methods and results.

For a numerical change, search for both the public name and the private helper
you change. Test an independently derived expected value, then trace any effect
on plots, pass-rate summaries, and data conversion. The returned array belongs
to the reference coordinates; changing evaluation-grid storage internally
must preserve that public correspondence.

## Trace a command: DICOM

The script entry point in `pyproject.toml` calls `pymedphys.__main__:main`,
which delegates to `pymedphys.cli.pymedphys_cli`.
[`define_parser`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/cli/__init__.py)
registers command groups, including `dicom_cli` from `cli/dicom.py`.
That feature parser registers subcommands and connects each one to a callable
through `set_defaults(func=...)`.

For example, `dicom merge-contours` passes the input/output paths and selected
structures to a wrapper in `_dicom/structure/merge.py`. Trace from the parser
to that wrapper and the shared implementation before changing the behaviour.
The [CLI reference](../../users/ref/cli/dicom.rst) is generated from the parser;
the user how-to still needs a usable input/output example.

Check default arguments, invalid inputs, output handling, and error messages
at the command boundary. Test shared scientific transformations separately.
For DICOM output, preserve the privacy and conformance decisions in the
[de-identification design](../design/deidentification/index.md) when applicable.

## Trace a delivery reader

The exported `Delivery` class is assembled in
[`_delivery.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_delivery.py).
Its reader mixins convert source formats into the shared delivery fields
defined by `DeliveryBase`. A format-specific change can consequently affect
metersetmap processing or a GUI comparison even if those callers never read
the source file directly.

Follow a reader from its public method, through the parser, to the construction
of monitor units, gantry/collimator angles, MLC positions, and jaws. Determine
the units, control-point ordering, and any filtering or normalisation at each
step. An array with the expected shape can still assign a value to the wrong
control point. Use asymmetric fixtures and explicit expected pairings.

## Trace an app

`pymedphys gui` launches `_app.py`, whose Streamlit index discovers the stable
and experimental app registries. The module name supplies the URL key, and its
`TITLE` and `CATEGORY` supply the index presentation. The app's `main()` handles
widgets and calls library functions.

[`tests/streamlit/apptest_utilities.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/tests/streamlit/apptest_utilities.py)
loads that same app script with `AppTest`. Tests can select an app with query
parameters, find widgets by label, and read rendered Markdown. These tests
exercise the app's interaction boundary; the underlying calculation still
needs its own numerical evidence.

Trace configuration reads, cache lifetimes, downloaded demo inputs, and output
paths as well as the widgets. A fixture must isolate those resources so the
result does not depend on another test's cached configuration. See
[Test a Streamlit app](../validation/testing.md#test-a-streamlit-app).

## Use a source search to confirm the impact

Run searches from the repository root; substitute the name you are changing:

```shell
rg -n "gamma_shell|pymedphys\.gamma" lib/pymedphys examples
rg -n "merge_contours_cli" lib/pymedphys
```

If ripgrep is unavailable, use your editor's search. Read the surrounding code,
not just the matched line. Verify direct and indirect callers, re-exports,
doctests, fixture generators, and notebooks. A design document can describe
planned behaviour; confirm the current implementation rather than assuming
the plan has already shipped.

Before editing, write down the public effects and the evidence needed for
them. [Make a change](../guides/make-a-change.md) gives the implementation
recipes, and [scientific evidence](../validation/scientific.md) helps select
checks that can detect an incorrect result.
