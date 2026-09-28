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

## Automated checks

Dependabot vulnerability and malware alerts, CodeQL code scanning, secret scanning with push protection, a weekly dependency audit, Bandit, and zizmor run in this repository. See the [workflow guide](lib/pymedphys/docs/contrib/info/workflows.md) for what each one covers and gates.
