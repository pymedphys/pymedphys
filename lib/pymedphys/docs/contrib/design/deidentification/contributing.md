---
myst:
  heading_anchors: 3
---

# Contributing to DICOM de-identification

For a change to the engine:

1. Check the [scope and implementation status](index.md), then identify the
   affected [specification](specification.md) and [decisions](decisions.md).
2. Update the implementation, focused tests, and requirements register together.
3. Update user guidance when supported behaviour or a limitation changes.
4. Check traceability and retain the evidence appropriate to the change.

## Change a decision or requirement

Read the complete decision, including its standards basis, rationale, and test
expectations. Update its text to describe the final design, and preserve its
identifier. The [requirements register](requirements.md) links those identifiers
to implementation modules and collected pytest tests.

Edit `lib/pymedphys/_dicom/deidentify/requirements.toml` in the same change.
Use `planned` or `partial` until the supported requirement is met; list the
remaining work for a partial entry and the reason for an exclusion. Cite tests
that check the stated requirement, including every parametrised case that the
claim depends on. Keep implementation and test paths relative to
`lib/pymedphys` so the register also works from an installed package.

Run the register checks from the repository root after the
[locked development setup](../../setups/index.rst):

```console
uv run -- pymedphys dev tests tests/dicom/test_deidentify_requirements.py
```

Success means the register loads, cited decisions and modules exist, and pytest
collects every traced test. This check validates traceability; run the affected
behaviour's tests as well. Record their results with the change.

The public library and command line expose only supported behaviour. Check the
legacy-migration decision before adding a deprecation warning: a released
replacement and migration guidance must cover that interface's use first.
Keep the user [de-identification guidance](../../../users/background/dicom-deidentification.md)
aligned with the coverage actually shipped.

## Update the pinned DICOM edition

Follow [Tables generated from a pinned edition](decisions.md#d-001-tables-generated-from-a-pinned-edition)
when changing the source pin, parsers, corrections, or generated tables. Review
the generator and generated data separately. Compare the hand-curated register
with every Annex E page of the new edition, including normative paragraphs
that the generated table comparison does not detect. Preserve the source
provenance and attribution.

Generate the tables from the new verified publication, then check that the
same sources reproduce the committed output:

```console
uv run -- pymedphys dev deid-tables
uv run -- pymedphys dev deid-tables --check
```

Both commands need the publication pages, either downloaded from NEMA or
supplied with `--source-dir` in the layout described by `--help`. `--check`
returns status 1 if tables are missing or differ. Never edit generated tables
by hand. Run the table-generator and loader tests appropriate to the change.

To inspect changes in the current publication without changing the pin or
writing tables:

```console
uv run -- pymedphys dev deid-tables --check-current
```

Status 0 means no generated table would change, 1 means a table would change,
and 3 means a page could not be fetched or a table generated. This comparison
does not check the hand-curated normative paragraphs. The
[workflow guide](../../info/workflows.md) describes the monthly edition check.

## Generate evidence for a release

Generate a register-only matrix for inspection:

```console
uv run -- pymedphys dev deid-matrix --output requirements-matrix.md
```

For release evidence, supply one JUnit report from each tested environment:

```console
uv run -- pymedphys dev deid-matrix --junit junit-environment-a.xml --junit junit-environment-b.xml --check --output requirements-matrix.md
```

Replace the example paths with the retained reports. `--check` requires at
least one report and returns status 1 when a traced test failed, was skipped,
or did not run. A requirement's tests must pass in every supplied environment;
retain the environment identities with the reports. Use the complete release
matrix required by the [runtime-environment decision](decisions.md#d-029-runtime-environments)
and [release guide](../../info/release-guide.md) for a release claim, rather
than promoting a focused local selection to complete evidence.

Publish the conformance statement, matrix, supported coverage and exclusions,
and separate MIDI benchmark categories described by
[Published benchmark results](decisions.md#d-018-published-benchmark-results).
Refresh that evidence for later releases that change the engine.

## Roadmap

Milestones group outcomes; they are not a sequence of pull requests or releases. Each pull request ships its own tests, documentation, and traceability, and M6 consolidates the evidence. The first supported release needs only the parts of M1 to M5 that its scope uses.

| Milestone | Outcomes | Done when |
| --- | --- | --- |
| M0 Legacy hygiene | Diagnostics free of identifying values and paths; limitation warnings and notices (D-019); pydicom minimum (D-002) | Each change has regression tests and documentation, and remaining disclosure channels are listed in the tracking issue. Hygiene does not make the legacy tools conform. |
| M1 Standard | Table generator and generated tables, including the PS3.3 Types of every composite IOD with its Functional Group Macros, generated for all but the three real-time IODs, which also need PS3.6 Table 9-1 (D-001); requirements register; monthly edition check (D-001) | Source provenance and table coverage are verified, and the generator and generated data are reviewed separately. |
| M2 Primitives | Keys and subject profiles; UID replacement; patient pseudonyms; date offsets; VR and VM validators and dummy values (D-021); rule layers, including the reviewed rules for the text, dates, times, and other attributes that Table E.1-1 omits (D-022, D-023), and preset composition; method digest (D-024) | Primitives and policy conflicts are validated before integration. Hypothesis is added with the first property tests that use it. |
| M3 Engine | Dataset transformation, with actions resolved by Type (D-020) and markers (D-012); file container (D-025); private attributes (D-028); descriptor cleaning; bitstream metadata; dataset-level API | Each component has tests, API documentation, and conformance evidence for explicitly supported input. A dataset-level API does not establish collection integrity or readiness to release. |
| M4 Pipeline | Discovery and writing through a staging area; reference graph with graded consequences (D-026) and two-pass verification; residual search (D-027); reports; risk detection; QC pack and attestation; statistical assessment; end-to-end preset validation | Graph and subject consistency, the separation of reports, QC material, and state, and every preset gate are verified. |
| M5 Interfaces and migration | Command line using the same engine as the library, for the first supported release, including the nomenclature converter commands that run as `python -m pymedphys._nomenclature` until then, with the test that keeps the tool's commands out of the `pymedphys` command line changed to require them; the app, after its own design for keys and QC material, in a later release (Scope); migration guides; deprecation warnings when D-019 allows | Only supported behaviour is exposed, with user documentation. |
| M6 First supported release | `basic` and `basic-clean-descriptors` enabled; how-to guide, generated conformance statement, requirements-to-tests matrix, and benchmark results (D-018) for the release scope | Evidence is published for the shipped coverage and exclusions are documented; the evidence is refreshed for each later release. |
| M7 Legacy removal | Removal of both legacy interfaces | The deprecation window in D-019 has passed. |

Later work needs its own design, tests, and conformance review: Clean Structured Content, accompanying spreadsheets pseudonymised with the same key, the Encrypted Attributes Sequence for controlled sharing (D-013), and the unsupported objects and options listed under Scope. Generating a table in M1 does not enable the corresponding option or support the corresponding IOD.
