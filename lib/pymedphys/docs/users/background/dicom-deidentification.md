# DICOM de-identification

This page explains the terms PyMedPhys uses when it removes identifying information from DICOM data, what software can and cannot claim, and the known limitations of the tools currently in PyMedPhys. A replacement de-identification engine is planned but is not available yet; its active decisions, implementation progress, and rolling plan are recorded in the [de-identification design document](../../contrib/info/deidentification-design.md). That work will be delivered through many small pull requests, with documentation and evidence accompanying each implemented capability.

## Terms

**De-identification** is the removal or replacement of information that could identify a person. It is the term used by the DICOM standard in [PS3.15 Annex E](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html) and by the [Medical Image De-Identification (MIDI) Task Group report](https://arxiv.org/abs/2303.10473). PyMedPhys uses this term for what its tools do.

**Pseudonymisation** is the replacement of direct identifiers, such as a patient's name and medical record number, with pseudonyms, so that records about the same person can still be linked to each other. It is one part of de-identification, not an alternative to it.

**Anonymisation** usually implies that nobody can reasonably re-identify the person. Whether that is true depends on the data *and* its release context: who receives it, what else they know or can obtain, and whether anyone holds a means of re-identification. It is a legal and contextual conclusion, for example under GDPR Recital 26, the Australian Privacy Act 1988 (Cth), or the UK Information Commissioner's Office guidance. No software can establish it on its own, so PyMedPhys does not describe its output as anonymised.

A few further terms, following the MIDI report:

- A **direct identifier** can identify a person on its own, for example a name, medical record number, or address.
- An **indirect identifier** (or quasi-identifier) can identify a person in combination with other knowledge, for example age, sex, weight, dates, or the treating institution.
- A **sensitive attribute** is information whose disclosure could harm the person even without identifying them, for example a diagnosis.

## Anonymisation and pseudonymisation use the same process

Removing identifiers and replacing them with consistent pseudonyms is the same transformation whether the result is called anonymised or pseudonymised. Two things differ:

1. **Whether a means of re-identification is kept.** If a key or a table mapping pseudonyms back to real identities is retained, whoever holds it can re-identify the data. For them, the data remain pseudonymised personal data. For a recipient without that key, the status needs its own assessment.
2. **Which indirect identifiers are kept.** Dates, ages, weights, device and institution names, and free-text descriptions can all help re-identify someone. Keeping them is sometimes essential, for example patient weight for PET standardised uptake values, or treatment dates for fractionation analysis. Each retained item adds risk that should be assessed for the particular collection.

## What software can claim

The DICOM standard defines a Basic Application Level Confidentiality Profile and a set of Options that remove, replace, clean, or retain specific attributes. The replacement engine will claim that its output is *de-identified in accordance with* a named edition of that profile with named options only when its effective rules and output satisfy those requirements. Selecting a preset alone is not evidence of conformance. Custom removals as well as retentions can invalidate an object or contradict an option. Unsupported processing, including opt-in processing of Private SOP Classes, will be labelled as outside the conformance claim.

Even full conformance does not guarantee that nobody can be identified:

- identifying text can be burned into the image pixels, which the Basic Profile does not address (PS3.15 E.3);
- the standard notes that it has been suggested that a 3D rendering of high-resolution head and neck imaging may be enough to identify a person (PS3.15 E.3.2), and the MIDI report notes that some parts of some RT Structure Set contours, such as the body outline of a head and neck case, pose a similar risk;
- the standard notes that anyone with access to the original images can match the pixel data, whatever happens to the identifiers (PS3.15 E.1).

Deciding whether a collection can be shared, and with whom, therefore also needs a risk assessment for that collection and its intended recipients.

The planned public-release workflow also requires human quality control and a documented statistical risk assessment. A numerical threshold is meaningful only with its named model, assumptions, and subject-level unit of analysis; it is not an overall guarantee of anonymity. Confidential review packs may contain identifying strings or image previews missed by automated cleaning. They must remain in the restricted review environment and must not be included with released data or ordinary reports.

The planned `basic`, `tps-import`, and `public-release` presets are designs, not current interfaces. Profile conformance and readiness to share a collection will be reported separately. `tps-import` will be for non-clinical databases only, and `public-release` will require the assessment and review gates above; its name will not mean that sharing is automatically approved.

## Limitations of the current PyMedPhys tools

The tools currently in PyMedPhys do not implement the DICOM profile. Until the replacement engine is available, be aware of the following:

- By default, `pymedphys.dicom.anonymise` and the `pymedphys dicom anonymise` command leave identifying UIDs such as Study, Series, SOP Instance, and Frame of Reference UIDs unchanged. UIDs can often be traced back to the original records by anyone with access to the source systems. Its default output file names contain the original SOP Instance UID. Its keyword list predates most RT coverage in the current standard, so RT dates (for example RT Plan, Structure Set, and treatment dates), plan and structure set labels, ROI names, beam names and descriptions, dose comments, and treatment machine names pass through unchanged. The tool also replaces some reference sequences with empty items, which can break links between objects, and it does not record in the output that de-identification took place.
- The experimental pseudonymisation module (`pymedphys.experimental.pseudonymisation` and `pymedphys experimental dicom pseudonymise`) replaces UIDs and some numeric values with hashes computed without a secret key. Anyone who holds the original UIDs can recompute the replacements and re-link records, and small-range values such as weight can be recovered by trying every plausible value. Names and identifiers are hashed with a secret stored in plain text in the user's PyMedPhys configuration, so pseudonyms from different projects on the same installation can be linked. It shifts every patient's dates by the same offset, also stored there, keeps times unchanged, and can fail on names containing non-ASCII characters. Its keyword list excludes identifying sequences such as Icon Image, Original Attributes, and Digital Signatures, so it processes their contents element by element instead of removing them, and contents not on its list, such as icon image pixel data and digital signature certificates, are kept. It replaces Patient's Sex with a hash that is not a permitted value.
- Neither tool rewrites the DICOM file preamble or the Media Storage SOP Instance UID in the File Meta Information, so the original SOP Instance UID can remain in every output file.
- Neither tool detects burned-in text or recognisable faces.

Review any output from these tools carefully before sharing it outside your organisation.

## Planned transition

Neither `anonymise` nor experimental pseudonymisation will be deprecated until its replacement and migration guidance are released. Until then, their known limitations are documented here, and planned warnings for experimental pseudonymisation and notices for `anonymise` will state them without deprecating either tool. Once a replacement is released, each legacy tool will remain for at least one full minor release with deprecation warnings before removal. If the replacement is not delivered, both remain available, with their documented limitations. Exact versions will be recorded in the release notes when scheduled, following D-023 in the design document. Legacy hygiene fixes do not make the current tools conform to the planned profile.

## Further reading

- DICOM PS3.15 Annex E, [Attribute Confidentiality Profiles](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html).
- Clunie DA et al., [Report of the Medical Image De-Identification (MIDI) Task Group: Best Practices and Recommendations](https://arxiv.org/abs/2303.10473), preprint.
- UK Information Commissioner's Office, [anonymisation guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/introduction-to-anonymisation/).
- Office of the Australian Information Commissioner, [De-identification and the Privacy Act](https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/handling-personal-information/de-identification-and-the-privacy-act).
