# DICOM de-identification

This page explains the terms PyMedPhys uses when it removes identifying information from DICOM data, what software can and cannot claim, and the known limitations of the tools currently in PyMedPhys. A replacement de-identification engine is being built; its design and progress are recorded in the [de-identification design document](../../contrib/info/deidentification-design.md).

## Terms

**De-identification** is the removal or replacement of information that could identify a person. It is the term used by the DICOM standard in [PS3.15 Annex E](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html) and by the [Medical Image De-Identification (MIDI) Task Group report](https://arxiv.org/abs/2303.10473). PyMedPhys uses this term for what its tools do.

**Pseudonymisation** is the replacement of direct identifiers, such as a patient's name and medical record number, with pseudonyms, so that records about the same person can still be linked to each other. It is one part of de-identification, not an alternative to it.

**Anonymisation** usually implies that nobody can reasonably re-identify the person. Whether that is true depends on the data *and* its release context: who receives it, what else they know or can obtain, and whether anyone holds a means of re-identification. It is a legal and contextual conclusion, for example under GDPR Recital 26, the Australian Privacy Act 1988 (Cth), or the UK Information Commissioner's Office guidance. No software can establish it on its own, so PyMedPhys does not describe its output as anonymised.

A few further terms, following the MIDI report:

- A **direct identifier** can identify a person on its own, for example a name, medical record number, or address.
- An **indirect identifier** (or quasi-identifier) can identify a person in combination with other knowledge, for example age, sex, weight, dates, or the treating institution.
- A **sensitive attribute** is information whose disclosure could harm the person even without identifying them, for example a diagnosis.

## Anonymisation and pseudonymisation are the same process

Removing identifiers and replacing them with consistent pseudonyms is the same transformation whether the result is called anonymised or pseudonymised. Two things differ:

1. **Whether a means of re-identification is kept.** If a key or a table mapping pseudonyms back to real identities is retained, whoever holds it can re-identify the data. For them, the data remain pseudonymised personal data. For a recipient without that key, the status needs its own assessment.
2. **Which indirect identifiers are kept.** Dates, ages, weights, device and institution names, and free-text descriptions can all help re-identify someone. Keeping them is sometimes essential, for example patient weight for PET standardised uptake values, or treatment dates for fractionation analysis. Each retained item adds risk that should be assessed for the particular collection.

## What software can claim

The DICOM standard defines a Basic Application Level Confidentiality Profile and a set of Options that remove, replace, clean, or retain specific attributes. The replacement engine will claim that its output is *de-identified in accordance with* a named edition of that profile with named options only when its effective rules and output satisfy those requirements. Selecting a preset alone is not evidence of conformance. Custom removals as well as retentions can invalidate an object or contradict an option. Unsupported processing, including opt-in processing of Private SOP Classes, will be labelled as outside the conformance claim.

Even full conformance does not guarantee that nobody can be identified. The standard itself notes that:

- identifying text can be burned into the image pixels, which the Basic Profile does not address;
- faces can be reconstructed from head and neck CT, MR, and PET, and an RT Structure Set body contour of a head and neck case is itself a face surface;
- anyone with access to the original images can match pixel data, whatever happens to the identifiers.

Deciding whether a collection can be shared, and with whom, therefore also needs a risk assessment for that collection and its intended recipients.

The planned public-release workflow also requires human quality control and a documented statistical risk assessment. A numerical threshold is meaningful only with its named model, assumptions, and subject-level unit of analysis; it is not an overall guarantee of anonymity. Confidential review packs may contain identifying strings or image previews missed by automated cleaning. They must remain in the restricted review environment and must not be included with released data or ordinary reports.

## Limitations of the current PyMedPhys tools

The tools currently in PyMedPhys do not implement the DICOM profile. Until the replacement engine is available, be aware of the following:

- `pymedphys.dicom.anonymise` and the `pymedphys dicom anonymise` command keep every UID (Study, Series, SOP Instance, and Frame of Reference UIDs). UIDs can often be traced back to the original records by anyone with access to the source systems. The tool also replaces some reference sequences with empty items, which can break links between objects, and it does not record in the output that de-identification took place.
- The experimental pseudonymisation module (`pymedphys.experimental.pseudonymisation` and `pymedphys experimental dicom pseudonymise`) replaces UIDs and some numeric values with hashes computed without a secret key. Anyone who holds the original UIDs can recompute the replacements and re-link records, and small-range values such as weight can be recovered by trying every plausible value. It shifts every patient's dates by the same offset, stored in the user's PyMedPhys configuration, and it can fail on names containing non-ASCII characters. It is deprecated and will be removed in a future release.
- Neither tool rewrites the DICOM file preamble or the Media Storage SOP Instance UID in the File Meta Information, so the original SOP Instance UID can remain in every output file.
- Neither tool detects burned-in text or recognisable faces.

Review any output from these tools carefully before sharing it outside your organisation.

## Further reading

- DICOM PS3.15 Annex E, [Attribute Confidentiality Profiles](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html).
- Clunie DA et al., [Report of the Medical Image De-Identification (MIDI) Task Group: Best Practices and Recommendations](https://arxiv.org/abs/2303.10473), preprint.
- UK Information Commissioner's Office, [anonymisation guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/introduction-to-anonymisation/).
- Office of the Australian Information Commissioner, [De-identification and the Privacy Act](https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/handling-personal-information/de-identification-and-the-privacy-act).
