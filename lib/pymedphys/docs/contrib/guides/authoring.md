# Author documentation

This guide is for contributors with a [development checkout](../start/setup.md)
who want to add or change a page, notebook, or API reference on the current
site. The result should work in the source view and built site, appear in the
right navigation, and support the behaviour it describes.

The [documentation build guide](../info/docs-guide.rst) owns the commands for
building, notebook cache control, local previews, external-link reports, and
CI artefacts. Use those procedures to verify the recipes here.

## Authoring checklist

1. Identify the reader, task, prerequisites, and observable result.
2. Choose the source of truth and the section where readers will look.
3. Write or change the source, with reproducible examples where useful.
4. Register a new page in its parent index.
5. Build, inspect the rendered result, check changed links, and review the diff.

## Choose the right page and source

| Reader's need | Where to write |
| --- | --- |
| Install or choose a user interface | `users/get-started/` |
| Complete a user task | The relevant user how-to or tutorial section |
| Understand a scientific definition or limitation | `users/background/`, linked from the task and API reference |
| Look up a function or command | Its docstring/parser, extracted in `users/ref/` |
| Contribute a change | The relevant section linked by [the contributor guide](../guide.md) |
| Understand a programme's decisions | Its [design document](../design/index.md) |
| Inspect a study's methods and results | A [validation record](../evidence/index.md) with named revisions and evidence |

Edit the canonical input rather than a copied page. Root `README.rst`,
`CONTRIBUTING.md`, and `CHANGELOG.md` supply generated documentation copies.
The de-identification requirements page is generated from its register, and
`conf.py` is generated from `_config.yml`.
[Source files and publishing](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html#source-files-and-publishing)
explains the build copies. A normal new page belongs under `lib/pymedphys/docs`.

Current procedures describe the state being merged. A design document states
the current decisions and planned versus implemented scope; fold revisions into
that description. Historical studies retain their revision, methods, inputs,
and results. Keep historical deployment commands intact and mark their scope.

## Add a prose page

Use the format already used by nearby pages. Markdown, reStructuredText, and
notebooks are supported; changing format is unnecessary for a small correction.
For a new Markdown task guide, this is a starting shape:

````markdown
# Complete a specific task

This guide is for ... With ... installed, you will produce ...

## Procedure

1. Prepare the input ...
2. Run ...
3. Confirm ...

## Resolve a failure

Explain a likely error and the next useful check.
````

Use an action title, explain units and prerequisites where they matter, and
show the success condition beside the instruction. Open a long procedure with
a short checklist and put one-time setup in a linked setup page or appendix.
Write for scientists who may not know software jargon. Use Australian/British
English and preserve command and API spellings.

Add the page, without its extension, to the appropriate index's `toctree`.
For example, an index containing `my-task.md` can include:

````markdown
```{toctree}
:maxdepth: 1

my-task
```
````

Use a relative source link with its extension when mentioning another checked-in
page, such as `[Set up your checkout](../start/setup.md)`. Keep reStructuredText
`:doc:` references in reStructuredText. The
[portable-link rules](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html#writing-portable-links) explain
links in downloadable notebooks, generated pages, and specialised API references.

After building, reach the page through its parent navigation and follow its
links. Confirm that code blocks preserve their spacing and commands are usable
in the shell named by the page. Use separate shell blocks when syntax differs.

## Add or revise an executed notebook

Use a notebook when code, results, and explanation together teach the task.
Keep it short enough for the documentation build, and use synthetic or approved
data. Register the notebook in the relevant index as for a prose page.

1. Begin with a Markdown cell stating the question, supported inputs, units,
   dependencies, and what the reader should observe.
2. Make code runnable from a fresh kernel in cell order. Do not depend on a
   previous interactive session, files outside the documented input, or output
   saved in the notebook.
3. Put notebook dependencies in the `docs` dependency group in `pyproject.toml`
   and regenerate `uv.lock`. CI and Read the Docs install that locked group;
   packages present only in the broad development environment can conceal a
   missing documentation dependency.
4. Never install packages during the build. A reader-only installation cell,
   for example for Colab, must have the `skip-execution` cell tag. In Jupyter,
   add it through the cell's metadata/tags editor.
5. Explain each plotted axis, quantity, unit, and normalisation. Distinguish
   an illustrative calculation from evidence for a scientific claim.
6. Restart and run the notebook, then use the
   [fresh-cache build](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html#building-the-documentation-on-your-workstation)
   when dependency or execution changes need verification.

For example, a small synthetic calculation can demonstrate an API without a
clinical file:

```python
import numpy as np
import pymedphys

axis_mm = np.linspace(0, 10, 11)
dose = np.ones(11)
gamma = pymedphys.gamma((axis_mm,), dose, (axis_mm,), dose, 3, 1)
assert np.allclose(gamma, 0)
```

Explain that identical constant inputs produce zero gamma for the evaluated
points. This example exercises that property; it does not validate accuracy on
arbitrary dose grids. Scientific claims need
[independent evidence](../validation/scientific.md).

Downloadable notebooks should use published documentation URLs so their links
survive outside the checkout. Link to `stable` when the notebook describes
released behaviour, and to `latest` for development material. Check images,
outputs, paths, and metadata for identifiers or credentials before committing.

## Document a public API

The public object's NumPy-style docstring is the source for its API reference.
State its behaviour once there; task guides explain when and how to use it.
A useful docstring covers:

- parameters and returns, with units, array dimensions, and coordinate order;
- meaningful defaults and valid/unsupported inputs;
- errors and limitations a caller must handle;
- a reproducible example, and standard edition/clause references where needed.

Use sections such as `Parameters`, `Returns`, `Raises`, `Notes`, and `Examples`
as appropriate. Follow the existing feature's docstrings and the
[NumPy docstring guide](https://numpydoc.readthedocs.io/en/latest/format.html).
Explain standards claims precisely; avoid equating a passing example with
clinical suitability.

Add an `autofunction` or `autoclass` entry for the public name in its reference
page. The existing [gamma reference](../../users/ref/lib/gamma.rst) uses:

```rst
.. autofunction:: pymedphys.gamma

.. autofunction:: pymedphys.gamma_pass_rate
```

Use `automodule` only when the selected members and module scope are what the
reader needs. New reference pages must also be added to
`users/ref/lib/index.rst`. Build and inspect the signature, parameter sections,
examples, and links; importability alone does not establish reference coverage.

## Document a command

Argument help and defaults come from the parser. A CLI reference page extracts
them with `sphinx-argparse`, for example:

```rst
.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: dicom
```

The `:path:` selects the command group. Add a user how-to for input preparation,
an actual invocation, output, and failure handling; generated help alone does
not teach a workflow. For developer commands, use
[the developer reference](dev-reference.rst).

## Verify and submit

Build using the canonical build guide and inspect every changed page. Check
source-view links as well as built links. Treat external-link failures as
evidence to investigate: a rate limit or authentication requirement may differ
from a deleted target. GitHub URLs excluded from automated link checking still
need manual verification when changed.

Review the final diff for generated copies, cached output, hidden metadata,
and unrelated edits. Include the relevant changelog entry and state the checked
pages and notebook execution conditions in the PR. See
[the first-contribution tutorial](../start/first-contribution.md) for submission.
