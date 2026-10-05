# Testing and scientific validation

These guides are for contributors checking changes in the current source.
Start with a [working checkout](../start/setup.md), the intended behaviour,
and any relevant design decisions. The outcome is evidence a reviewer can
inspect and reproduce, with its scope and limitations stated.

- [Run and write tests](testing.md): select a suite, build useful regression
  tests, test the GUI, and keep tests compatible with installed packages.
- [Scientific evidence](scientific.md): derive expected results independently,
  justify tolerances, and distinguish implementation checks from suitability
  for an intended use.
- [Fixtures and external data](data.md): choose, register, cache, and replace
  reproducible inputs without exposing patient data.
- [Validation records](../evidence/index.md): inspect the existing studies and
  their named revisions. They complement ongoing tests rather than supplying
  current test results automatically.

A passing suite establishes the properties it exercises. A documentation build
establishes that the selected sources and notebook executions build successfully.
Neither result alone establishes scientific correctness or clinical suitability.
Choose the smallest set of checks that addresses the changed claims and their
plausible failure modes, then report what actually ran.

```{toctree}
:maxdepth: 1

testing
scientific
data
```
