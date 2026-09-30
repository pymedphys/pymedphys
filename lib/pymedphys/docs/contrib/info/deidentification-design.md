# DICOM de-identification design

This document specifies the DICOM de-identification engine that will replace `pymedphys.dicom.anonymise` and the experimental pseudonymisation module, and records the decisions behind it. So far the generated standard tables, the requirements register, and some of the primitives exist, but nothing yet de-identifies a data set; the register records what is implemented. The current tools share one engine in `lib/pymedphys/_dicom/anonymise/`, do not implement a DICOM confidentiality profile, and have the limitations listed in [DICOM de-identification](../../users/background/dicom-deidentification.md).

Pull requests for this work are listed in the [tracking issue](https://github.com/pymedphys/pymedphys/issues/2075). A pull request that changes a decision updates this document, the user documentation, and any affected code in the same change.

## Scope

The engine de-identifies a collection of DICOM instances as a unit and preserves the references between them. The library API, the command-line interface, and the Streamlit app all call the same engine.

The target coverage is:

- **Objects:** CT, MR, PET, RT Structure Set, RT Plan, RT Dose, RT Beams Treatment Record, RT Image, spatial registration, and segmentation.
- **Profile and options:** the Basic Application Level Confidentiality Profile with the Retain Safe Private, Retain Device Identity, Retain Patient Characteristics, Retain Longitudinal Temporal Information with Modified Dates, and Clean Descriptors Options.
- **Evidence:** a generated conformance statement, a requirements register traced to tests, and published benchmark results (D-018).

The first supported release covers the Basic Profile with a run-scoped key for uncompressed CT, RT Structure Set, RT Plan, and RT Dose. Later releases extend it to the target coverage, each with its own evidence.

The following are not supported. Input that needs them is rejected or sequestered, without a conformance claim:

- second-generation RT objects, RT Ion objects, and brachytherapy treatment records;
- the Clean Pixel Data and Clean Recognizable Visual Features Options (D-015), the Clean Graphics Option, and the Retain UIDs, Retain Institution Identity, and Retain Longitudinal Temporal Information with Full Dates Options;
- Structured Reports, Key Object Selection documents, Presentation States, and Private SOP Classes (D-010);
- legal determinations, since whether data are anonymous depends on the release context, not on the software.

## Terminology and claims

The engine performs **de-identification**, the term used by DICOM PS3.15 and the MIDI Task Group report. Anonymisation and pseudonymisation are not separate features: both apply the same transformation. They differ in whether anyone retains a means of re-identification, such as a project key or a crosswalk, and in which indirect identifiers the selected options keep.

Whether data are anonymous is a legal conclusion about the data in their release context (for example GDPR Recital 26), which software cannot establish. The Australian Privacy Act 1988 (Cth) s 6(1) and the HIPAA Privacy Rule (45 CFR 164.514) use "de-identified" for such a legal status.

In code, command-line output, reports, and documentation:

- Describe output only as "de-identified in accordance with the DICOM PS3.15 *edition* Basic Application Level Confidentiality Profile with *options*", and only after validating its effective policy and content against that profile and those options (D-011). Never use "de-identified" without that qualification.
- Never describe output as "anonymised".
- Where a key or crosswalk is retained, state that the data remain pseudonymised personal data for whoever holds it, and that any other recipient needs its own assessment.

An instance is **sequestered** when the engine neither de-identifies nor writes it: the run report lists it by opaque identifiers only, it is excluded from the conformance claim, and its source is left unchanged.

## Standards basis

| Role | Source |
| --- | --- |
| Normative rules | [DICOM PS3.15 Annex E](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html), edition 2026d: E.1.1 (de-identifier), E.1.3 (conformance statement), E.2 (Basic Profile), E.3 (Options), and Tables E.1-1, E.1-1a, E.3.4-1, and E.3.10-1 |
| Supporting DICOM parts | PS3.3 (attribute Types per IOD), PS3.4 (Table B.5-1, the IOD of each Storage SOP Class), PS3.5 (UID encoding and UUID-derived UIDs), PS3.6 (data dictionary and well-known UIDs), PS3.10 (File Meta Information), PS3.16 (Tables 8-1 and 8-2 coding schemes and their UIDs, CID 7050 de-identification methods, and CID 7005 contributing equipment purposes) |
| Best practice | Clunie DA et al., *Report of the Medical Image De-Identification (MIDI) Task Group: Best Practices and Recommendations*, 7 February 2025, [arXiv:2303.10473](https://arxiv.org/abs/2303.10473) |
| Validation | NCI MIDI synthetic-identifier datasets, answer keys, and validation script (D-018); `dciodvfy` and `dcentvfy` from dicom3tools, which check object validity, not privacy |
| Governance context (documentation only) | GDPR Article 4(5) and Recital 26; CJEU C-413/23 P *EDPS v SRB* (4 September 2025); UK ICO anonymisation guidance; Privacy Act 1988 (Cth) and OAIC de-identification guidance; ISO 25237:2017 |

Where this document relies on an informative Note in PS3.15 or on a MIDI recommendation, the choice it supports is a design decision, not a conformance requirement. Browsing links follow the current edition; the table generator uses the pinned publication (D-001).

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
- A new edition updates the register with the tables: add paragraphs, update changed text, and remove deleted paragraphs without reusing their identifiers.
- Normative text without "shall", such as the paragraphs after Table E.1-1a on actions for Sequences and on Options overriding the Profile, gets entries when the engine implements it.
- The traceability matrix for each release (D-018) is generated from the register.

## Architecture

The engine will live in `lib/pymedphys/_dicom/deidentify/`, with its public API in `pymedphys.dicom`. Its components are listed below; they are not a pull request sequence.

1. **Generated standard tables.** Table E.1-1 with every option column; Tables E.1-1a and E.3.10-1; the PS3.6 data dictionary (Table 6-1), with each attribute's keyword, VR, VM, and retirement; the PS3.6 Annex A registries of UIDs, well-known frames of reference, and the UIDs of context groups and templates (Tables A-1 to A-4); the PS3.16 coding schemes (Tables 8-1 and 8-2) and context groups CID 7050 and CID 7005; the PS3.4 Storage SOP Classes with the IOD of each (Table B.5-1); and, from PS3.3, the modules of each supported IOD and the attribute tables of those modules and of the macros they include, which give each attribute's Type (D-001).
2. **Rule layers.** Rules apply in this order: generated tables (L1), reviewed supplementary rules (L2), then validated user rules (L3).
   - L1 gives each attribute of Table E.1-1 the action of the selected options that give one, and otherwise the Profile's, since "a requirement for an Option, when implemented, overrides any requirement for the underlying Profile" (E.1.1). E.3.6 specifies Retain Longitudinal Temporal Information with Full Dates and with Modified Dates as mutually exclusive, so a selection of both is rejected. Otherwise PS3.15 defines no precedence between options, so an attribute to which two selected options give different actions has no L1 action and is reported as a conflict for policy validation (D-007, D-011). In 2026d, the only such options are Retain Device Identity and Modified Dates, on eleven attributes.
   - L2 covers attributes that Table E.1-1 omits but the de-identifier remains responsible for (E.1.1, Note 1 after Table E.1-1a). These are dates, times, and person names by VR; operator-entered RT text such as Beam Name, Dose Comment, and Radiation Machine Name; the role of every UI attribute (D-003); and the role of every temporal attribute (D-007). A test fails if the pinned dictionary contains an attribute in these categories with no rule.
   - L2 only strengthens L1. It never retains a value that L1 removes, replaces, or cleans, unless a selected option permits it.
   - An element with VR UN is decoded with its dictionary VR and then handled by its rule. Attributes absent from the pinned dictionary and without an L2 rule are removed. Retired attributes follow Table E.1-1 where listed and L2 otherwise.
   - Compound actions such as X/Z/D are resolved from the attribute's Type in its module and sequence context for the IOD.
   - L3 rules are validated as D-011 requires.
3. **Identifiers.** Keyed replacement of UIDs (D-003) and patient identifiers (D-005), using keys and subject profiles held by a custodian (D-004).
4. **Dates and times.** Per-subject shifts (D-006), handling of each temporal attribute by its role (D-007), and stable synthetic birth dates for `tps-import` (D-008).
5. **Free text.** Descriptor cleaning (D-009). Text is decoded according to Specific Character Set (0008,0005) before matching, cleaning, or hashing. Replacement values are encoded in the dataset's character set, and the dataset is converted to UTF-8 (ISO_IR 192) when a value cannot otherwise be encoded.
6. **Private attributes.** Removed unless the Retain Safe Private Option is selected.
   - With that option, a private attribute is retained only when shown to be safe by a route E.3.10 allows. It is matched by private creator, whichever block it occupies (MIDI §1.17.3), and the basis for retaining each element is recorded.
   - Table E.1-1 gives retained private attributes C, so their values are still cleaned: UIDs by D-003, dates by D-007, and text as descriptors (D-009).
   - Deidentification Action (0008,0307) is followed where present, as E.3.10 requires.
   - A private sequence not known to be safe is parsed and each nested attribute is handled on its own merits.
7. **File container.**
   - The engine replaces the File Meta Information and the preamble, as E.1.1 requires: it builds the File Meta Information itself, describing the de-identifying application, and writes a zeroed preamble (D-002).
   - It removes group 0004 from every file other than a DICOMDIR, and removes Data Set Trailing Padding. A source DICOMDIR is never passed through; one is written only by regenerating it from the de-identified files (E.1.1).
   - Encapsulated documents are replaced, as Table E.1-1 requires, or the instance is sequestered.
   - Metadata in compressed pixel data bitstreams, such as JPEG APPn segments, is removed without recompression.
   - Output file and directory names are built only from replacement identifiers, never from source paths, file names, or attribute values.
   - De-identification markers follow D-012.
8. **Referential integrity.**
   - A first pass builds a graph of instances and references. It reports dangling references, frame of reference mismatches, and inconsistent hierarchy using opaque identifiers, before anything is written.
   - After writing, the engine verifies one-to-one UID mappings; consistent references; consistent values for each entity above the instance level, such as Patient ID, Study ID, and Series Number (E.1.1 step 2, Note 3); absence of original UIDs where replacement or removal is required; and unchanged values where retention is required.
   - It searches each whole output file for source values that had to be removed or replaced, including the preamble, trailing padding, OB and UN values, and bitstream metadata.
9. **Risk detection and quality control.** Indicators for burned-in text and reconstructable faces (D-015), a restricted QC pack for human review (D-016), and statistical disclosure control (D-017).
10. **Reports.**
    - Each run writes a machine-readable and human-readable release report, which contains no source values or original paths (D-016).
    - Each run also writes a conformance statement generated from the rule tables and the effective policy. It covers everything E.1.3 requires, the descriptions that E.3.5, E.3.6, E.3.7, and E.3.10 require for selected options, and each interpretation recorded in this document.
    - Each release publishes a traceability matrix from requirements to tests (D-018).

## Presets

| Preset | Intended use | Profile and options |
| --- | --- | --- |
| `basic` (default) | Baseline transformation | Basic Profile |
| `tps-import` | Copies for non-clinical treatment planning system databases, such as research copies of patient data, or duplicates of phantom data that must coexist without UID conflicts | Basic Profile; Retain Longitudinal Temporal Information with Modified Dates; Retain Patient Characteristics; Retain Device Identity; Clean Descriptors |
| `public-release` | Collections being assessed for unrestricted public sharing | Basic Profile; Retain Longitudinal Temporal Information with Modified Dates; Clean Descriptors; Retain Safe Private |

- These are target option sets. A preset is enabled only once its behaviour is implemented and validated for the documented input scope. Selecting a preset is not evidence of conformance (D-011).
- `tps-import` makes no PS3.15 conformance claim, because its Retain Device Identity and Modified Dates options conflict (D-007). Its output is marked as D-012 describes.
- `tps-import` writes synthetic birth dates (D-008), and retains cleaned descriptors only after pooled human review, otherwise applying the Basic Profile's actions (D-009). Each run with a new key gives UIDs and patient pseudonyms unrelated to earlier copies, so several copies of one source, such as a phantom, can coexist in one planning system (D-003).
- `public-release` omits Retain Device Identity, because device serial numbers and machine names can identify an institution and, with dates, individual treatments.
- Profile conformance and readiness to release are reported separately. `basic` output is not thereby ready to share. `tps-import` output is for non-clinical databases only. `public-release` output also needs a statistical assessment, pixel and face review, and a human QC attestation (D-016 and D-017).

## Decisions

These are the active design decisions, not statements that the code implements them. Decision identifiers are stable and never reused.

### D-001: Tables generated from a pinned edition

- **Decision.**
  - A development command generates the L1 tables from the pinned edition of the standard, currently 2026d. It downloads the published HTML pages, verifies each page's SHA-256 against the pinned digest, and parses them with `html.parser`. Most pages are NEMA's chtml pages, one per section. PS3.3's module and macro tables span dozens of those, so PS3.3 is read from its single-page HTML, which marks up tables in the same way. It records the edition, the source digests, and a digest of the generated content. The PS3.6 data dictionary and Annex A tables, and the PS3.16 coding schemes and context groups, parse from the HTML as reliably as the Annex E tables, so no DocBook XML parser is needed.
  - The repository and the package keep the generated tables, not the standard's source files. Each generated file carries the copyright attribution `DICOM PS3.x <edition>, © NEMA`, such as "DICOM PS3.15 2026d, © NEMA".
  - A loader reads each table, checks each row's fields, types, and actions, and rejects a table whose rows no longer match the digest recorded in the file. This catches a table edited without updating that digest; it does not authenticate the file.
  - Table E.1-1a must define exactly the action codes the engine implements, so a new edition that adds or removes a code fails generation until the engine handles it.
  - PS3.3 is generated for the IODs of the first supported release: CT Image, RT Dose, RT Structure Set, and RT Plan, named by their tables in the pin, since table numbers can change between editions. For each IOD, its modules table gives each module's information entity, section, and usage, with any condition. Each module's attribute table is the one in that section titled with the module's name and "Module Attributes", such as "Patient Module Attributes". Attribute tables, and every macro table they include, are kept as published, without descriptions: each row's nesting depth, name, tag, and Type, or the macro an "Include" row adds. Generation checks every tag against the data dictionary and allows nesting only below a sequence.
  - The loader expands each IOD's modules, following every "Include", into each attribute's Type in each module and within each enclosing sequence. An attribute of a repeating group, such as Overlay Data (6002,3000), matches its group's definition, (60xx,3000). Different modules can give an attribute different Types, and an attribute the IOD does not define has none.
  - An instance names its SOP Class in SOP Class UID (0008,0016), not its IOD, so PS3.4 Table B.5-1, which gives the IOD of each Standard Storage SOP Class, is generated whole from its chtml page. The engine finds an instance's IOD, and with it the Types, from its SOP Class UID without trailing NUL and space padding, as it does before replacing a UID (D-003), since PS3.5 Section 9.1 pads a UID of odd length, such as each of the first release's SOP Class UIDs, with a NUL. Only the SOP Classes of generated IODs have Types; any other SOP Class, including one the table does not list, such as a retired or Private SOP Class, is outside the supported scope (D-010).
  - Table E.3.4-1 is not generated until the Clean Structured Content Option is designed.
  - A monthly workflow opens an issue when a new edition would change the generated tables. Generated files are never edited by hand.
- **Rationale.** The legacy keyword list was transcribed by hand and has drifted: it has 217 entries, drawn from Supplement 142, while Table E.1-1 in 2026d has 657 rows. The standard is revised about five times a year. NEMA holds the copyright in the standard, and each table records that attribution. Table E.3.4-1 also contains SNOMED CT, LOINC, NCDR, NCIt, and UMLS codes, which carry their own terms. The standard library parsers add no dependency and only ever read verified publications, in a development-only tool. PS3.3 tables are kept as published because expanding each macro in each IOD would repeat shared modules and macros: the four IODs expand to about 18,600 definitions, but their 97 tables fit in a quarter of a megabyte. Table B.5-1 is small (173 rows in 2026d), so supporting another IOD later needs only that IOD's PS3.3 tables.
- **Tests.** Regeneration reproduces the committed tables and digests; a source file with a different digest is rejected; a table whose rows differ from their recorded digest, or whose rows have the wrong fields, types, or actions, is rejected; and every generated file carries the copyright attribution. For PS3.3, merged cells are expanded; modules are found by section and title; macros are reached through nested includes; spot Types match the published tables, including different Types in different modules and sequences; and malformed nesting, missing tables, and cycles of includes are rejected. For PS3.4, every Storage SOP Class is a current SOP Class in PS3.6 Table A-1; every generated IOD is the IOD of a Storage SOP Class; and the first release's SOP Classes find their IODs, with or without padding and when read from a file, while other SOP Classes and unlisted UIDs find none.

### D-002: pydicom 3.0 minimum

- **Decision.** Require pydicom 3.0 or later, with no compatibility layer for pydicom 2.
- **Rationale.** The package declared `pydicom>=2.0.0`, but continuous integration tests only the locked 3.0.2. The engine uses `dcmwrite(..., enforce_file_format=True)`, added in pydicom 3.0. That call updates the Media Storage SOP Class and Instance UIDs but keeps other File Meta elements and any existing preamble, so the engine builds both itself.
- **Tests.** None of its own: CI runs the suite against the locked pydicom 3.

### D-003: UID replacement

- **Decision.**
  - Resolve each UID attribute's effective action from the L1, L2, and validated L3 rules before transforming its value.
  - Semantic identifiers need explicit L2 rules. SOP Class UIDs, transfer syntaxes, and well-known coding-scheme and context-group UIDs are retained. Local coding-scheme identifiers and private codes are retained only when a reviewed L2 rule classifies them as non-identifying; this is stricter than Table E.1-1, which gives C only to the Code Sequences it lists (E.1.1, Notes 7 and 10 after Table E.1-1a). A UI attribute with no rule is rejected, never hashed merely because of its VR.
  - The L2 file `uid_roles.toml` gives every UI attribute of the pinned dictionary a role. An `instance` attribute identifies an instance, event, entity, device, or organisation; every UI attribute that Table E.1-1 replaces has this role, as do instance UIDs the table omits, such as Target Frame of Reference UID (0018,991E). A `definition` attribute identifies something a standard or vendor publishes: a SOP Class, transfer syntax, coding scheme, context group, mapping resource, or template.
  - A value that the pinned tables register (PS3.6 Annex A and PS3.16 Tables 8-1 and 8-2) is retained whatever the attribute's role, because it names a public definition rather than an instance. Examples are a well-known frame of reference (PS3.6 Table A-2) and the Universal Coordinated Time synchronization frame of reference. This interprets U for such values, and the conformance statement records it. Any other value is replaced; in a `definition` attribute, where it may be a local definition under an institution's root, the replacement is also reported.
  - Where replacement is required, remove trailing NUL and space padding, then compute a 32-byte token with HMAC-SHA256 under the run's key (D-004) and a UID-specific domain label. The replacement is the name-based SHA-1 (version 5) UUID of that token in a fixed namespace defined by PyMedPhys, written as a `2.25.` UID of at most 44 characters. The namespace is the version 5 UUID of `https://docs.pymedphys.com/deidentify/uid-namespace` in the URL namespace, and never changes.
  - Use the same derivation for every occurrence, including nested references, File Meta Information, and retained private elements. The same key always gives the same replacement, within a run and across runs. A new key gives unrelated replacements, for example to import another copy of a phantom alongside earlier copies.
  - Replacement UIDs never use an organisation root.
  - Device UID (0018,1002) is replaced under the Basic Profile (U) and retained under Retain Device Identity (K).
- **Rationale.**
  - **Standards basis.** PS3.5 B.2 derives `2.25.` UIDs from UUIDs as defined by ISO/IEC 9834-8 and ITU-T X.667. X.667 defines the name-based SHA-1 UUID as version 5 (clause 14.3). Its Table 3 reserves versions 0 and 6 to 15, and a note in clause 12.2 expects any new format to use different variant bits, so the version 8 layout that RFC 9562 adds is not an X.667 UUID. X.667 does not limit names to text (Annex B), so the 32-byte token is a valid name. Using the token as the name keeps the standard version 5 construction; replacing its SHA-1 step with HMAC-SHA256 would not. A `2.25.` UID needs no registered root, whereas an organisation root can identify the institution (E.3.9 Note 2).
  - **Re-linking.** The UUID's name is a keyed token, so without the key, knowing a source UID does not reveal its replacement. Unkeyed hashes, as in the legacy pseudonymisation, and version 5 UUIDs of the source UIDs themselves both reveal it. Published SHA-1 collision attacks need inputs the attacker chooses, and without the key nobody can choose the HMAC outputs that form the names. A compromised key reveals the replacements of known source UIDs (D-004).
  - **Uniqueness.** A version 5 UUID has 122 variable bits, so the probability of any collision among $10^9$ replacement UIDs is about $10^{-19}$.
  - **State.** Replacements are computed from the key alone, so no UID map is needed: parallel workers need no coordination, output does not depend on the number of workers, and incremental export needs only the key. Random version 4 UUIDs would instead need a map equivalent to a crosswalk, protected, shared between workers, and kept for incremental export.
- **Tests.** Known-answer vectors for the derivation; version and variant bits; length at most 44 characters; a role for every UI attribute, and the instance role for every UI attribute Table E.1-1 replaces; registered values retained under either role; consistent replacements across workers, nested references, File Meta Information, retained private elements, and incremental runs; unrelated replacements under different keys; Device UID under the Basic Profile and under Retain Device Identity; retained class, coding-scheme, and context-group identifiers; rejection of unclassified UIDs; and, after writing, both replacements and required retentions.

### D-004: Keys and subject profiles

- **Decision.**
  - Keys are 256 bits from a cryptographically secure generator. An ephemeral key and its run-only state are discarded after the run, so generated values are consistent only within that run. A project key and its subject profiles are held by a custodian, so generated values stay consistent across runs, as incremental RT collections need.
  - Use a separate key for each project and recipient, with subject profiles isolated per key. Releases under one key are linkable by design. Separate keys separate only the generated values: pixel data, geometry, and retained attributes can still link releases, and each release's assessment covers them (D-017).
  - Derivations for UIDs, patient identifiers, and date offsets are domain-separated. Each is an HMAC-SHA256 under the key of the version label `pymedphys-deid/1`, the domain, and each input, every one preceded by its length, so no two domains or splits of the input share a message. A new derivation takes a new version label.
  - Each key has a non-secret identifier derived from it. Reports may record the identifier, never the key.
  - Project keys and subject profiles are stored only in custodian-controlled locations outside output and QC directories, and never in logs, reports, or the PyMedPhys user configuration. A key file is JSON (`pymedphys-deid-key/1`) holding the key and its identifier. It is created exclusively, so an existing file or symbolic link is never overwritten or followed, and with owner-only permissions where the platform enforces file modes; elsewhere writing it warns.
  - The subject profile is the single source of truth for a subject's date offset and synthetic values. They are derived at first export, persisted, and read back afterwards; a change of derivation never silently changes an exported subject.
  - A profile store is JSON (`pymedphys-deid-profiles/1`) that records its key's identifier and refuses any other key. It holds each subject under the key's `subject` derivation of the identity, never under an identifier, with the values and the derivation version that produced them. It is replaced atomically, created with owner-only permissions where the platform enforces file modes, and kept out of the configuration directory and any protected directory, like a key file. Under an ephemeral key, profiles are kept for the run only.
  - Incremental export needs both the key and the subject profile. Recipients receive neither.
  - Rotating a key starts a new domain of generated values. If a key or profile is lost, earlier exports cannot be extended consistently. A compromised key is treated as disclosure of the crosswalk, and affected releases are reassessed.
- **Rationale.** Medical record numbers and similar identifiers have little entropy, so anyone holding the key can enumerate candidates and re-identify every subject: a project key is equivalent to a crosswalk. Profiles shared between keys would give every recipient the same shifted dates and synthetic values.
- **Tests.** Key-file creation and permissions; refusal to write keys or profiles into output, QC, or configuration locations; stable key identifiers; offsets read from an existing profile after a derivation change; profiles isolated per key; consistent generated values across incremental releases; and a demonstration that a key enumerates low-entropy identifiers.

### D-005: Keyed patient pseudonyms

- **Decision.** Every preset replaces Patient ID and Patient's Name with values derived from the subject's identity (identifier and issuer, or a curator-supplied identity) under the key (D-004), rather than with empty values. One format serves every preset. It is conspicuously synthetic, deterministic under the key, valid for the VR (64 characters for LO and for each PN component group), identical for every instance of a subject, and does not embed the source identifier. The conformance statement describes it, as E.1.3 requires for dummy values.
- **Format.** The subject's code is the base32 form (RFC 4648) of the first 80 bits of the key's `patient` derivation of the identity. Patient ID becomes `DEID-` and the code (21 characters), and Patient's Name becomes `DEIDENTIFIED^` and the code. An identity is either a Patient ID with its issuer, ignoring LO padding, or a curated subject identifier; the two kinds are framed differently, so the same text in each is two subjects. An empty Patient ID names no subject and needs a curated identity. Among a million subjects the chance that any two share a code is below $10^{-12}$.
- **Rationale.** Patient's Name is Z and Patient ID is Z/D in the Basic Profile, both of which permit a dummy value. Empty values would merge every patient in a multi-patient collection, whereas keyed pseudonyms keep subjects separate and, under a project key, consistent across runs. Conspicuous values stop a research copy from being mistaken for a clinical record.
- **Tests.** Determinism under one key and difference across keys; VR validity; distinct pseudonyms for distinct subjects, including the same identifier from different issuers; and consistency across a subject's instances.

### D-006: Date shifting

- **Decision.** Where Retain Longitudinal Temporal Information with Modified Dates is selected, shift each subject's subject-event and radiation-source dates (D-007) backwards by a whole number of weeks between 52 and 520, never zero. With a project key, the offset is read from the subject profile (D-004); with an ephemeral key, it is derived for the run. Times are unchanged. Dates found in free text are removed, not shifted. Without the option, the Basic Profile's actions apply.
- **Derivation.** A new subject's offset is 52 weeks plus the first 64 bits of the key's `date-offset` derivation of the identity, modulo 469, so each of the 469 offsets is equally likely to within one part in $10^{16}$. A DA value moves by the offset; a DT value moves its date and keeps its time, and any UTC offset it carries becomes the nominal offset once the value is in the instance's local time (D-007). A DT value without a full date, such as a year alone, cannot move by whole weeks, so it is not shifted and the engine decides what to write. A DT value at a leap second, with a second of 60, is neither shifted nor converted to local time, because PS3.5 allows 60 only at a real leap second, which the moved value would not be; its instance is sequestered.
- **Rationale.** Whole weeks preserve intervals, times of day, and weekdays, which fractionation analyses need. Shifting backwards avoids future-dated plans, which planning systems may reject. Excluding zero ensures every date moves (MIDI §1.17.9). Shifting a free-text string wrongly recognised as a date can disclose the offset (MIDI §1.17.9).
- **Tests.** Offset range and exclusion of zero; preservation of intervals, times, and weekdays; rejection of leap seconds; consistency across the studies and runs of one subject; and removal of dates in free text.

### D-007: Temporal attributes by role

- **Decision.** L2 gives every date, time, and datetime attribute a role. Where Modified Dates is selected, each role is handled as follows:
  - **Subject event**, such as Study Date, Treatment Date, and Beam Hold Transition DateTime (300C,0127): shifted by the subject's offset (D-006).
  - **Radiation source**, Source Strength Reference Date (300A,022C) and Time (300A,022E): shifted by the same offset, so that decay intervals to treatment remain correct.
  - **Device**, such as the calibration, installation, and manufacture attributes listed below; **vocabulary version**, published or local, such as Context Group Version (0008,0106) and Context Group Local Version (0008,0107); and **other**: replaced with a fixed, conspicuous dummy value that differs from the original.
  - **Time zone**, Timezone Offset From UTC (0008,0201): replaced with the nominal offset `+0000`, after every DT value in the instance that carries its own offset is converted to the instance's local time and given the same nominal offset. The instance's dates and times are then all local times under one offset, so their intervals are kept, including across midnight, and no offset reveals the season of the original date through daylight saving, such as +1100 rather than +1000, or the location. The local time is the instance's Timezone Offset From UTC where present, which PS3.3 C.12.1.1.8 makes the offset of every value without its own, and otherwise the offset of its earliest DT value that has one, compared to the microsecond. The replacement is a valid offset for the instance's times, as C requires, and the conformance statement records that it is nominal. Intervals between instances at different offsets, such as either side of a daylight-saving change, move by the difference between their offsets. An instance with a value whose precision cannot express its conversion exactly, such as a date alone, is sequestered.

  Without Modified Dates, Table E.1-1 applies unchanged. The conformance statement describes these modifications, as E.3.6 requires.

  The L2 file `temporal_roles.toml` gives each DA, DT, and TM attribute of the pinned dictionary a role, including attributes that Table E.1-1 omits, such as DICONDE and DICOS attributes. It also gives a role to every attribute of another VR that Table E.1-1 cleans under Modified Dates, so a new edition that cleans another fails to load until that attribute has a reviewed rule. In 2026d it has 187 rules: 152 subject event, 2 radiation source, 12 device, 4 vocabulary version, 1 time zone, and 16 other. An attribute that PS3.3 requires to follow a subject event, such as Item Inventory DateTime (0008,0404), which must be at or after Content Date (0008,0023), is itself a subject event, so shifting keeps the order. The UI and temporal roles files share one format and loader.

  Besides Timezone Offset From UTC, Table E.1-1 cleans two attributes of other VRs under Modified Dates. Frame Origin Timestamp (0034,0007), each frame's capture time as an IEEE 1588 timestamp in TAI (PS3.3 C.7.6.27.1.1), is a subject event; its seconds move by the subject's offset, which keeps the timing between frames exactly. Certified Timestamp (0400,0310) occurs only inside the Digital Signatures Sequence (FFFA,FFFA), which Table E.1-1 removes under every option, so its role, other, never applies.

  In 2026d, eleven attributes are K under Retain Device Identity and C under Modified Dates. Ten are device attributes: Date of Last Calibration (0018,1200), Time of Last Calibration (0018,1201), DateTime of Last Calibration (0018,1202), Calibration DateTime (0018,1203), Date of Manufacture (0018,1204), Date of Installation (0018,1205), Calibration Time (0014,407C), Calibration Date (0014,407E), Date of Last Detector Calibration (0018,700C), and Time of Last Detector Calibration (0018,700E). The eleventh is Beam Hold Transition DateTime. K keeps a non-Sequence value unchanged (Table E.1-1a) and E.3.8 requires retention, whereas E.3.6 requires modification, and PS3.15 defines no precedence between options. No output can satisfy both options while one of these attributes has a value, so a policy that selects both makes no conformance claim. `tps-import` does this deliberately and handles these attributes by role, as above; any other such policy is rejected (D-011). A test fails if a regenerated Table E.1-1 adds a conflict.
- **Rationale.** E.3.6 requires every date and time in a Table E.1-1 attribute to be modified, in a manner that reduces the possibility of matching and preserves temporal relationships only to the extent the application needs. Neither removal nor retention is modification. Shifting a device or vocabulary date by the subject's offset would disclose that offset whenever the original is known or guessable, such as a published version date or a known calibration date; MIDI §1.17.9 describes the same mechanism for free text. It would also give one device different dates in different subjects' output, revealing the differences between their offsets. No preset needs these dates' relationships to the images, so a fixed dummy value satisfies E.3.6 and C (a value of similar meaning that contains no identifying information) and discloses nothing.
- **Consequences.** Dose and decay calculations stay consistent; device calibration history and vocabulary versions are lost. The first supported release, which uses the Basic Profile only, is unaffected. Under `tps-import`, Retain Device Identity keeps Source Serial Number (3008,0105), so subjects treated with the same source can be linked and the differences between their offsets disclosed; this residual risk is documented for non-clinical use. `public-release` does not retain source serial numbers.
- **Tests.** Every temporal attribute in the pinned dictionary has a role; every value in a Table E.1-1 attribute is modified, including one equal to the dummy value; known device and vocabulary dates alongside shifted subject dates do not expose the offset; source-to-treatment intervals are preserved; a custom policy selecting both conflicting options is rejected; and a regenerated Table E.1-1 with a new option conflict fails the tests.

### D-008: Synthetic birth dates for TPS import

- **Decision.**
  - Resolve a stable subject identity, as D-005 does.
  - Before first export, designate one reference study with a validated date and an age in completed years. The synthetic birth date is that study's shifted date minus the age in calendar years, with 29 February mapped to 28 February.
  - Persist the reference, offset, derivation version, and chosen date in the subject profile (D-004; run-only under an ephemeral key), and reuse the date for every instance and later run. A study that arrives later, whatever its date, never changes the reference.
- **Failure handling.** Unresolved subject identity stops the affected objects for curator resolution. For an identified subject, missing or invalid reference dates or ages, or inconsistent source ages, must be resolved before synthesis. Otherwise an empty birth date is written consistently for that subject, and that choice is persisted too. A conflict with an existing profile stops the subject for review. Changing an exported choice requires an explicit migration of the related collection.
- **Rationale.** Patient's Birth Date is Z in the Basic Profile, and no option retains or cleans it, so a synthetic value is a permitted dummy value. Planning systems may reject records with empty or invalid values. Recomputing the date from each study's date and rounded age could give one subject several birth dates. The synthetic date expresses approximate age at the reference study, not the true birthday; the retained Patient's Age remains the source for age analyses.
- **Tests.** Several studies at one age; birthdays between studies; leap years; independence from processing order; earlier studies arriving later; missing or inconsistent ages; missing subject state; and identical birth dates across a subject's instances and incremental runs.

### D-009: Descriptor cleaning

- **Decision.**
  - Start with a vocabulary-based cleaner, combined with context-aware checks and checks for echoes of known patient and other person identifiers, including reordered names and reformatted dates (MIDI §1.17.2).
  - Treat unresolved ambiguous text conservatively, subject to D-011. Remove optional attributes, use permitted empty or dummy values for required ones, or hold the output for confidential review.
  - Other validated methods, including removing optional descriptors, may satisfy the option. Describe the method and its limits in the conformance statement, as E.3.5 requires.
  - Claim Clean Descriptors (DCM 113105) only for output whose retained descriptor strings have passed pooled human review; otherwise apply the Basic Profile's actions and do not claim the option.
  - The user supplies the vocabulary; PyMedPhys bundles none. A vocabulary is a UTF-8 JSON file that holds its entries together with their source, version, source-file SHA-256, and required attribution. A converter command produces it from the AAPM TG-263 spreadsheet or an institutional list, and converted files are never edited by hand. Without a vocabulary, descriptors receive the Basic Profile's actions.
  - `pymedphys._nomenclature.tg263` converts the TG-263 spreadsheet. It reads the user's copy, maps its columns by header text, and writes JSON with the spreadsheet's file name, worksheet version, SHA-256, AAPM's attribution, and a digest of its entries; its loader rejects a file whose entries no longer match that digest. Entries are kept as published, except that surrounding whitespace is removed, the derived "N Characters" column is dropped, and unlabelled columns are ignored. The module sits outside the de-identification package so that other tools, such as a check of structure names against TG-263, can use it.
- **Rationale.** E.3.5 specifies what to remove, not an algorithm (Note 4). A vocabulary can contain words that are also names, such as "Hand" (MIDI §1.17.2), so a token's presence in a vocabulary is not evidence that its use is safe. JSON keeps the provenance, attribution, and value types in the same file as the entries, which CSV cannot, and matches the repository's existing data files. The TG-263 journal article is licensed CC BY-NC-ND 4.0, which forbids the commercial use and adaptation that Apache-2.0 permits, and no licence compatible with Apache-2.0 has been found for its nomenclature spreadsheet, so, under the packaging rule for bundled data in `AGENTS.md`, PyMedPhys reads the user's copy rather than bundling one. AAPM publishes the spreadsheet in the Excel 97-2003 format, which `xlrd` reads.
- **Tests.** Names that overlap anatomical terms; clinician names; mixed descriptive and identifying text; non-English text; missing source identifiers; converting the AAPM spreadsheet and an institutional list; rejecting a vocabulary without its source record; and processing without one. Vocabulary matching alone never produces a claim.

### D-010: Unsupported object types

- **Decision.** Sequester Structured Reports (including dose reports), Key Object Selection documents, Presentation States, instances of Private SOP Classes, and objects outside the supported scope. List them in the report and exclude them from the conformance claim.
- **Rationale.** The Basic Profile gives Content Sequence D, and E.3.4 Note 2 warns of significant risk in de-identifying Structured Reports without the Clean Structured Content Option. Presentation States can carry graphic and text annotations (MIDI §1.22.3). De-identification of Private SOP Classes is not defined (E.1.1, Note 6 after Table E.1-1a).
- **Tests.** Each type is sequestered and reported, and never written to the release output.

### D-011: Validated overrides and derived claims

- **Decision.**
  - Validate the effective policy across L1, L2, and L3 before processing. Reject unresolved conflicts between selected options; a documented deviation never authorises a conformance claim.
  - Validate every L3 removal, replacement, and retention against attribute Type, VR and VM, conditional requirements, referential integrity, and the effective profile and options. Reject a change that invalidates a supported IOD.
  - Check every value the engine writes, whether a replacement, a dummy value, or an L3 value, against its VR's definition in PS3.5 Table 6.2-1 and its attribute's VM in the pinned dictionary before writing it. A text value is checked as the engine sets it, before encoding adds a padding byte. Where PS3.6 gives an attribute alternative VRs, such as "US or SS" or "OB or OW", the value is checked against the VR that applies in the data set, as the standard determines it from other attributes and the transfer syntax: for example Pixel Representation (0028,0103) decides US or SS for Pixel Padding Value (PS3.3 C.7.5.1), and Bits Allocated (0028,0100) and the transfer syntax determine which of OB and OW Pixel Data may have (PS3.5 Annex A). The checks of a value on its own accept any alternative it fits. As a text value is written, the engine also checks that the data set's Specific Character Set can encode it, and that the first component group of a Person Name uses only the characters PS3.5 Section 6.2.1.2 allows there. What is wrong is reported without quoting the value.
  - A change incompatible with a selected option requires an explicitly revised policy that is revalidated in full; an option is never dropped silently.
  - Derive all report wording and De-identification Method and Code Sequence content from each instance's validated result. A run with mixed results cannot claim that every output conforms.
  - `tps-import` is the only policy that produces nonconformant output, marked as D-012 describes. Any other policy that cannot conform, such as one retaining attributes its options do not keep, is rejected, and instances of Private SOP Classes are sequestered (D-010).
- **Rationale.** E.1.1 requires that each attribute specified to be retained "shall be retained", and an option's requirements override the Profile's. Removing Patient's Weight therefore contradicts Retain Patient Characteristics, even though removal discloses less. Maintaining IOD integrity is the de-identifier's responsibility (E.1.1 step 2, Note 1).
- **Tests.** Removal of Type 1 and Type 2 attributes; removal of retained patient characteristics; retention the profile forbids; conditional attributes; revised option sets; and agreement between report claims and inserted markers.

### D-012: De-identification markers

- **Decision.** Markers are derived from each instance's validated result (D-011).
  - For conformant output, set Patient Identity Removed (0012,0062) to YES; add the CID 7050 codes for the profile and each satisfied option to De-identification Method Code Sequence (0012,0064), keeping existing items; and add a value naming the tool, its version, the PS3.15 edition, and the policy digest to De-identification Method (0012,0063), keeping existing values.
  - For `tps-import` output, which makes no conformance claim (D-007), set Patient Identity Removed to YES; add no CID 7050 codes, keeping existing items; and add a De-identification Method value naming the tool, its version, and the policy, and stating that no PS3.15 conformance is claimed.
  - For both, set Longitudinal Temporal Information Modified (0028,0303) to REMOVED, or to MODIFIED where Modified Dates is applied, and add a Contributing Equipment Sequence (0018,A001) item whose purpose of reference is DCM 109104 (De-identifying Equipment, CID 7005).
  - Never set Patient Identity Removed to NO. Nonconformant output carries YES only when every deviation from the selected profile and options removes or modifies more than they require, as `tps-import`'s modification of device dates does.
- **Rationale.** E.1.1, E.2, and E.3.6 require these markers in their text, not in Table E.1-1, so the table generator does not produce them. E.1.1 says codes and text are "added to" these attributes, so earlier markers are kept. The CID 7050 codes carry the profile claim, so output without them claims none. PS3.3 notes that De-identification Method may describe the extent of de-identification, for example a HIPAA Limited Data Set, so YES with a descriptive value is an established way to record de-identification that stops short of a profile. NO would be false for `tps-import`, whose patient identity is removed, and E.1.2 has a re-identifier set NO while removing the method attributes. MIDI §1.14.3 recommends recording the de-identifying equipment in Contributing Equipment Sequence.
- **Tests.** Markers for each preset, including `tps-import`, and for input that already carries markers; values within their VR limits; `tps-import` output without new CID 7050 codes; no output with Patient Identity Removed set to NO; and agreement between markers and report claims.

### D-013: No Encrypted Attributes Sequence

- **Decision.** The engine does not write the Encrypted Attributes Sequence and stores no recovery or consistency data in its output. Consistency comes from custodian-held keys and subject profiles outside the output (D-004). If the sequence is added later, it is for controlled sharing only and is never enabled by `public-release`. The conformance statement records this interpretation.
- **Rationale.** E.1.1 step 1, Note 3, deprecates other mechanisms in the data for identity recovery or longitudinal consistency "in favor of the Encrypted Attributes Data Set mechanism". MIDI §1.17.11 calls encrypting original values into de-identified images "generally inadvisable", especially for publicly released data.
- **Tests.** No output contains an Encrypted Attributes Sequence or other recovery data.

### D-014: No preset named after a regulation

- **Decision.** No preset carries a regulatory name. The documentation maps DICOM profile behaviour to regulatory frameworks without claiming compliance.
- **Rationale.** The HIPAA Safe Harbor method is not a DICOM profile. It permits dates reduced to a year, which a DA value cannot hold, and its "comparable images" provision is open to interpretation for head imaging (MIDI §1.18.3.3).

### D-015: Pixel data: detect and warn

- **Decision.**
  - Detect and report indicators of risk for review: burned-in text; reconstructable faces, including RT Structure Set contours of the head (MIDI §1.20.4); and PET series from which body weight can be recovered, such as SUV-scaled series released with attenuation-corrected images (MIDI §1.20.2). The absence of an indicator is not proof of absence.
  - Never claim the Clean Pixel Data or Clean Recognizable Visual Features Options.
  - Keep Burned In Annotation (0028,0301) and Recognizable Visual Features (0028,0302) as received, since the pixel data are unchanged. Never change either to NO, and do not treat a received NO as evidence of safety.
  - A reported risk does not waive the `public-release` gates (D-017). Optical character recognition and defacing may later be added as optional plugins.
- **Rationale.** PS3.15 sets these attributes to NO only as part of the Clean Pixel Data and Clean Recognizable Visual Features Options (E.3.1 and E.3.2), which the engine does not implement. Neither attribute is in Table E.1-1, so L2 needs an explicit rule.
- **Tests.** Received values pass through unchanged, no output changes either attribute to NO, and detection results appear in the report.

### D-016: Confidential QC separate from release reports

- **Decision.**
  - Logs, standard output and standard error, warnings, exception messages, output file and directory names, and release reports contain no source attribute values, original paths, or keys. They use attribute paths, opaque object identifiers, rule identifiers, and aggregate results.
  - A QC pack contains only the retained strings, contextual excerpts, and image previews needed for review. It is written to an explicitly designated location restricted to authorised reviewers, treated as potentially identifying, excluded from release directories and archives, and has documented retention and deletion.
  - Key and subject-profile stores are separate custodian-controlled state and are included in neither.
  - Release reports record an opaque attestation reference and outcome, not the review material.
- **Rationale.** Human review needs material that may still identify people; routine diagnostics and distributable reports do not.
- **Tests.** Captured logs and errors contain no source values or paths; release archives contain no QC or state artefacts; the QC destination and access requirements are enforced; and a reviewer can locate affected output from opaque identifiers.

### D-017: Public-release risk assessment

- **Decision.** A `public-release` run is marked ready for release only when three gates pass: statistical disclosure control, pixel and face review, and a human QC attestation.
  - **Statistical gate.** Accept a maximum per-subject re-identification probability of 0.09 by default, or 0.05 when selected, under an explicitly selected and validated model.
    - The assessment names and versions the model and its implementation. It defines the attacker's assumed knowledge, including knowledge of membership, and identifies the reference population and sampling assumptions, or justifies assessment within the release cohort. It records matching variables, generalisation, missing-data handling, uncertainty, and exclusions.
    - It counts distinct subjects, not images, frames, or visits, and accounts for linked longitudinal records and earlier linked releases. A sample-based `1/k` calculation is permissible only with a documented known-membership or equivalence-class model.
    - The assessment is bound to the exact collection and policy versions, and any change requires reassessment. A missing model, incomplete subject coverage, an unavailable estimate, or a failed threshold fails the gate; no default score substitutes.
    - A documented external assessment may supply the evidence. An automated estimator is enabled only after it has been selected and validated.
  - **Human review.** Review every distinct retained string, every series (by maximum intensity projection or cine strip), and every instance in high-risk categories. Potentially reconstructable facial information blocks release unless a risk assessment reference is recorded. Review material follows D-016.
- **Rationale.** MIDI §1.15.2.2 describes 0.09 as a common choice and 0.05 for more sensitive collections. Sections 1.15.1.1 and 1.15.1.2 show that such a number is meaningful only with a group size, reference population, threat model, and choice of maximum or average risk, and that public releases are assessed on maximum risk with attack assumed certain. The statistic covers only the modelled disclosure channels, so it cannot replace pixel review or human QC, or establish legal anonymity.
- **Tests.** Subject versus instance counts; longitudinal and prior-release linkage; missing model, assumptions, or coverage; threshold boundaries; failed or stale assessments; and independence of the three gates.

### D-018: Published benchmark results

- **Decision.**
  - For each release of the engine, publish results against the NCI MIDI validation resources as separate metrics rather than a single score, recording versions and supported coverage. Each implementation pull request adds its own tests and traceability, and M6 consolidates the evidence for the first supported release. Releases that change only documentation or legacy code claim no engine results.
  - Use the MIDI-B collection, with its synthetic and curated datasets, answer keys, and mapping files ([doi:10.7937/cf2p-aw56](https://doi.org/10.7937/cf2p-aw56)), and the Pseudo-PHI-DICOM-Data collection ([doi:10.7937/s17z-r072](https://doi.org/10.7937/s17z-r072)), both licensed CC BY 4.0, with the [NCI validation script](https://github.com/CBIIT/midi_validation_script) (Apache-2.0).
  - Benchmark runs download the collections. Tests may use small subsets cached through the PyMedPhys Zenodo data store, with attribution, the licence, and a note of changes. The validation script's repository is not copied into PyMedPhys, because it also bundles third-party executables.
  - Report results per answer-key category, and document each category where PyMedPhys's policy deliberately differs from the answer key.
- **Rationale.** Separate, versioned metrics let users judge performance for their own data and coverage. The validation manual states that many answers follow TCIA's original curation of each source collection rather than strict DICOM requirements, so an aggregate score would penalise deliberate, conformant differences. CC BY 4.0 permits redistribution with attribution, and the collections are too large to keep in the repository.
- **Tests.** The benchmark workflow reproduces the published results, and cached subsets carry their attribution.

### D-019: No deprecation before a released replacement

- **Decision.**
  - Disclose the legacy tools' limitations now with warnings that are not deprecations and promise no removal. For experimental pseudonymisation, these are a `UserWarning` subclass in the library, a standard-error notice on the command line, and a banner in the app. For `pymedphys.dicom.anonymise`, they are corrected documentation and docstrings, a `UserWarning` subclass from the library function, and a standard-error notice on the command line.
  - Deprecate a legacy interface (library, command line, or app) only once a released replacement covers its use and migration guidance is published, which is no earlier than the first supported release (M6).
  - Keep each legacy interface for at least one full minor release with deprecation warnings, then remove both in the same release. Record exact versions in the release notes when they are scheduled.
  - Until removal, change the legacy tools only to stop them disclosing identifying information or to prevent harm to data, such as silently altering or losing source files. List other defects among the limitations in the user guidance instead of fixing them.
- **Rationale.** Deprecating before a replacement exists would leave users nowhere to go and, if the work stalled, would make the warning permanent noise. If the replacement is not delivered, both legacy interfaces remain available with their documented limitations. Other fixes to the legacy tools are spent on code with a limited life, and can change behaviour that users rely on, as a new pseudonym format would; disclosure and data-safety fixes protect people and data until the replacement is available, which justifies that cost.
- **Tests.** Limitation warnings are not `DeprecationWarning`s and mention no removal; each public call warns once; and the command-line and app notices appear. Once deprecation starts, the deprecation warnings are tested and the migration guide is published.

## Roadmap

Milestones group outcomes; they are not a sequence of pull requests or releases. Each pull request ships its own tests, documentation, and traceability, and M6 consolidates the evidence. The first supported release needs only the parts of M1 to M5 that its scope uses.

| Milestone | Outcomes | Done when |
| --- | --- | --- |
| M0 Legacy hygiene | Diagnostics free of identifying values and paths; limitation warnings and notices (D-019); pydicom 3.0 minimum (D-002) | Each change has regression tests and documentation, and remaining disclosure channels are listed in the tracking issue. Hygiene does not make the legacy tools conform. |
| M1 Standard | Table generator and generated tables (D-001); requirements register; edition-check workflow | Source provenance and table coverage are verified, and the generator and generated data are reviewed separately. |
| M2 Primitives | Keys and subject profiles; UID replacement; patient pseudonyms; date offsets; VR and VM validators and dummy values; rule layers and preset composition | Primitives and policy conflicts are validated before integration. Hypothesis is added with the first property tests that use it. |
| M3 Engine | Dataset transformation; file container; private attributes; descriptor cleaning; bitstream metadata; dataset-level API | Each component has tests, API documentation, and conformance evidence for explicitly supported input. A dataset-level API does not establish collection integrity or readiness to release. |
| M4 Pipeline | Discovery and writing; reference graph and two-pass verification; reports; risk detection; QC pack and attestation; statistical assessment; end-to-end preset validation | Graph and subject consistency, the separation of reports, QC material, and state, and every preset gate are verified. |
| M5 Interfaces and migration | CLI and app using the same engine; migration guides; deprecation warnings when D-019 allows | Only supported behaviour is exposed, with user documentation. |
| M6 First supported release | How-to guide, generated conformance statement, requirements-to-tests matrix, and benchmark results (D-018) for the release scope | Evidence is published for the shipped coverage and exclusions are documented; the evidence is refreshed for each later release. |
| M7 Legacy removal | Removal of both legacy interfaces | The deprecation window in D-019 has passed. |

Later work needs its own design, tests, and conformance review: Clean Structured Content, accompanying spreadsheets pseudonymised with the same key, the Encrypted Attributes Sequence for controlled sharing (D-013), and the unsupported objects and options listed under Scope. Generating a table in M1 does not enable the corresponding option.
