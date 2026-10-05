# Documentation ownership and migration

For documentation authors and maintainers checking scope, canonical sources and
update responsibilities. Follow [#1665](https://github.com/pymedphys/pymedphys/issues/1665)
for the restructure, [#1634](https://github.com/pymedphys/pymedphys/issues/1634)
for tutorials and [#2140](https://github.com/pymedphys/pymedphys/issues/2140)
for release guidance.

## Canonical sources

Canonical ownership is:

| Material | Authoritative source |
| --- | --- |
| Contributor-wide rules | Repository `CONTRIBUTING.md`, copied into the contributor-policy page |
| Human procedures and factual explanations | Task guides verified against the implementation |
| Programme scope and decisions | Programme design pages, including the canonical de-identification decisions |
| Agent-specific mandates | `AGENTS.md`, linking shared human guidance |
| Public function contracts | API docstrings, rendered through autodoc |
| Command options | Argparse parser definitions, rendered through sphinx-argparse |
| Requirements and traceability | Curated requirements register; matrices are generated |
| Homepage and release notes | Repository README and CHANGELOG, copied during build preparation |

Current, experimental, planned and historical material must identify its scope. A recorded scientific result applies only to its revisions, methods, inputs and environment. Do not rewrite recorded conditions as current instructions. Keep each report's figures, CSVs, provenance and compressed outputs with its report.

## Ownership and update triggers

Matthew Jennings coordinates this documentation restructure through #1665. Workstream owners remain responsible for keeping their shared procedures aligned with their sources. Subject review is required for scientific and vendor-specific claims; coordinate an appropriate reviewer on the corresponding PR rather than treating the following roles as an appointment policy.

| Workstream | Documentation maintainer | Subject review | Update trigger |
| --- | --- | --- | --- |
| Navigation, authoring and migration | Matthew Jennings | Documentation/build maintainer | New page, source move, build or theme change |
| Onboarding, architecture and tests | Matthew Jennings | Maintainer of the affected module/tool | Parser, exports, markers, packaging or setup change |
| Maintainer handbook and compatibility | Matthew Jennings | CI/release administrator and policy maintainer | Workflows, hosted settings, release or adopted policy change |
| De-identification programme | Matthew Jennings | DICOM programme reviewer | Standards edition, requirement, decision or implementation milestone |
| Gamma and coordinate evidence | Matthew Jennings | Medical physics/scientific reviewer | New result, method, artefact or evidence revision |
| User and vendor workflows | Matthew Jennings | Workflow owner; vendor specialist where needed | Supported input, configuration, adapter, limitation or output change |

## Check documentation changes

Prepare and build the documentation with warnings treated as errors, following
the [documentation guide](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html#building-the-documentation-on-your-workstation).
Inspect each changed page in the rendered site, its local links, retained
section anchors, report downloads, source links and notebook examples. Check
the reader's route through navigation and search on desktop and narrow screens.
External-link reports and manually checked advisory failures form separate evidence.

The contributor procedures, maintainer handbook and design/evidence catalogues
are available from the [Developer guide](../contrib/guide.md). User instructions
remain in [Getting started](../users/get-started/index.md) and
[How-to guides](../users/howto/index.md). Track the user task navigation and
complete URL/fragment inventory in #1665 alongside this work.
