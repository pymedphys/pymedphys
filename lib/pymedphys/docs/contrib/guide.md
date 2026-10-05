# Developer guide

Use these guides to change the current PyMedPhys source, check the result,
and prepare it for review. They are written for physicists and other scientists
as well as software developers. For installing or using a released version,
start with the [user guide](../users/get-started/index.md).

## Choose your next task

| I want to... | Start here |
| --- | --- |
| Make my first contribution | [Start contributing](start/index.md) |
| Install the tools and create a checkout | [Set up a development environment](start/setup.md) |
| Change an API, command, app, or dependency | [Make a change](guides/make-a-change.md) |
| Write a page, notebook, or API reference | [Author documentation](guides/authoring.md) |
| Understand where a feature lives | [Architecture and repository map](architecture/index.md) |
| Write or select tests | [Run and write tests](validation/testing.md) |
| Establish a scientific result | [Scientific evidence](validation/scientific.md) |
| Add or replace test data | [Fixtures and external data](validation/data.md) |
| Review, maintain, or release PyMedPhys | [Maintainer tasks](maintainers/index.md) |
| Find a programme's decisions or recorded results | [Design documents](design/index.md) and [validation records](evidence/index.md) |

The [contribution policy](https://github.com/pymedphys/pymedphys/blob/main/CONTRIBUTING.md)
sets the rules for pull requests, documentation, changelog entries, and review.
Read it before submitting work. Keep patient-identifying information out of
public issues, pull requests, screenshots, notebooks, and attached files;
the policy explains how to report an accidental disclosure privately.

## A contribution from start to finish

1. [Set up your checkout](start/setup.md), then create a working branch.
2. Describe the problem and an observable outcome. For a small fix, a concrete
   before-and-after example is enough. For a larger programme, read its design
   document and tracking issue first.
3. [Make the change](guides/make-a-change.md), with the tests and documentation
   needed to support its behaviour.
4. [Choose appropriate checks](validation/testing.md#choose-checks-for-your-change)
   and inspect the documentation preview when pages or examples change.
5. [Open the pull request and respond to review](start/first-contribution.md).
   Reviewers should be able to reproduce the result from the evidence supplied.

Current contributor procedures describe `main`. Historical implementation
articles and validation records identify their own revisions; treat their
commands and results as evidence for those revisions. The public documentation's
`stable` version describes the latest stable release, while `latest` describes
the development branch.

```{toctree}
:maxdepth: 2
:hidden:

start/index
guides/index
architecture/index
validation/index
maintainers/index
design/index
evidence/index
index
```
