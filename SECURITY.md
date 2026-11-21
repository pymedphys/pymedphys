# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability.

Email <developers@pymedphys.com>. Include the PyMedPhys version, what the issue affects, and steps to reproduce if you have them.

You can instead report it privately with **Report a vulnerability** on the repository's **Security and quality** tab.

The maintainers will acknowledge the report, work with you on a fix, and agree the timing of any public disclosure with you.

## Supported versions

PyMedPhys is pre-1.0. Security fixes are released as new versions on PyPI and only the latest release receives them, so please upgrade before reporting an issue you cannot reproduce on the current version.

## Scope

PyMedPhys is a library and a set of tools that run on the user's own machine. The Streamlit GUI (`pymedphys gui`) and the DICOM listener (`pymedphys dicom listen`) are intended for trusted networks and are not hardened for exposure to the public internet.

## DICOM receiver diagnostic boundary

The `pymedphys dicom listen` command avoids patient-bearing storage paths
in its own messages. While the command runs, its Python logging stream also
replaces pydicom and pynetdicom records (including those emitted before the
C-STORE callback) and captured Python warnings with fixed summaries, retaining
their severity but not their DICOM values, raw exception text or paths.
This is a diagnostic-output safeguard, not DICOM de-identification.

The safeguard does not cover arbitrary direct writes to stdout/stderr, data
stored in the DICOM archive, callbacks, or custom application logging when
using `DicomListener` as a library. Detailed dependency diagnostics remain
available in separately configured, access-controlled clinical applications;
these must not forward unredacted logs to public or centralised collectors.
Keep archives and detailed clinical logs within the site's approved security
boundary.

## Automated checks

Dependabot vulnerability and malware alerts, CodeQL code scanning, secret scanning with push protection, a weekly dependency audit, Bandit, and zizmor run in this repository. See the [workflow guide](lib/pymedphys/docs/contrib/info/workflows.md) for what each one covers and gates.
