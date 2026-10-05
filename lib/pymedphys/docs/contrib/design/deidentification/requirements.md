---
myst:
  heading_anchors: 3
---

# DICOM de-identification requirements and evidence

## Requirements register

The requirements register traces the standard's "shall" statements and the MIDI best practices to the decisions, code, and tests that satisfy them. It is `lib/pymedphys/_dicom/deidentify/requirements.toml`, curated by hand, and records:

- every paragraph of PS3.15 Annex E in the pinned edition that contains "shall", outside Notes and tables, verbatim with any list it introduces and a link to the paragraph;
- the 18 best practices of MIDI §1.6, summarised in PyMedPhys's words.

Like the generated tables, the file carries the attribution "DICOM PS3.15 2026d, © NEMA" (D-001).

Identifiers are stable and never reused. `PS3.15-E.1.1-01` numbers the paragraphs of a section in the standard's order, and `MIDI-BP-01` to `MIDI-BP-18` follow the report's numbering. Each entry cites the decisions that address it and has one of these statuses:

| Status | Meaning | Entry also records |
| --- | --- | --- |
| `planned` | In scope, not yet implemented | The milestone that completes it |
| `partial` | Partly implemented | Modules and tests so far, what remains, and the milestone that completes it |
| `implemented` | Met for the supported scope | Modules and the tests that show it |
| `out-of-scope` | Not supported, such as an Option that Scope excludes | A note saying why |
| `not-applicable` | Outside PyMedPhys's role, such as re-identification | A note saying why |

- A pull request that implements part of a requirement updates its entry in the same change.
- `pymedphys._dicom.deidentify.requirements.load_requirements` rejects malformed or inconsistent entries, such as an implemented requirement without tests or an exclusion without a note. Tests check that every cited decision and module exists, that pytest collects every cited test, and that the register follows the edition of the generated tables.
- A new edition updates the register with the tables, after comparing it with every Annex E page of that edition: add paragraphs, update changed text, and remove deleted paragraphs without reusing their identifiers.
- Normative text without "shall", such as the paragraphs after Table E.1-1a on actions for Sequences and on Options overriding the Profile, gets entries when the engine implements it.
- The traceability matrix for each release (D-018) is generated from the register by `pymedphys dev deid-matrix`, as Markdown, and is not committed. It summarises the entries by status and source, and lists each requirement with its milestone, decisions, modules, and traced tests, the exclusions with the reason for each, and the remaining work with its milestone. Given pytest JUnit XML reports with `--junit`, one for each tested environment, it gives each traced test's outcome. A requirement's traced tests pass only when every case of every test that traces it passed in every report: a skipped case, or a test or case that one report lacks although another ran it, leaves them incomplete; passing tests do not make a partial requirement met. `--check` exits with status 1 when a traced test failed, was skipped, or did not run. Each release renders the matrix from the reports of every environment in the unit-test matrix, checks it, and attaches it to the GitHub release.

## Documentation matrix and release evidence

The [generated requirements matrix](https://docs.pymedphys.com/en/latest/contrib/info/deidentification-requirements.html)
renders the committed register during every documentation build. It describes
coverage and remaining work without test outcomes. Edit
`lib/pymedphys/_dicom/deidentify/requirements.toml` rather than that generated page.

A release's matrix adds its own pytest JUnit XML results. Keep that matrix
with the release's conformance statement and the category-specific benchmarks
required by [Published benchmark results](decisions.md#d-018-published-benchmark-results).
Tests passing for a partial requirement do not make it implemented, and an
object's presence in a generated standards table does not make it supported.
The [release guide](../../info/release-guide.md) describes how these artefacts
are published; the [contributor procedure](contributing.md) describes updating
and checking the register.

```{toctree}
:hidden:

../../info/deidentification-requirements
```
