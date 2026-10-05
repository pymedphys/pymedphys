# Development how-tos

These guides are for contributors who have completed
[checkout setup](../start/setup.md). They describe how to change the current
source, with an observable result and appropriate evidence for each task.

- [Make a change](make-a-change.md) covers library functions, commands, GUI apps,
  dependencies, and data.
- [Author documentation](authoring.md) covers prose, executed notebooks,
  API reference, and generated sources.
- [Developer command reference](dev-reference.rst) lists the commands from
  the current parser and explains the pytest options passed through to tests.
- [Use the development environment in Jupyter](../tips/add-jupyter-kernel.rst)
  connects a notebook editor to this checkout.

For the project's patterns, read [Architecture](../architecture/index.md).
For scientific or standards changes, choose evidence with
[Scientific evidence](../validation/scientific.md) before implementation.

```{toctree}
:maxdepth: 1

make-a-change
authoring
dev-reference
../info/docs-guide
../tips/add-jupyter-kernel
```
