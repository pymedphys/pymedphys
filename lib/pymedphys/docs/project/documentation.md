---
myst:
  heading_anchors: 3
---

# Documentation ownership and migration

For documentation authors and maintainers checking scope, canonical sources and retained links. The restructure is tracked in [#1665](https://github.com/pymedphys/pymedphys/issues/1665), with tutorial work linked to [#1634](https://github.com/pymedphys/pymedphys/issues/1634) and release guidance to [#2140](https://github.com/pymedphys/pymedphys/issues/2140).

The audit used `f5e0dd6785768fe934ad06d277c1eac1a6814f78`. Implementation started from `7276c309741ada6087a8845604b42f5b823d54b2`, including subsequent de-identification preservation work. The migration manifest uses that implementation baseline's rendered URLs and section fragments. During implementation, `main` advanced to `eaf3abee4038b30b5e1e82ef7bf94f36409f48d6`; its D-009 update was transferred verbatim into the canonical decisions page, preserving the accompanying implementation and register updates.

## Inventory and canonical sources

Download the [page inventory](documentation-inventory.csv) and [migration manifest](documentation-migration.json). The inventory records each maintained source's audience, purpose, status, authority, inbound source links, destination and update trigger. Generated pages are identified separately. The manifest records every baseline page URL and its rendered section fragments; old pages remain available when their contents have moved.

The [public-reference coverage register](reference-coverage.md) maps current exports and parser commands to contracts and task guides, with experimental gaps identified explicitly.

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

## Check a migration

**Prerequisites:** a complete documentation build, with generated pages prepared. **Inputs:** built HTML and the committed manifest. **Outputs:** a report of retained URLs/fragments, destinations and broken local HTML links. **Success:** the checker exits zero and each changed reader path has been inspected in the rendered site.

From the repository root:

```shell
uv run python .github/scripts/check_documentation_migration.py lib/pymedphys/docs/_build/html
```

The checker reads the manifest independently of the new navigation. It also validates local HTML links and fragments, report downloads and bundled assets. External links remain the responsibility of the documentation link checker and manual inspection of advisory failures. Source-view links, notebook launches, desktop/narrow navigation, search and hosted version selection also need inspection.

Compatibility pages preserve headings or explicit HTML anchors and direct readers to the canonical destination. Keep the manifest when future migrations occur; append newly moved pages rather than discarding earlier URL commitments.

## Completion and remaining decisions

The accepted restructure supplies task paths, contributor procedures, a maintainer handbook, design/evidence catalogues and user workflows. The inventory and migration check describe the delivered sources. Governance proposals remain explicitly pending on the [compatibility page](compatibility.md). Scientific records and partial studies retain their achieved scope, including unmeasured cases; documentation organisation does not fill those scientific evidence gaps.

Confirm tutorial commands with their supplied synthetic or approved inputs before claiming a first successful result. Vendor integrations also need an authorised local service or vendor dataset for end-to-end verification. Record those limits in the workflow and PR rather than implying that a source audit constitutes a live clinical verification.
