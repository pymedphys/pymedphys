# DICOM de-identification

This page explains the terms PyMedPhys uses for removing identifying information from DICOM data, what software can and cannot claim, and the known limitations of the tools currently in PyMedPhys. A standards-based replacement is being designed in the [de-identification design document](../../contrib/info/deidentification-design.md); it is not available yet.

## Terms

**De-identification** is the removal or replacement of information that could identify a person. It is the term used by the DICOM standard in [PS3.15 Annex E](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html) and by the [Medical Image De-Identification (MIDI) Task Group report](https://arxiv.org/abs/2303.10473).

**Pseudonymisation** is the replacement of direct identifiers, such as a patient's name and medical record number, with pseudonyms, so that records about the same person can still be linked to each other. It is one part of de-identification, not an alternative to it.

**Anonymisation** usually implies that nobody can reasonably re-identify the person. Whether that is true depends on the data *and* its release context: who receives it, what else they know or can obtain, and whether anyone holds a means of re-identification. It is a legal and contextual conclusion, for example under GDPR Recital 26 or the UK Information Commissioner's Office guidance, and no software can establish it on its own. Some laws, including the Australian Privacy Act 1988 (Cth) and the US HIPAA Privacy Rule, use "de-identified" for the same kind of legal conclusion. PyMedPhys therefore does not describe its output as anonymised, and does not describe it as de-identified without naming the DICOM profile it conforms to.

A few further terms, following the MIDI report:

- A **direct identifier** can identify a person on its own, for example a name, medical record number, or address.
- An **indirect identifier** (or quasi-identifier) can identify a person in combination with other knowledge, for example age, sex, weight, dates, or the treating institution.
- A **sensitive attribute** is information whose disclosure could harm the person even without identifying them, for example a diagnosis.

## Anonymisation and pseudonymisation use the same process

Removing identifiers and replacing them with consistent pseudonyms is the same transformation whether the result is called anonymised or pseudonymised. Two things differ:

1. **Whether a means of re-identification is kept.** If a key or a table mapping pseudonyms back to real identities is retained, whoever holds it can re-identify the data. For them, the data remain pseudonymised personal data. For a recipient without that key, the status needs its own assessment.
2. **Which indirect identifiers are kept.** Dates, ages, weights, device and institution names, and free-text descriptions can all help re-identify someone. Keeping them is sometimes essential, for example patient weight for PET standardised uptake values, or treatment dates for fractionation analysis. Each retained item adds risk that should be assessed for the particular collection.

## What a conformance claim means

The DICOM standard defines a Basic Application Level Confidentiality Profile and a set of Options that remove, replace, clean, or retain specific attributes. The planned replacement will describe its output as "de-identified in accordance with" a named edition of that profile and named Options only when its effective rules and output satisfy them.

Even full conformance does not guarantee that nobody can be identified:

- identifying text can be burned into the pixel data, which the Basic Profile does not address (PS3.15 E.2);
- the standard notes that it has been suggested that a 3D rendering of high-resolution head and neck imaging may be enough to identify a person (PS3.15 E.3.2), and the MIDI report notes that RT Structure Set contours of the body surface, including the head, pose a similar risk;
- the standard notes that anyone with access to the original images could match the pixel data, whatever happens to the identifiers (PS3.15 E.1.1 and E.3.9).

Deciding whether a collection can be shared, and with whom, therefore also needs a risk assessment for that collection and its intended recipients.

## Limitations of the current tools

Neither current tool implements the DICOM profile. Review any output from them carefully before sharing it outside your organisation.

### `anonymise`

These apply to `pymedphys.dicom.anonymise` and the `pymedphys dicom anonymise` command:

- UIDs are never replaced. Study, Series, SOP Instance, and Frame of Reference UIDs, and the references between objects, keep their original values, which anyone with access to the source systems can often trace back to the original records.
- Output file names contain the original SOP Instance UID.
- Its keyword list omits most RT attributes, so these pass through unchanged: RT Plan, Structure Set, and treatment dates and times; plan, structure set, and ROI labels, names, and descriptions; ROI interpreter names; beam names and descriptions; dose comments; treatment and RT Image machine names; and source serial numbers.
- It replaces some reference sequences, such as Referenced Image Sequence, with an empty item, which breaks links between objects.
- It writes `ANON` into Patient's Sex and other coded values it replaces, which is not a permitted value.
- `is_anonymised_dataset` can report output as anonymised while the problems above remain.

### Experimental pseudonymisation

These apply to `pymedphys.experimental.pseudonymisation`, the `pymedphys experimental dicom pseudonymise` command, and the pseudonymisation app:

- UIDs and decimal values are replaced with hashes computed without a secret key. Anyone who holds the original UIDs can recompute the replacements and re-link records, and small-range values such as weight can be recovered by trying every plausible value.
- Names and identifiers are hashed with a secret stored in plain text in the user's PyMedPhys configuration. There is one secret per installation, so pseudonyms from different projects on the same installation can be linked.
- Every patient's dates are shifted by the same offset, which is also stored in that configuration, and times are unchanged. Only dates on its keyword list are shifted; RT dates keep their true values. Where a shifted date and an unshifted RT date have a known or inferable original relationship, their difference reveals the offset, and with it the true dates of every patient pseudonymised with that configuration.
- It does not replace Referenced Dose Reference UID or most newer RT UIDs, so some references break or keep their original values.
- Its keyword list excludes identifying sequences such as Icon Image, Original Attributes, and Digital Signatures. It processes their contents element by element instead of removing them, so contents not on its list, such as icon image pixel data and digital signature certificates, are kept.
- The command replaces Patient's Sex with a hash that is not a permitted value and, with so few possible values, is easily reversed. `pseudonymise()` and the app leave it unchanged.
- It fails on names containing non-ASCII characters, and on some ages and decimal values.

### Both tools

- Directory mode recreates the source folder structure in the output, so folder names such as a patient's name are copied. Without an output directory, output is written beside the originals. Only files whose names end in `.dcm` are processed.
- Overlays are kept, as are unknown or newer attributes nested inside sequences.
- Neither tool records in its output that de-identification took place.
- Neither rebuilds the DICOM file preamble or File Meta Information, so the original Media Storage SOP Instance UID and Source Application Entity Title can remain in every output file.
- Neither detects burned-in text or recognisable faces.
- Exception messages can include original file paths and attribute values, and pydicom's warnings and log messages about invalid values quote those values.
- `pymedphys gui`, which runs the pseudonymisation app, starts Streamlit with its default settings. It listens on all network interfaces, so other computers on the network may be able to reach the app, and Streamlit's usage statistics are enabled.

## Planned replacement

Neither current tool will be deprecated until its replacement and migration guidance are released. Until then, their limitations are stated without deprecating them: experimental pseudonymisation's library functions emit a `PseudonymisationLimitationWarning`, its command prints a notice on standard error, and its app shows a banner, and planned notices for `anonymise` will do the same. Once a replacement is released, each current tool will remain for at least one full minor release with deprecation warnings before removal. If the replacement is not delivered, both remain available with their documented limitations.

## Further reading

- DICOM PS3.15 Annex E, [Attribute Confidentiality Profiles](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html).
- Clunie DA et al., [Report of the Medical Image De-Identification (MIDI) Task Group: Best Practices and Recommendations](https://arxiv.org/abs/2303.10473), preprint.
- UK Information Commissioner's Office, [anonymisation guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/introduction-to-anonymisation/).
- Office of the Australian Information Commissioner, [De-identification and the Privacy Act](https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/handling-personal-information/de-identification-and-the-privacy-act).
