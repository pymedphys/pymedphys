# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability.

Report it through GitHub's private vulnerability reporting for this repository (the "Report a vulnerability" button under the Security tab), or email <developers@pymedphys.com>. Include the PyMedPhys version, what the issue affects, and steps to reproduce if you have them.

The maintainers will acknowledge the report, work with you on a fix, and agree the timing of any public disclosure with you.

## Supported versions

PyMedPhys is pre-1.0. Security fixes are released as new versions on PyPI and only the latest release receives them, so please upgrade before reporting an issue you cannot reproduce on the current version.

## Scope

PyMedPhys is a library and a set of tools that run on the user's own machine. The Streamlit GUI (`pymedphys gui`) and the DICOM listener (`pymedphys dicom listen`) are intended for trusted networks and are not hardened for exposure to the public internet.

## Automated checks

Dependabot alerts, a weekly dependency audit, Bandit, and zizmor run in this repository. See `lib/pymedphys/docs/contrib/info/workflows.md` for what each one gates.
