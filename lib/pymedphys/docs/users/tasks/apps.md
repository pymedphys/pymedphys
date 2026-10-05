# Use the apps

Install the `user` extra, activate the environment, and run `pymedphys gui`.
Choose an app from the selector. The [GUI reference](../ref/cli/gui.rst)
describes serving addresses, ports, and host restrictions. By default only this
computer can connect. If serving another computer, apply the access conditions
in that reference: the apps have no login and use unencrypted HTTP.

The selector groups apps by their declared maturity. A beta app still belongs
to a beta package; review release notes and validate your workflow when
upgrading. Alpha/draft apps have additional interface and completeness risks.

## MetersetMap Comparison

Use the [first-result demonstration](first-result.md#compare-delivery-using-the-app-demonstration)
for a complete path with public data. The three configuration modes are:

| Mode | Inputs and outputs |
| --- | --- |
| **Demo Data** | Downloads example records/configuration into the current working directory. |
| **File Upload/Download Only** | Bundled configuration enables DICOM RT Plan and TRF uploads without a clinic connection. Its output defaults to `~/pymedphys-gui-metersetmap`. |
| **Config on Disk** | Uses the configured site directories, data methods, and output locations. Appears when the configuration file is available. |

For uploads, enable **Run in Advanced Mode** to change **Data Input Method**.
Upload a supported RT Plan as reference and its intended TRF as evaluation.
Choose the required fraction group for a multi-group plan and check the selected
field/session, displayed names, MU, and control-point counts before calculation.
Missing Mosaiq configuration can leave the TRF patient name as `Unknown`; that
does not prevent decoding, but the operator must establish the intended pairing.

The app uses a 1 mm grid, 410 mm maximum leaf gap, and 80 leaf pairs with 10 mm
outer pairs and 78 inner pairs of 5 mm. These are fixed app settings, not values
read from the gamma configuration. Use the library with explicit geometry for
a different machine; see [Delivery data](delivery.md).

**Run Calculation** creates:

- reference and evaluation MetersetMap images;
- an evaluation-minus-reference difference image;
- gamma on the reference map, and a histogram with summary values;
- `reference.png`, `evaluation.png`, `diff.png`, `gamma.png`, and `report.png`
  under the configured PNG directory;
- a PDF in the selected eSCAN directory when ImageMagick conversion succeeds.

Check the actual output locations before running. Source identifiers and paths
appear in reports and filenames. Saved component PNGs are display images rather
than full-precision numerical arrays. Gamma settings are supplied by `[gamma]`,
with selected overrides in advanced mode. The report titles currently say
“Local Gamma”; retain the actual configured `local_gamma` value with your
interpretation, especially if using global gamma.

A MetersetMap represents MU-weighted aperture exposure, not absorbed dose or an
independent measurement of leaf position. Interpret spatial disagreement,
selected MU, cutoff, and the number of analysed pixels alongside pass rate.
If PDF conversion fails, inspect the saved PNG and install/configure ImageMagick
if a PDF is required. A missing site/path/key error calls for the
[configuration reference](../ref/configuration.md), not an arbitrary copy of
another centre's settings. Restart the app after editing its cached configuration.

## DICOM Pseudonymisation

This beta app applies the legacy experimental pseudonymisation interface to
uploaded DICOM files/ZIPs and offers outputs for download. Read
[DICOM de-identification](../background/dicom-deidentification.md) before use:
the current tool does not implement a DICOM confidentiality profile and output
requires review before sharing. The planned replacement is documented separately.
Generated pseudonymisation settings are installation-wide and stored in plain
text in `config.toml`; see [configuration](../ref/configuration.md#credentials-and-settings-outside-this-file).

## Experimental apps

These entries are available from the selector; maturity follows their current
registration. Start with approved example data and verify outputs against a
known source before adopting a workflow.

| App | Maturity | Purpose and prerequisites |
| --- | --- | --- |
| Electron Insert Factor Modelling | Alpha | Models measured cutout-factor data with Monaco inserts. Provides demo configuration; a site configuration needs Monaco paths, a measurement CSV, and matching patterns. See [electron factors](electronfactors.md). |
| Clinical Dashboard | Alpha | Displays site Mosaiq physics-QCL information. Needs configured Mosaiq access and `physics_qcl_location`; reports depend on local task conventions. |
| iCom Logs Explorer | Draft | Browses recorded streams. Needs a site's `export-directories.icom` with the expected archive layout. |
| TRF Explorer | Draft | Uploads/selects and decodes TRFs; indexing and patient lookup require the relevant TRF/Mosaiq settings. |
| iView Database Explorer | Draft | Explores a configured iView DB directory and its DBF tables/files. Site and linac configuration must match the source. |
| DICOM Explorer | Draft | Displays an uploaded DICOM header; header values may identify a patient. |
| Sum Coincident DICOM Doses | Draft | Uploads at least two compatible RT Dose files, sums them, and offers a DICOM download. Grids must satisfy the dose-grid checks; acceptance does not resample them or establish clinical compatibility. |
| Mosaiq to CSV | Draft | Exports configured Mosaiq data for selected patient IDs. Needs authorised database access; CSVs contain identifying information. |
| Anonymising Monaco Backend Files | Draft | Transforms selected Monaco backend files into the configured export directory. Review output contents and identifiers before sharing. |
| MOSAIQ Claude Chat | Draft, opt-in | Sends questions and database query results to Anthropic's API. Needs `user,ai`, an Anthropic key, network access, and Mosaiq access. |

For the AI app, install `pymedphys[user,ai]` only when this external service is
intended. It reads `ANTHROPIC_API_KEY` or accepts a key in its UI. Authorise the
data flow with the people responsible for the database and service before
querying: installing the extra does not authorise sending clinical data.
Other apps do not need that extra.

The current shared Mosaiq selector used by **Mosaiq to CSV** and **MOSAIQ
Claude Chat** connects on port 1433 even if the site configuration supplies
a different port. See the configuration reference before selecting a site
that requires a non-default endpoint.

See the [configuration reference](../ref/configuration.md) for fields consumed
by these apps. Experimental apps are not interchangeable routes to every
library feature; use the [task index](index.md) to choose the appropriate API
or command when a graphical workflow does not cover the task.
