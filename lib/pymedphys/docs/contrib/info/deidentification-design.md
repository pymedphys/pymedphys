# DICOM de-identification: design and decision log

This is a living document. It records the design of the DICOM de-identification engine that replaces `pymedphys.dicom.anonymise` and the experimental pseudonymisation module, the decisions taken and why, and the state of implementation. Every pull request that touches de-identification updates it: status, decision log, and the "Open questions and next pull request" section.

For the user-facing explanation of terms and current limitations, see [DICOM de-identification](../../users/background/dicom-deidentification.md).

## Status

| Item | State |
|---|---|
| Design | Agreed with maintainers; refined per pull request |
| Implementation | Not started (milestone M0 in progress) |
| DICOM edition targeted | PS3.15 2026d |
| Last updated by | PR 01 (design document, contributor principles, background page) |

## Scope

In scope:

- De-identification of DICOM instances, including RT Structure Set, RT Plan, RT Dose, RT treatment records, RT Image, registration, segmentation, CT, MR, and PET, as a single collection with referential integrity preserved.
- A library API, a command-line interface, and a Streamlit application.
- Evidence of conformance and of de-identification performance: a conformance statement, a requirements register with traceability to tests, and published benchmark results.

Out of scope for the engine itself (documented as residual risk, with plugin hooks where relevant):

- Removing burned-in text from pixel data (Clean Pixel Data Option) and removing recognisable visual features such as faces (Clean Recognizable Visual Features Option).
- Legal determinations. Whether a de-identified collection is "anonymous" depends on the disclosure context, not on the software.

## Terminology and claims

The engine performs **de-identification**, the term used by DICOM PS3.15 and by the MIDI Task Group report. Anonymisation and pseudonymisation are not separate features:

- Both use the same transformation. What differs is whether a means of re-identification is retained (a project key or a crosswalk held by a custodian) and which indirect identifiers the chosen options retain.
- Whether data are anonymous is a legal conclusion about the data in their release context (for example GDPR Recital 26, the Australian Privacy Act 1988 (Cth) s 6, or the UK ICO's motivated intruder test). Software cannot make that conclusion.

Wording rules for code, command-line output, reports, and documentation:

- The technical claim is always "de-identified in accordance with DICOM PS3.15 *edition* Basic Application Level Confidentiality Profile with options *list*".
- The engine never describes its output as "anonymised".
- Where a key or crosswalk is retained, documentation states that the data remain pseudonymised personal data for whoever holds it, and that a separate recipient needs its own assessment.

## Normative and guidance basis

| Role | Source |
|---|---|
| Normative technical rules | [DICOM PS3.15 Annex E, Attribute Confidentiality Profiles](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html), edition 2026d: E.1.1 (de-identifier), Table E.1-1 (attribute actions), E.1.3 (conformance statement contents), E.2 (Basic Profile), E.3 (Options), Table E.3.4-1 (structured content), Table E.3.10-1 (safe private attributes) |
| Supporting DICOM parts | PS3.3 (attribute Types per IOD), PS3.4 (SOP Class to IOD), PS3.5 (UID encoding, UUID-derived UIDs), PS3.6 (data dictionary, well-known UIDs), PS3.10 (File Meta Information), PS3.16 (CID 7050 de-identification method codes, CID 7005 contributing equipment purpose) |
| Best practice companion | Clunie DA et al. *Report of the Medical Image De-Identification (MIDI) Task Group: Best Practices and Recommendations*, report dated 2025-02-07, [arXiv:2303.10473](https://arxiv.org/abs/2303.10473) (preprint) |
| Validation resources | NCI MIDI synthetic identifier datasets, answer keys, and validation scripts; `dciodvfy` and `dcentvfy` from dicom3tools for object validity and cross-object consistency (validity only, not privacy) |
| Governance context (documentation only) | UK ICO anonymisation guidance; GDPR Article 4(5) and Recital 26; CJEU C-413/23 P *EDPS v SRB* (4 September 2025); Privacy Act 1988 (Cth) and OAIC de-identification guidance; ISO 25237:2017 (pseudonymisation) |

The rules applied by the engine are generated from the pinned edition of the standard, never transcribed by hand. The MIDI report's best practices are recorded as requirements alongside the standard's "shall" statements, so that every requirement can be traced to the code that implements it and the tests that check it.

## Why the existing tools are replaced

Both existing paths share one engine in `lib/pymedphys/_dicom/anonymise/` and have defects that cannot be fixed without redesign:

- `pymedphys.dicom.anonymise` keeps every UID, replaces reference sequences such as Referenced Image Sequence with an empty item (breaking references), writes invalid values (Patient's Sex `ANON`), never records that de-identification took place, and does not implement a PS3.15 profile. Its keyword list derives from an old edition of Table E.1-1 of about 220 rows; edition 2026d has 657.
- The experimental pseudonymisation module hashes UIDs and decimal strings without a secret, so anyone holding the original UIDs can re-link records and small-range values such as weight can be recovered by trying every plausible value. It jitters ages non-deterministically, applies one date offset to every patient on an installation, fails on non-ASCII names, maps Dose Reference UID but not Referenced Dose Reference UID (breaking the RT Plan to treatment record link), and misses most enhanced RT UIDs.
- Both write the original SOP Instance UID and the original 128-byte preamble back into every output file. pydicom 3 only re-synchronises the File Meta Information when `enforce_file_format=True`, which the existing code does not pass.
- Error handling logs original values, and file handling prints original paths.

## Architecture

The package will live in `lib/pymedphys/_dicom/deidentify/` with the public API exposed from `pymedphys.dicom`. The main parts, in the order they will be implemented:

1. **Generated standard tables (rule layer L1).** Table E.1-1 with every option column, Tables E.1-1a, E.3.4-1, and E.3.10-1, CID 7050, well-known UIDs, the VR and VM of every Table E.1-1 attribute, and attribute Types for supported IODs. A development command regenerates them from the standard and records the edition, the source file digest, and a content digest.
2. **Supplementary rules (rule layer L2).** Reviewed rules, each with a rationale, for attributes the table does not list but that the de-identifier is still responsible for: dates, times, and person names by value representation; operator-entered RT text outside the table such as Beam Name and Dose Comment; RT Image machine names; and a classification of every UID attribute as class-typed or instance-typed. A test fails if the dictionary contains an attribute in one of these categories with no rule.
3. **User rules (rule layer L3).** Validated overrides. Options are the primary configuration. Additional removals are always allowed; additional retentions require an explicit acknowledgement that the result is not conformant, and the justification is recorded.
4. **UID engine.** Every UID value that is not class-typed and not a well-known value is replaced by the same function everywhere it occurs, in any sequence, in the File Meta Information, and in retained private elements. The replacement is a keyed HMAC-SHA256 of the original, formatted as a version 8 UUID and encoded as a `2.25.` UID of at most 44 characters. Mapping by value rather than by attribute list keeps links intact even where the table covers one side of a reference and not the other.
5. **Keys.** A 256-bit key is either ephemeral (discarded after the run, so links hold within the run only) or a project key held by a custodian (links hold across runs, as incremental RT collections need). Derivations for UIDs, identifiers, and date offsets are domain-separated. Keys are never logged or written into outputs.
6. **Temporal handling.** Removal (Basic Profile), full retention, or per-subject whole-day shifts that keep times, intervals, and optionally the weekday. Dates found inside free text are removed rather than shifted.
7. **Free text.** A vocabulary-based cleaner that keeps only known-safe tokens (the only basis for claiming the Clean Descriptors Option), a scanner for echoes of the patient's own identifiers, value checks on code strings and numeric strings, and pooled human review of every distinct retained string.
8. **Private attributes.** Removed by default. With the Retain Safe Private Option, retained only when shown to be safe by the routes E.3.10 allows, matched by private creator regardless of block, with the basis for each retained element recorded.
9. **Container.** File Meta Information and preamble rebuilt, group 0004 and trailing padding removed, encapsulated documents replaced or sequestered, and metadata inside compressed pixel data bitstreams stripped without recompression.
10. **Referential integrity.** A first pass builds a graph of instances and references and reports dangling references, frame of reference mismatches, and inconsistent hierarchy before anything is written. After writing, the engine verifies that the mapping is one-to-one and that no original instance UID remains.
11. **Risk detection and quality control.** Risk indicators for burned-in text and potentially reconstructable faces (including RT Structure Set body contours of head and neck cases), sequestration of object types that cannot be cleaned, a human review pack, and statistical disclosure control support for retained indirect identifiers.
12. **Reports.** A machine-readable and human-readable report per run, a conformance statement generated from the rule tables, and a traceability matrix from requirements to tests.

## Presets

| Preset | Purpose | Options claimed |
|---|---|---|
| `basic` (default) | Strict conformance to the Basic Profile | Basic Profile only |
| `tps-import` | Research copies that import into commercial treatment planning systems | Basic Profile, Retain Longitudinal Temporal Information with Modified Dates, Retain Patient Characteristics, Retain Device Identity, Clean Descriptors |
| `public-release` | Unrestricted public sharing, following the MIDI best practices | Basic Profile, Retain Longitudinal Temporal Information with Modified Dates, Clean Descriptors, Retain Safe Private |

Each preset claims exactly the options it applies. Details of each preset are recorded in the decision log as they are implemented.

## Decision log

Entries are numbered and never deleted. A superseded decision is marked as such and points to its replacement.

### D-001: One engine, called de-identification

- **Context.** Anonymisation and pseudonymisation were implemented as separate features with separate defects, and "anonymised" implies a legal status the software cannot establish.
- **Decision.** One engine. Re-identification capability is a property of key custody, not a different transformation. The wording rules above apply everywhere.
- **Consequences.** The legacy API names are deprecated. Documentation explains key custody and recipient context instead of promising anonymity.

### D-002: Rules generated from a pinned edition of the standard

- **Context.** The legacy keyword list was transcribed from an old edition and drifted. The standard is revised about five times a year.
- **Decision.** Generate all rule tables from the pinned edition (currently 2026d). Record provenance. Check monthly for a new edition and open an issue when the generated tables would change.
- **Consequences.** Table changes arrive as reviewable generated diffs. Hand edits to generated files are never accepted.

### D-003: UIDs mapped by value with a keyed function

- **Context.** Table E.1-1 does not list every instance UID attribute (for example Target Frame of Reference UID), so mapping only listed attributes would leak original UIDs and break references. Unkeyed hashing lets anyone with the original UIDs re-link. A shared lookup table is fragile under parallel processing and cannot be reproduced later.
- **Decision.** Replace every non-class, non-well-known UID value with HMAC-SHA256 under the run's key, formatted as a version 8 UUID in a `2.25.` UID. An organisation root under the PyMedPhys root UID is available as an option for systems that cannot handle long numeric components.
- **Consequences.** Links survive regardless of which attributes the table lists. Output is deterministic for a given key and independent of the number of worker processes. Replacement UIDs contain no timestamp.

### D-004: pydicom 3.0 as the minimum version

- **Context.** The package declares `pydicom>=2.0.0` but continuous integration only tests the locked 3.0.2. The engine needs pydicom 3 behaviour for writing File Meta Information.
- **Decision.** Raise the minimum to 3.0.
- **Consequences.** No compatibility layer for pydicom 2. Existing code that uses pydicom 3 deprecated arguments keeps working with deprecation warnings; migrating it before pydicom 4 is separate work.

### D-005: Standard library parsers for the table generator

- **Context.** The generator parses the standard's published HTML and DocBook XML. Bandit flags the standard library XML parser.
- **Decision.** Use `html.parser` and `xml.etree.ElementTree`. Verify the source file's SHA-256 before parsing, and justify each `nosec` comment as the security policy requires.
- **Consequences.** No new dependency. The parser only ever sees verified publications, in a development-only tool.

### D-006: Treatment planning system import defaults

- **Context.** Commercial planning systems may reject empty identifiers, invalid values, or future-dated plans.
- **Decision.** For `tps-import`: shift dates backwards only, by a whole number of weeks between 52 and 520, never zero, preserving the weekday. Generate conspicuously synthetic names and identifiers (for example `ZZRESEARCH^...`). Write a synthetic birth date derived from the shifted study date and the patient's age at year precision, with an option to leave it empty.
- **Consequences.** Imported research copies are recognisable as such and date intervals such as fractionation patterns are preserved. The synthetic birth date reveals no more than the retained age. The documentation requires import into non-clinical databases only.

### D-007: Public release defaults

- **Context.** The MIDI report recommends a quantified risk threshold, human quality control, and caution with potentially reconstructable faces.
- **Decision.** For `public-release`: statistical disclosure control threshold 0.09 by default (0.05 selectable); human review of every distinct retained string, every series (by maximum intensity projection or cine strip), and every instance in high-risk categories; potentially reconstructable facial information is a hard block unless a risk assessment reference is recorded; a human quality control attestation is required before a run can be marked ready for release.
- **Consequences.** Public release requires deliberate human involvement, as the MIDI report and NCI evaluation results indicate it should.

### D-008: UID root

- **Decision.** `2.25.` UIDs derived from version 8 UUIDs by default; the organisation root is opt-in. See D-003.

### D-009: Deprecation window

- **Decision.** `pymedphys.dicom.anonymise` and the `pymedphys dicom anonymise` command remain for one minor release with a deprecation warning, then are removed. The experimental pseudonymisation module is deprecated immediately, with a security note, and removed in the same release.

### D-010: Published benchmark results

- **Decision.** Results against the NCI MIDI validation resources are published in the documentation for each release, as separate metrics rather than a single score.

### D-011: Private SOP Classes

- **Context.** PS3.15 states that de-identification of Private SOP Classes is not defined.
- **Decision.** Instances of Private SOP Classes are excluded by default and listed in the report. Processing them is opt-in and falls outside the conformance claim.

### D-012: No Safe Harbor preset

- **Context.** The HIPAA Safe Harbor method is not a DICOM profile, a DICOM date cannot hold a year alone, and the "comparable images" provision is open to interpretation for head imaging.
- **Decision.** No preset carries a regulatory name. The documentation maps DICOM profile behaviour to regulatory frameworks without claiming compliance.

### D-013: Encrypted Attributes Sequence deferred

- **Context.** PS3.15 prefers the Encrypted Attributes Sequence for re-identification. The MIDI report advises against encrypted original values in publicly released data.
- **Decision.** Not in the first release. If added later, it is for controlled sharing only and never enabled by `public-release`.

### D-014: Pixel data protections are detect and warn

- **Decision.** The engine detects and reports risk from burned-in text and recognisable features, never claims the Clean Pixel Data or Clean Recognizable Visual Features Options, and never sets Burned In Annotation or Recognizable Visual Features to NO. Optical character recognition and defacing may be added later as optional plugins.

### D-015: Small pull requests with documentation

- **Context.** Maintainers review this work by hand.
- **Decision.** Each pull request has a single concern and about 400 lines of hand-written change at most, excluding tests and documentation. Generated data is kept separate from logic. Every pull request includes docstrings, user documentation for user-visible changes, a changelog entry, and an update to this document.

## Implementation roadmap

| Milestone | Pull requests | Content |
|---|---|---|
| M0 Hygiene | 01 to 06 | This document and contributor principles; stop legacy code logging identifying values; deprecate experimental pseudonymisation with a security note; pydicom 3.0 minimum; bind the GUI to localhost; add Hypothesis for property tests |
| M1 Standard | 07 to 13 | Table parser and generator command; generated Annex E tables; data dictionary, code, and attribute Type tables; requirements register |
| M2 Primitives | 14 to 20 | Keys, UIDs, value representation validators and dummy values, dates, selectors and actions, policy and presets, supplementary rules |
| M3 Engine | 21 to 28 | Dataset transformation, File Meta Information, private attributes, text cleaning, bitstream metadata, public dataset-level API |
| M4 Pipeline | 29 to 37 | File discovery and writing, reference graph, two-pass pipeline with verification, reports, risk detection, review pack, disclosure control, presets |
| M5 Interfaces | 38 to 42 | Command-line interface, legacy deprecation, Streamlit application |
| M6 Evidence | 43 to 46 | How-to guide, generated conformance statement, traceability matrix, evidence workflow with published benchmark results |
| M7 Later | | Remove legacy APIs; Clean Structured Content; de-identification of accompanying spreadsheets with the same key; Encrypted Attributes Sequence for controlled sharing |

## Open questions and next pull request

- **Next: PR 02.** Stop the legacy code from logging identifying values and printing original paths (`_dicom/anonymise/core.py` and `_dicom/anonymise/api.py`), with tests that capture logs and standard output.
- **Open:** confirm the licence terms of the AAPM TG-263 structure name list before vendoring it as part of the vocabulary cleaner (needed by PR 25).
- **Open:** confirm the licence terms of the TCIA synthetic identifier datasets before caching them for slow tests (needed by PR 31).
