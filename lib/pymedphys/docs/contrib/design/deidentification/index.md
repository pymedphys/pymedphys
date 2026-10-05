---
myst:
  heading_anchors: 3
---

# DICOM de-identification design

This document specifies the DICOM de-identification engine that will replace `pymedphys.dicom.anonymise` and the experimental pseudonymisation module, and records the decisions behind it. So far the generated standard tables, the requirements register, and some of the primitives exist, but nothing yet de-identifies a data set; the register records what is implemented. The current tools share one engine in `lib/pymedphys/_dicom/anonymise/`, do not implement a DICOM confidentiality profile, and have the limitations listed in [DICOM de-identification](../../../users/background/dicom-deidentification.md).

Pull requests for this work are listed in the [tracking issue](https://github.com/pymedphys/pymedphys/issues/2075). A pull request that changes a decision updates this document, the user documentation, and any affected code in the same change.

## Scope

The engine de-identifies a collection of DICOM instances as a unit and preserves the references between them. The library API, the command-line interface, and the Streamlit app all call the same engine.

The target coverage is:

- **Objects:** CT, MR, PET, RT Structure Set, RT Plan, RT Dose, RT Beams Treatment Record, RT Image, spatial registration, and segmentation.
- **Profile and options:** the Basic Application Level Confidentiality Profile with the Retain Safe Private, Retain Device Identity, Retain Patient Characteristics, Retain Longitudinal Temporal Information with Modified Dates, and Clean Descriptors Options.
- **Evidence:** a generated conformance statement, a requirements register traced to tests, and published benchmark results (D-018).

The first supported release covers the Basic Profile, alone (`basic`) and with the Clean Descriptors Option (`basic-clean-descriptors`), with a run-scoped key, for uncompressed CT Image, RT Structure Set, RT Plan, and RT Dose instances, including those of CT Image Storage - For Processing (D-010). Clean Descriptors is included because, under the Basic Profile alone, RT Structure Sets would keep no usable structure names (D-009). Later releases extend it to the target coverage, each with its own evidence.

The first supported release ships the library API and the command line, which is a thin layer over the library: batch users need the command line, and the surface to validate stays small. A library alone was rejected because most users will not script it. The app comes in a later release, because `pymedphys gui` has no login and can serve its apps to other computers, so a de-identification app needs its own design for keys and QC material. Until the new app ships, the legacy pseudonymisation app stays, with its limitation banner (D-019).

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

An instance is **sequestered** when the engine does not write it to the release output, whether it is set aside before de-identification or fails a check during or after it: the run report lists it by opaque identifiers only, it is excluded from the conformance claim, and its source is left unchanged.

## Standards basis

| Role | Source |
| --- | --- |
| Normative rules | [DICOM PS3.15 Annex E](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html), edition 2026d: E.1.1 (de-identifier), E.1.3 (conformance statement), E.2 (Basic Profile), E.3 (Options), and Tables E.1-1, E.1-1a, E.3.4-1, and E.3.10-1 |
| Supporting DICOM parts | PS3.3 (attribute Types per IOD), PS3.4 (Table B.5-1, the IOD of each Storage SOP Class), PS3.5 (UID encoding, registration, and UUID-derived UIDs), PS3.6 (data dictionary and well-known UIDs), PS3.7 (Implementation Class UIDs), PS3.10 (File Meta Information), PS3.16 (Tables 8-1 and 8-2 coding schemes and their UIDs, CID 7050 de-identification methods, and CID 7005 contributing equipment purposes) |
| Best practice | Clunie DA et al., *Report of the Medical Image De-Identification (MIDI) Task Group: Best Practices and Recommendations*, 7 February 2025, [arXiv:2303.10473](https://arxiv.org/abs/2303.10473) |
| Validation | NCI MIDI synthetic-identifier datasets, answer keys, and validation script (D-018); `dciodvfy` and `dcentvfy` from dicom3tools, which check object validity, not privacy |
| Governance context (documentation only) | GDPR Article 4(5) and Recital 26; CJEU C-413/23 P *EDPS v SRB* (4 September 2025); UK ICO anonymisation guidance; Privacy Act 1988 (Cth) and OAIC de-identification guidance; ISO 25237:2017 |

Where this document relies on an informative Note in PS3.15 or on a MIDI recommendation, the choice it supports is a design decision, not a conformance requirement. Browsing links follow the current edition; the table generator uses the pinned publication (D-001).

## Read the design

Use the [specification](specification.md) for the engine's components and
presets, the [decision record](decisions.md) for the rationale and tests behind
each choice, and [requirements and evidence](requirements.md) for the register
and release claims. [Contributing to the engine](contributing.md) explains how
to update these sources together and records the milestone roadmap.

```{toctree}
:maxdepth: 1

specification
decisions
requirements
contributing
```
