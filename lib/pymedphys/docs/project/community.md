# Community, citation and licensing

For users seeking help, authors citing PyMedPhys and contributors checking reuse requirements.

## Join the community

Use [GitHub Discussions](https://github.com/pymedphys/pymedphys/discussions) for questions and collaboration. Report reproducible bugs through [Issues](https://github.com/pymedphys/pymedphys/issues), including version, environment, steps and synthetic inputs. Start contributing with the [first-contribution walkthrough](../contrib/start/first-contribution.md). Public-data rules are in [CONTRIBUTING](../contrib/index.md); suspected vulnerabilities follow [SECURITY](https://github.com/pymedphys/pymedphys/blob/main/SECURITY.md).

The canonical README records current maintainers and contributors. See [Maintain the project](../contrib/maintainers/project.md) for responsibilities and issue routing.

## Cite PyMedPhys

Please cite the [Journal of Open Source Software paper](https://joss.theoj.org/papers/10.21105/joss.04555):

Biggs, S., Jennings, M., Swerdloff, S., Chlap, P., Lane, D., Rembish, J., McAloney, J., King, P., Ayala, R., Guan, F., Lambri, N., Crewson, C., Sobolewski, M. (2022). PyMedPhys: A community effort to develop an open, Python-based standard library for medical physics applications. *Journal of Open Source Software*, 7(78), 4555. https://doi.org/10.21105/joss.04555

Record the version and scientific procedure used alongside the citation. The [Statement of Need](../statement-of-need.rst) provides project context; the [scientific evidence catalogue](../contrib/evidence/index.md) records the limits of specific experiments.

## Reuse and licences

PyMedPhys's own code uses the [Apache License 2.0](https://github.com/pymedphys/pymedphys/blob/main/LICENSE). Published packages also bundle MIT-licensed code, including the Pinnacle exporter with its [MIT licence](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_pinnacle/LICENSE-MIT), and declare `Apache-2.0 AND MIT` in `pyproject.toml`. Bundled code and data retain their individual notices in source headers, generated-data metadata and associated files; check a downloaded dataset's licence at its source. See [Fixture and data guide](../contrib/validation/data.md) for provenance, permitted samples and retirement. Packaging must preserve required licences and PEP 639 metadata.

Recheck this page when citation, maintainers, licensing or community channels change.

```{toctree}
:hidden:

../statement-of-need
```
