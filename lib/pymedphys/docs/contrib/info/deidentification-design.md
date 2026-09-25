# DICOM de-identification: design and decision log

This is the living source of truth for the planned DICOM de-identification engine that will replace `pymedphys.dicom.anonymise` and the experimental pseudonymisation module. It records the intended behaviour, decisions and their rationale, implementation progress, and remaining work. The architecture and presets describe the target, not capabilities available today. Every de-identification pull request updates its own progress entry and any affected decisions, roadmap dependencies, open questions, or user documentation.

The programme will require many small, single-concern pull requests. There is no fixed total or preallocated PR sequence. Milestones group related outcomes; each contains as many reviewable PRs as needed. The near-term queue is only the next slice of work, not the whole programme (D-015 and D-022).

For the user-facing explanation of terms and current limitations, see [DICOM de-identification](../../users/background/dicom-deidentification.md).

## Status

| Item | State |
| --- | --- |
| Design | Agreed with maintainers; refined per pull request |
| Legacy hygiene | M0 documentation and diagnostic fixes under review; see Progress |
| Replacement engine | Not implemented or available; architecture and presets below are planned |
| DICOM edition targeted | PS3.15 2026d |

## Progress

Record actual opened or merged PRs here, using their GitHub numbers, scope, status, validation, and remaining limitations. Future work belongs in the roadmap and near-term queue. Each PR maintains its own entry to reduce conflicts; it must also reconcile shared decisions and planning where its findings change them. Update merge status when reconciling the next PR; "open" is not evidence of a shipped feature.

- **[#2061](https://github.com/pymedphys/pymedphys/pull/2061), M0 design and documentation.** Open. Establishes this design, contributor principles, and user guidance. D-016 to D-021 record the technical review corrections; D-022 records the rolling plan and consistency rules. Documentation checks cover links and a Sphinx build with warnings treated as errors and notebook execution disabled. No replacement engine or deprecation warnings are implemented here.

- **[#2062](https://github.com/pymedphys/pymedphys/pull/2062), M0 legacy diagnostics.** Open, based on #2061. Removes identifying values and paths from explicit application logging and progress output, with capture tests. Eight canary tests capture DEBUG logs and both standard streams; the PR reports them passing alongside pre-commit, type/lint checks, and an app-render check. The existing download-dependent tests were blocked locally by Zenodo access and rely on CI. Re-raised exceptions and pydicom value-validation warnings remain separate disclosure channels, tracked in the near-term queue. This is a partial implementation of D-020, not a deprecation change or a claim that every diagnostic channel is sanitised.

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

- The technical claim, only after validating the effective policy and output, is "de-identified in accordance with DICOM PS3.15 *edition* Basic Application Level Confidentiality Profile with options *list*". Preset selection alone does not establish conformance. Claims and method codes must reflect the options actually satisfied; permitted nonconformant processing is explicitly labelled, with unsupported claims and codes suppressed (D-017).
- The engine never describes its output as "anonymised".
- Where a key or crosswalk is retained, documentation states that the data remain pseudonymised personal data for whoever holds it, and that a separate recipient needs its own assessment.

## Normative and guidance basis

| Role | Source |
| --- | --- |
| Normative technical rules | [DICOM PS3.15 Annex E, Attribute Confidentiality Profiles](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html), edition 2026d: E.1.1 (de-identifier), Table E.1-1 (attribute actions), E.1.3 (conformance statement contents), E.2 (Basic Profile), E.3 (Options), Table E.3.4-1 (structured content), Table E.3.10-1 (safe private attributes) |
| Supporting DICOM parts | PS3.3 (attribute Types per IOD), PS3.4 (SOP Class to IOD), PS3.5 (UID encoding, UUID-derived UIDs), PS3.6 (data dictionary, well-known UIDs), PS3.10 (File Meta Information), PS3.16 (CID 7050 de-identification method codes, CID 7005 contributing equipment purpose) |
| Best practice companion | Clunie DA et al. *Report of the Medical Image De-Identification (MIDI) Task Group: Best Practices and Recommendations*, report dated 2025-02-07, [arXiv:2303.10473](https://arxiv.org/abs/2303.10473) (preprint) |
| Validation resources | NCI MIDI synthetic identifier datasets, answer keys, and validation scripts; `dciodvfy` and `dcentvfy` from dicom3tools for object validity and cross-object consistency (validity only, not privacy) |
| Governance context (documentation only) | UK ICO anonymisation guidance; GDPR Article 4(5) and Recital 26; CJEU C-413/23 P *EDPS v SRB* (4 September 2025); Privacy Act 1988 (Cth) and OAIC de-identification guidance; ISO 25237:2017 (pseudonymisation) |

The normative standard tables (rule layer L1) are generated from the pinned edition, never transcribed or edited by hand. Reviewed supplementary rules (L2) and validated user rules (L3) are maintained separately with their rationale; they are not claimed to come from the generated tables. The MIDI report's best practices are recorded as requirements alongside the standard's "shall" statements, so that every requirement can be traced to the code that implements it and the tests that check it. The browsing links above may follow the current edition; generator inputs must use the pinned publication and verified digests (D-002 and D-005).

## Why the existing tools are replaced

Both existing paths share one engine in `lib/pymedphys/_dicom/anonymise/`. Targeted hygiene fixes can reduce immediate disclosure, but profile conformance and collection-level guarantees require the planned replacement. The limitations motivating this work include:

- By default, `pymedphys.dicom.anonymise` leaves identifying UIDs such as Study, Series, SOP Instance, and Frame of Reference UIDs unchanged. It replaces reference sequences such as Referenced Image Sequence with an empty item (breaking references), writes invalid values (Patient's Sex `ANON`), never records that de-identification took place, and does not implement a PS3.15 profile. Its keyword list derives from an old edition of Table E.1-1 of about 220 rows; edition 2026d has 657.
- The experimental pseudonymisation module hashes UIDs and decimal strings without a secret, so anyone holding the original UIDs can re-link records and small-range values such as weight can be recovered by trying every plausible value. It jitters ages non-deterministically, applies one date offset to every patient on an installation, fails on non-ASCII names, maps Dose Reference UID but not Referenced Dose Reference UID (breaking the RT Plan to treatment record link), and misses most enhanced RT UIDs.
- Neither explicitly rebuilds the file preamble or File Meta Information. If present in the input, the original Media Storage SOP Instance UID and preamble can survive writing, including after pseudonymisation changes the dataset's SOP Instance UID.
- Legacy diagnostics can expose original values and paths. Progress records the application logging/output fixes and remaining exception and dependency-warning channels; a partial hygiene fix does not complete D-020.

## Architecture

The package will live in `lib/pymedphys/_dicom/deidentify/` with the public API exposed from `pymedphys.dicom`. The following is a component map, not a PR sequence. The roadmap records dependencies and delivery gates. The scope above is the target coverage; each implementation PR must state which IODs, options, and inputs it supports and reject or sequester unsupported cases without a conformance claim.

1. **Generated standard tables (rule layer L1).** Table E.1-1 with every option column, Tables E.1-1a, E.3.4-1, and E.3.10-1, CID 7050, well-known UIDs, the VR and VM of every Table E.1-1 attribute, and attribute Types for supported IODs. A development command regenerates them from the standard and records the edition, the source file digest, and a content digest.
2. **Supplementary rules (rule layer L2).** Reviewed rules, each with a rationale, for attributes the table does not list but that the de-identifier is still responsible for: dates, times, and person names by value representation; operator-entered RT text outside the table such as Beam Name and Dose Comment; RT Image machine names; and UID roles including SOP classes, transfer syntaxes, coding schemes, context groups, devices, and instance identities/references. A test fails if the dictionary contains an attribute in one of these categories with no rule. UI value representation alone does not determine the action (D-016).
3. **User rules (rule layer L3).** Options are the primary configuration. Validate both removal and retention overrides against the IOD and effective profile/options before writing. Reject invalid IOD changes; changes incompatible with the selected options require an explicitly revised policy or acknowledged nonconformant processing with no unsupported claims (D-017).
4. **UID engine.** Resolve the effective action from L1, L2, and validated L3 rules before transforming a UID. Values selected for replacement use the same keyed HMAC-SHA256 function everywhere replacement is required, including nested references, File Meta Information, and retained private elements. Format replacements as version 8 UUIDs in `2.25.` UIDs of at most 44 characters. Retain UIDs when the effective action requires retention; apply reviewed semantic rules to vocabulary and other non-instance identifiers (D-016).
5. **Keys.** A 256-bit key is either ephemeral (discarded after the run, so links hold within the run only) or a project key held by a custodian (links hold across runs, as incremental RT collections need). Derivations for UIDs, identifiers, and date offsets are domain-separated. Keys are never logged or written into outputs.
6. **Temporal handling.** Apply the Basic Profile's removal, empty-value, or dummy-value actions as required by the attribute and IOD; selected temporal options permit full retention or per-subject whole-day shifts that keep times, intervals, and optionally the weekday. Dates found inside free text are removed rather than shifted. Any synthetic birth date is a single subject-level value reused across studies and incremental runs from a custodian-controlled subject profile (D-018).
7. **Free text.** A vocabulary-based cleaner is the initial implementation choice, not a prerequisite imposed by the Clean Descriptors Option. Combine it with checks for echoes of known patient and other person identifiers, contextual handling of ambiguous words, value checks on code and numeric strings, and pooled human review of retained strings in the confidential QC pack (D-019 and D-020).
8. **Private attributes.** Removed by default. With the Retain Safe Private Option, retained only when shown to be safe by the routes E.3.10 allows, matched by private creator regardless of block, with the basis for each retained element recorded.
9. **Container.** File Meta Information and preamble rebuilt, group 0004 and trailing padding removed, encapsulated documents replaced or sequestered, and metadata inside compressed pixel data bitstreams stripped without recompression.
10. **Referential integrity.** A first pass builds a graph of instances and references and reports dangling references, frame of reference mismatches, and inconsistent hierarchy using opaque identifiers before anything is written. After writing, verify one-to-one replacement mappings, consistent links and subject-level replacements, absence of original UIDs where replacement/removal is required, and unchanged values where retention is required.
11. **Risk detection and quality control.** Risk indicators for burned-in text and potentially reconstructable faces (including RT Structure Set body contours of head and neck cases), sequestration of object types that cannot be cleaned, a confidential human review pack, and statistical disclosure control support with an explicitly selected and validated assessment model (D-020 and D-021).
12. **Reports.** A machine-readable and human-readable release report per run, a conformance statement generated from the rule tables and effective policy, and a traceability matrix from requirements to tests. Release reports exclude source values and original paths and are separate from confidential QC artifacts and custodian-controlled state (D-020).

## Planned presets

| Preset | Intended use | Intended profile and options |
| --- | --- | --- |
| `basic` (default) | Baseline attribute transformation | Basic Profile only |
| `tps-import` | Research copies that import into commercial treatment planning systems | Basic Profile, Retain Longitudinal Temporal Information with Modified Dates, Retain Patient Characteristics, Retain Device Identity, Clean Descriptors |
| `public-release` | Prepare a collection for assessment for unrestricted public sharing | Basic Profile, Retain Longitudinal Temporal Information with Modified Dates, Clean Descriptors, Retain Safe Private |

These presets are not available yet. M2 defines and tests their policy composition; M3 and M4 supply the transformation and collection-level checks required to use them. Enable a preset only when its required behaviour is implemented and validated for the documented input scope. Validate the effective rules and output before emitting any claim. Overrides cannot silently change the option set; revised policies need explicit selection and validation, and nonconformant processing cannot inherit the preset's claims (D-017).

Profile conformance and release readiness are separate results. `basic` does not authorise sharing, `tps-import` is restricted to non-clinical databases (D-018), and `public-release` additionally requires statistical assessment, pixel/face risk review, and human QC attestation (D-020 and D-021). No preset name or technical conformance claim establishes legal anonymity.

## Decision log

The entries below are the active design decisions, not statements that the code already implements them. Decision identifiers are stable and never reused. Superseded entries are preserved in the Historical decisions section below, outside the active design: D-003 is replaced by D-016, D-006 by D-018, and D-007 by D-021. When a decision changes, reconcile the architecture, presets, roadmap, contributor guidance, user documentation, and affected PR descriptions in the same change.

### D-001: One engine, called de-identification

- **Context.** The current anonymisation and pseudonymisation interfaces share legacy transformation code but expose different strategies and defects. "Anonymised" implies a legal status the software cannot establish.
- **Decision.** One engine. Re-identification capability is a property of key custody, not a different transformation. The wording rules above apply everywhere.
- **Consequences.** The legacy API names will be deprecated and removed according to D-009. This design PR does not change their runtime status. Documentation explains key custody and recipient context instead of promising anonymity.

### D-002: Rules generated from a pinned edition of the standard

- **Context.** The legacy keyword list was transcribed from an old edition and drifted. The standard is revised about five times a year.
- **Decision.** Generate normative standard tables (L1) from the pinned edition (currently 2026d). Record provenance; keep supplementary and user rules (L2 and L3) distinct. Add a monthly edition check with the generator workflow and open an issue when the generated tables would change.
- **Consequences.** Table changes arrive as reviewable generated diffs. Hand edits to generated files are never accepted.

### D-004: pydicom 3.0 as the minimum version

- **Context.** The package declares `pydicom>=2.0.0` but continuous integration only tests the locked 3.0.2. The engine needs pydicom 3 behaviour for writing File Meta Information.
- **Decision.** Raise the minimum to 3.0.
- **Consequences.** No compatibility layer for pydicom 2. Existing code that uses pydicom 3 deprecated arguments keeps working with deprecation warnings; migrating it before pydicom 4 is separate work.

### D-005: Standard library parsers for the table generator

- **Context.** The generator parses the standard's published HTML and DocBook XML. Bandit flags the standard library XML parser.
- **Decision.** Use `html.parser` and `xml.etree.ElementTree`. Verify the source file's SHA-256 before parsing, and justify each `nosec` comment as the security policy requires.
- **Consequences.** No new dependency. The parser only ever sees verified publications, in a development-only tool.

### D-008: UID root

- **Decision.** `2.25.` UIDs derived from version 8 UUIDs by default; the organisation root is opt-in. See D-016 for which values are replaced.

### D-009: Deprecation window

- **Decision.** Introduce experimental pseudonymisation deprecation warnings and a security note in M0, including its CLI and app entry points. "Immediately" means this early implementation work, not that the documentation PR has already deprecated or removed anything. Introduce warnings for `pymedphys.dicom.anonymise` and `pymedphys dicom anonymise` when usable replacements and migration guidance ship in M5. Keep these stable legacy interfaces for one full minor release with those warnings, then remove them and the experimental pseudonymisation entry points together in a subsequent minor release (M7). Here "the same release" means the common removal release, not the release that first warns about experimental pseudonymisation. Record exact versions when the implementation PRs schedule them.

### D-010: Published benchmark results

- **Decision.** Publish results against the NCI MIDI validation resources for each release of the replacement engine, as separate metrics rather than a single score, with versions and supported coverage recorded. Add tests and traceability with each implementation PR; M6 consolidates and publishes that evidence before the first supported replacement release. Intermediate documentation or hygiene releases do not claim replacement-engine results.

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

- **Decision.** The engine detects indicators of risk from burned-in text and recognisable features and reports them for review; absence of an indicator is not proof of absence. It never claims the Clean Pixel Data or Clean Recognizable Visual Features Options and never sets Burned In Annotation or Recognizable Visual Features to NO. Reporting a risk does not waive the `public-release` gates in D-021. Optical character recognition and defacing may be added later as optional plugins.

### D-015: Small pull requests with documentation

- **Context.** Maintainers review this work by hand.
- **Decision.** Each pull request has a single concern. As a sizing guide, aim for no more than about 400 lines of hand-written change, excluding tests and documentation; reviewability still matters for all files. Split work that grows beyond a digestible review. Keep generated data separate from hand-written logic where possible. Ship relevant tests and evidence, docstrings for new or changed public APIs and CLI options, user documentation for user-visible changes, a changelog entry, and an update to this document with the change. Documentation-only PRs do not need invented runtime tests or docstrings. Milestones and queue entries may split into further PRs (D-022).

### D-016: Resolve UID actions before mapping values

- **Context.** Replaces D-003. Table E.1-1 gives Device UID (0018,1002) action U in the Basic Profile but K under [Retain Device Identity](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/sect_E.3.8.html). The `tps-import` preset therefore must retain it. UID roles also extend beyond classes and instances: [Coding Scheme UID (0008,010C)](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.12.html) identifies a vocabulary, including local vocabularies absent from a well-known-UID list.
- **Decision.** Resolve the effective action from the profile, selected options, and reviewed supplementary/override rules first. Apply keyed HMAC-SHA256, formatted as a version 8 UUID under `2.25.`, only where replacement is required. The organisation root remains opt-in. Use the same replacement for all occurrences selected for replacement and their corresponding references. Retention requirements take precedence over the general mapping mechanism. Semantic identifiers need explicit rules; do not hash an unclassified UID merely because its VR is UI. Reject or sequester unsupported cases rather than silently treating them as instance identifiers.
- **Validation.** Test Device UID under both `basic` and `tps-import`, retained coding-scheme/context identifiers, consistent nested instance references and file-meta replacements, retained private UIDs, and refusal of unresolved semantic cases. Verify both replacements and required retentions after writing.

### D-017: Validate overrides and derive conformance claims

- **Context.** PS3.15 E.1.1 requires IOD integrity and retention of attributes required by selected options. Removing Patient Weight while claiming [Retain Patient Characteristics](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/sect_E.3.7.html) contradicts that option, even though removal reduces disclosure.
- **Decision.** Validate every removal, replacement, and retention override against attribute Type, VR/VM, conditional requirements, referential integrity, and the effective profile/options. Reject changes that invalidate a supported IOD. For option conflicts, require an explicitly selected, fully revalidated policy or an explicit nonconformant mode with a recorded justification; never silently drop an option. Nonconformant processing, including opt-in Private SOP Classes, receives no unsupported conformance label or method code. Derive all report wording and De-identification Method/Code Sequence content from the validated result; a mixed run cannot claim that every output conforms.
- **Validation.** Cover removal of Type 1 and Type 2 attributes, deletion of retained patient characteristics, retention forbidden by the selected profile, conditional attributes, revised option sets, nonconformant acknowledgements, and consistency between report claims and inserted metadata.

### D-018: Stable synthetic birth dates for TPS import

- **Context.** Replaces D-006. Recalculating a birth date from each study's date and rounded age can assign multiple birth dates to one subject. A project key alone does not fix a changing reference event.
- **Decision.** Keep the backwards shift of 52 to 520 whole weeks, excluding zero, conspicuously synthetic names/identifiers, and the restriction to non-clinical databases. Resolve a stable project subject identity, including the identifier's issuer or a curator-supplied identity. Before first export, designate one reference study with a validated date and age in completed years. Subtract that age in calendar years from its shifted date to obtain one synthetic birth date (map 29 February to 28 February if necessary). Persist the reference, date offset, derivation version, and chosen synthetic date in the custodian-controlled subject profile. Reuse that date for every instance and subsequent run; a later or earlier incoming study must not change the reference. The date expresses approximate age at the reference event, not the true birthday; study-specific retained Patient's Age remains the source for age analyses.
- **Failure handling.** Unresolved subject identity stops the affected objects for curator resolution. For an identified subject, missing or invalid reference dates/ages or inconsistent source ages require resolution before synthesis; otherwise emit an empty birth date consistently for that subject. Persist that empty choice too. Conflicts with an existing profile stop the subject for review rather than silently regenerating a date. Changing a previously exported choice requires an explicit migration of the related collection. Incremental export requires the saved profile as well as the project key.
- **Validation.** Test multiple studies at the same age, later birthdays, leap years, processing-order independence with the designated reference, earlier studies arriving later, missing/inconsistent ages, missing subject state, and identical birth dates across related instances and incremental runs.

### D-019: Descriptor cleaning is an implementation choice

- **Context.** [PS3.15 E.3.5](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/sect_E.3.5.html) specifies the information to remove, not one mandatory cleaning algorithm. A vocabulary can include words that are also names, such as "Hand".
- **Decision.** Start with a vocabulary-based cleaner, with context-aware checks and checks against known patient and other person identifiers. Treat unresolved ambiguous text conservatively: remove optional attributes, use permitted empty or dummy values for required attributes, or hold the affected output for confidential review, subject to D-017. A token's presence in a vocabulary is not evidence that its use is safe. Other validated cleaning methods, including removing optional descriptors, may satisfy the option; document the method and limits in the conformance statement and preserve IOD validity.
- **Validation.** Include names overlapping anatomical terms, clinician names, mixed descriptive/identifying text, non-English text, and missing source identifiers. Require human review of retained strings; do not claim that vocabulary matching alone establishes conformance.

### D-020: Confidential QC artifacts are separate from release reports

- **Context.** Human review of retained strings and image previews requires access to material that may still identify people. Routine diagnostics and distributable reports do not require that material.
- **Decision.** Logs, standard output, exceptions, and release reports contain no source attribute values, original paths, or secret keys. Use attribute paths, opaque object identifiers, rule identifiers, and aggregate results. A QC pack may contain only the retained strings, contextual excerpts, and image previews needed for review, in an explicitly designated location restricted to authorised reviewers. Treat it as potentially identifying, exclude it from release directories/archives, and document retention and deletion. Key and subject-profile stores are separate custodian-controlled state and are never included in either report. Release reports record an opaque attestation reference and outcome, not the sensitive review material.
- **Validation.** Capture logs and errors, inspect release archives for QC/state artifacts, verify explicit QC destination/access requirements, and ensure a reviewer can locate the affected output through opaque identifiers without source paths appearing in release reports.

### D-021: Bind public-release thresholds to an assessment model

- **Context.** Replaces D-007. The MIDI report discusses 0.09 and 0.05 as example thresholds in section 1.15.2.2; sections 1.15.1.1 and 1.15.1.2 distinguish group size, reference population, threat model, and maximum versus average risk. Those numbers alone do not define an estimator or a release decision.
- **Decision.** Retain 0.09 as the default acceptance threshold, with 0.05 selectable, for a documented maximum per-subject re-identification probability under an explicitly selected and validated model. Before this can be a release gate, require the assessment to name/version the model and implementation, define the assumed attacker knowledge and membership knowledge, identify the reference population and sampling assumptions (or justify assessment within the release cohort), and record matching variables, generalisation, missing-data handling, uncertainty, and exclusions. Count distinct subjects, not images, frames, or visits; account for linked longitudinal records and previously released linked data. A sample-based `1/k` calculation is permissible only with a documented known-membership/equivalence-class model, not as an estimate of population uniqueness.
- **Release gate.** Bind the assessment to the exact collection and policy versions. No selected/validated model, incomplete subject coverage, an unavailable estimate, or a failed threshold means the SDC gate is not passed; do not substitute a default score. A documented external assessment may supply the evidence while automated estimators are being developed. Any collection or policy change requires reassessment. The statistic covers only the modelled disclosure channels, so it cannot replace pixel/face risk assessment or human QC, or establish legal anonymity.
- **Human review.** Retain review of every distinct retained string, every series (by maximum intensity projection or cine strip), and every instance in high-risk categories. Potentially reconstructable facial information remains a hard block unless a risk assessment reference is recorded. A human QC attestation is required before marking a run ready for release; confidential review artifacts follow D-020.
- **Validation.** Test subject-versus-instance counts, longitudinal and prior-release linkage, missing model/assumptions/coverage, threshold boundaries, failed or stale assessments, and separation of statistical, pixel/face, and human-review gates. Select and validate the initial estimator before enabling an automated SDC gate in M4.

### D-022: Rolling plan and consistent documentation

- **Context.** A short progress list and fixed future PR ranges suggested competing programme sizes and forced unrelated work into a predetermined sequence. A late evidence milestone also obscured the requirement to ship documentation and tests with each change.
- **Decision.** Keep stable milestone and decision identifiers, but identify actual PRs by their GitHub numbers. Maintain an outcome-based roadmap, a rolling near-term queue, and a separate progress record. Neither milestone rows nor queue entries are PR-sized commitments; split them whenever necessary to satisfy D-015. Introduce dependencies when their first verified consumer needs them, not to fill an earlier numbered slot. Review shared planning at the start and end of each PR and reconcile all affected documentation and PR descriptions. Record what is planned, under review, merged, or released explicitly.
- **Consequences.** No fixed PR count or speculative PR numbering. Independent work may proceed concurrently when dependencies permit; declare stacked branches and update them after changes to their base. Tests, user guidance, requirements traceability, and conformance evidence grow with the implementation. M6 is their release-level consolidation, not permission to defer them.

## Implementation roadmap

These milestones describe outcomes and dependencies, not a fixed sequence of PRs or releases. Expect many small PRs within each milestone, and more as review exposes additional work. M0 hygiene can continue alongside the replacement; M1 to M5 describe increasing capabilities with dependencies between individual tasks. M6 evidence work runs throughout M1 to M5 and is a gate for the first supported replacement release. M7 removal also has the release-timing constraint in D-009.

| Milestone | Work to split into single-concern PRs | Dependencies and completion evidence |
| --- | --- | --- |
| M0 Hygiene | Design and current-tool guidance; explicit legacy logging/output fixes; remaining exception and warning disclosure channels; experimental deprecation warnings and security note; pydicom 3.0 minimum; GUI localhost binding and disabled usage statistics | Each change has its own regression checks and docs. Track partial fixes and residual risks explicitly; hygiene does not establish profile conformance. |
| M1 Standard | Pinned-source parsing and generator command; generated Annex E tables; dictionary, method codes, well-known UIDs, and attribute Types; requirements register and edition-check workflow | Verify source provenance and generated-table coverage. Keep generator logic and generated data reviewable separately. Start traceability with the first implemented requirement. |
| M2 Primitives | Keys and domain separation; UID mapping; VR/VM validators and dummy values; dates and subject profiles; selectors and actions; supplementary rules and validated policy/preset composition | Use the relevant M1 tables and requirements. Add Hypothesis with, or immediately before, the first property tests that use it. Validate primitives and policy conflicts before integration. |
| M3 Engine | Dataset transformation; File Meta Information and preamble; private attributes; descriptor cleaning; bitstream metadata; dataset-level API | Integrate tested M1/M2 components for explicitly supported inputs. Ship tests, API docs, and conformance evidence per component. A dataset-level API does not establish collection-level integrity or release readiness. |
| M4 Pipeline | Discovery and writing; reference graph; two-pass collection verification; sanitised reports; risk detection; restricted QC pack and attestation; statistical assessment integration; end-to-end preset validation | Requires the relevant M3 transformations. Verify graph and subject consistency, report/QC/state separation, and all preset gates. D-021 permits validated external assessment evidence; an automated estimator needs separate validation before activation. |
| M5 Interfaces and migration | CLI and Streamlit interfaces to the same engine; migration guides; stable legacy deprecation warnings | Expose only supported behaviour with the corresponding M3/M4 checks and user docs. Replacement availability is subject to M6 evidence; start the stable deprecation window only when replacements and migration guidance ship. |
| M6 Release evidence | Consolidate the how-to guide, generated conformance statement, requirements-to-tests matrix, and reproducible benchmark publication workflow | Develop these with M1 to M5. Before the first supported replacement release, publish evidence for the shipped coverage and document exclusions; refresh it for each subsequent engine release (D-010). |
| M7 Later work | Remove legacy interfaces after the deprecation window; separately consider Clean Structured Content, accompanying spreadsheets using the same key, and Encrypted Attributes Sequence for controlled sharing | Removal follows D-009. Other extensions require their own design, tests, and conformance review; generating a standard table in M1 does not enable the corresponding option. |

## Near-term queue and open questions

This is a rolling planning horizon, not a complete backlog or a promise of one PR per row. Re-scope each item before opening a PR; add its actual GitHub link to Progress once opened. Independent items may use separate branches, but parallel work is optional and must account for shared files and semantic dependencies. Use `main` for independent work once prerequisites merge; identify the base PR explicitly for stacked work.

| Next work | Status and dependency |
| --- | --- |
| Legacy application logging and progress output | Under review in #2062, based on #2061. Preserve its focused scope and capture-test coverage. |
| Remaining legacy diagnostic disclosure | Planned follow-up to #2062: scope sanitisation of re-raised exceptions and dependency warnings into reviewable changes, with compatibility decisions and capture tests. Keep these residual risks visible until addressed; D-020 is the target, not a claim that the initial fix covers all channels. |
| Experimental pseudonymisation warnings and security note | Planned M0 work under D-009. Cover library, CLI, and app guidance; removal is a later, separate change. |
| pydicom 3.0 minimum | Planned M0 dependency change under D-004, with regenerated dependency files and compatibility checks. |
| GUI localhost binding and usage statistics | Planned M0 change, with configuration tests and documentation of access defaults. |
| First standard parser and provenance checks | First M1 implementation slice; depends on the agreed pinned inputs and generator approach (D-002 and D-005), not completion of unrelated M0 hygiene. Split remaining tables and generator features into subsequent PRs. |
| Hypothesis and its first property tests | Deferred until the first M2 consumer is ready. Add it with that consumer or a directly preceding, verified prerequisite; do not land an unused dependency early. |

Open questions are tied to capabilities, not guessed future PR numbers:

- **Automated risk estimation:** select and validate the model and supported assumptions before enabling an automated M4 statistical disclosure control (SDC) gate. Until then, a public-release workflow needs a complete documented external assessment meeting D-021. Missing, failed, or stale evidence cannot pass.
- **Vocabulary licensing:** confirm the AAPM TG-263 structure-name licence before vendoring it for the M3 descriptor cleaner.
- **Benchmark licensing:** confirm the TCIA/NCI MIDI synthetic-identifier dataset and answer-key licences before vendoring or caching them for tests. Plan these checks with M1 requirements and the first benchmark tests, not only at M6 publication.
- **Release versions:** record the experimental warning release, the supported replacement/stable warning release, and the common legacy removal release when scheduled under D-009. No version or deprecation is introduced by this documentation PR.

## Historical decisions

These entries are retained verbatim for traceability. They are superseded and must not guide implementation or claims; use the replacement decision identified at the start of each entry.

### D-003: UIDs mapped by value with a keyed function

**Superseded by D-016.** The original decision below is retained for history and must not guide implementation.

- **Context.** Table E.1-1 does not list every instance UID attribute (for example Target Frame of Reference UID), so mapping only listed attributes would leak original UIDs and break references. Unkeyed hashing lets anyone with the original UIDs re-link. A shared lookup table is fragile under parallel processing and cannot be reproduced later.
- **Decision.** Replace every non-class, non-well-known UID value with HMAC-SHA256 under the run's key, formatted as a version 8 UUID in a `2.25.` UID. An organisation root under the PyMedPhys root UID is available as an option for systems that cannot handle long numeric components.
- **Consequences.** Links survive regardless of which attributes the table lists. Output is deterministic for a given key and independent of the number of worker processes. Replacement UIDs contain no timestamp.

### D-006: Treatment planning system import defaults

**Superseded by D-018.** The original decision below is retained for history and must not guide implementation.

- **Context.** Commercial planning systems may reject empty identifiers, invalid values, or future-dated plans.
- **Decision.** For `tps-import`: shift dates backwards only, by a whole number of weeks between 52 and 520, never zero, preserving the weekday. Generate conspicuously synthetic names and identifiers (for example `ZZRESEARCH^...`). Write a synthetic birth date derived from the shifted study date and the patient's age at year precision, with an option to leave it empty.
- **Consequences.** Imported research copies are recognisable as such and date intervals such as fractionation patterns are preserved. The synthetic birth date reveals no more than the retained age. The documentation requires import into non-clinical databases only.

### D-007: Public release defaults

**Superseded by D-021.** The original decision below is retained for history and must not guide implementation.

- **Context.** The MIDI report recommends a quantified risk threshold, human quality control, and caution with potentially reconstructable faces.
- **Decision.** For `public-release`: statistical disclosure control threshold 0.09 by default (0.05 selectable); human review of every distinct retained string, every series (by maximum intensity projection or cine strip), and every instance in high-risk categories; potentially reconstructable facial information is a hard block unless a risk assessment reference is recorded; a human quality control attestation is required before a run can be marked ready for release.
- **Consequences.** Public release requires deliberate human involvement, as the MIDI report and NCI evaluation results indicate it should.
