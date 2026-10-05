# Configuration reference

Most library calls and file-based CLI commands do not require a site
configuration. Configure the feature you use: the app and logfile consumers
read different subsets of the same TOML file. The loader does not validate a
single global schema, supply missing feature keys, or merge defaults from
another file. A bundled example's `version = 1` is not a schema-version
contract.

## Locate the file and follow redirects

The default file is `~/.pymedphys/config.toml`, where `~` is the home
directory of the account running the command or app. On Windows this is usually
`C:/Users/<account>/.pymedphys/config.toml`. A scheduler or service account
may have a different home directory from your interactive account.

The internal loader's optional path is a **directory** containing
`config.toml`, not a filename. Apps with a demo or bundled-file mode select
such a directory internally. There is no general CLI `--config` option.

To share a centrally managed configuration, the local file can contain:

```toml
redirect = "../department/pymedphys.toml"
```

A relative redirect is resolved against the file containing it; an absolute
path is also accepted. Redirects may chain, and a repeated resolved file raises
`ValueError`. Each target replaces the preceding file's contents: keys beside
`redirect` are not merged into the target. Missing files and malformed TOML
raise errors; missing consumer keys often raise `KeyError` or omit a site
from a selector.

Path strings are not automatically expanded by the loader. Some consumers
expand `~`, while others pass the string directly to `Path` or a file reader.
Use absolute paths for deployed configuration. TOML literal strings are useful
for Windows paths, for example `'C:\Research\reports'`; forward slashes
also work. Environment variables such as `%USERPROFILE%` and `$HOME` are not
expanded by the loader. Restart the app after editing configuration because
app readers cache it.

## Minimum configuration for MetersetMap file uploads

The **File Upload/Download Only** mode already supplies a bundled configuration.
To use **Config on Disk** with DICOM/TRF uploads, this is a complete small
example. Replace the two output paths with writable, authorised directories
before use:

```toml
[data_methods]
available = ["dicom", "trf"]
default_reference = "dicom"
default_evaluation = "trf"

[[site]]
name = "Practice"

[site.export-directories]
escan = 'C:/Research/practice/reports'

[output]
png_directory = 'C:/Research/practice/metersetmaps'

[gamma]
dose_percent_threshold = 2
distance_mm_threshold = 0.5
local_gamma = true
quiet = true
max_gamma = 5
lower_percent_dose_cutoff = 20
```

These gamma settings mirror the bundled app configuration; they are examples,
not a recommendation or an acceptance criterion. Choose and retain parameters
appropriate to your verified workflow. The calculation uses MetersetMap values
rather than absorbed dose. See [the app guide](../tasks/apps.md).

| Key | Consumer and requirement |
| --- | --- |
| `data_methods.available` | MetersetMap input choices: `monaco`, `dicom`, `icom`, `trf`, `mosaiq`. Enable only configured sources. |
| `data_methods.default_reference`, `default_evaluation` | Must name enabled input choices. |
| `site[].name` | Site label and key used by selectors and machine-to-site mappings. |
| `site[].export-directories.escan` | Destination for the app's report; selected site must supply it. |
| `output.png_directory` | Destination for component PNGs and assembled reports. |
| `gamma` | Keyword arguments passed to `pymedphys.gamma`; the advanced controls also directly require `dose_percent_threshold`, `distance_mm_threshold`, `local_gamma`, and `max_gamma`. |
| `debug.baseline_directory` | Optional advanced comparison with existing baseline PNGs. |

The normal output/export-directory controls expand `~`. The optional baseline
comparison reads its path directly. PDF creation requires the separately
installed ImageMagick executable and its local permissions; a PNG report may
exist even if PDF conversion fails.

## Add delivery sources

Add keys for the sources enabled above. This fragment illustrates the table
nesting; replace hostnames, paths, machine names, and timezone with local values:

```toml
[[site]]
name = "Practice"

[site.monaco]
focaldata = 'C:/Research/Monaco/FocalData'
clinic = "PracticeClinic"

[site.export-directories]
escan = 'C:/Research/practice/reports'
icom = 'C:/Research/icom-records'
icom_live = 'C:/Research/icom-records/live'

[site.mosaiq]
hostname = "mosaiq.example.invalid"
port = 1433
timezone = "Australia/Sydney"
alias = "Practice Mosaiq"

[[site.linac]]
name = "PRACTICE_LINAC"
ip = "192.0.2.10"
samba_ip = "192.0.2.11"

[icom]
patient_directories = ['C:/Research/icom-records/patients']

[trf_logfiles]
root_directory = 'C:/Research/trf-records'
```

This fragment replaces the example's `[[site]]` block; do not append a second
site with the same name. Keep the earlier `data_methods`, `output`, and
`gamma` tables when using the app.

| Feature | Additional keys and interpretation |
| --- | --- |
| Monaco delivery selection | `site[].monaco.focaldata` plus `clinic` are joined to locate the clinic directory. These strings are not expanded. The adapter reads raw `tel.1` files; see [delivery data](../tasks/delivery.md). |
| DICOM file search | The app derives `DCMXprtFile` from the selected Monaco clinic directory's grandparent. There is no independent DICOM search-directory key. Uploading a DICOM file does not need this search location. |
| iCOM delivery selection | `icom.patient_directories` is a list of archived patient directories containing `.xz` records. Supply absolute paths; these are passed directly to `Path`. |
| Indexed TRF selection | `trf_logfiles.root_directory` supplies `indexed/` and `index.json`. `site[].linac[].name` maps a machine to its site; that site's Mosaiq hostname, port, and timezone support identification. Unindexed TRF upload has a separate path. |
| Mosaiq delivery selection | Each configured site needs `mosaiq.hostname`, `port`, and `timezone`. `alias` is optional and otherwise displays hostname/port. Database name is `MOSAIQ` in this app connection path. |
| Live status display | `site[].export-directories.icom_live` and each `linac[].ip` locate the listener's `live/<ip>/` directories. `linac[].name` identifies the displayed machine; diagnostic backup status also uses the TRF root. |

The iCOM listener itself takes IP and output-directory CLI arguments and does
not use this TOML source configuration. Its input IP and the Samba backup IP
can differ. See [logfile capture and decoding](../tasks/logfiles.md).

## Configure TRF orchestration

`pymedphys trf orchestrate` requires `trf_logfiles.root_directory`,
`site[].name`, a Mosaiq `hostname`, `port`, and `timezone`, plus a
`site[].linac` array with each machine's `name` and `samba_ip`.
Sites missing the Mosaiq details and machines missing name/Samba IP are skipped.
Check the selected machines and the generated index rather than treating an
empty run as success.

The account running it needs access to the Elekta diagnostic backup share,
the archive/index destinations, and Mosaiq credentials. The command fetches,
extracts, archives, and indexes data under the TRF root; it changes those
directories. Run it on an approved test archive before scheduling it. The
timezone describes Mosaiq's local time for matching UTC logfile timestamps.
It must include the correct daylight-saving rules.

## Configure the experimental apps

The [app catalogue](../tasks/apps.md) records each app's declared maturity and
scope. These keys do not enable or validate every app at once.

| App | Required configuration |
| --- | --- |
| iCom Logs Explorer | A named site with `export-directories.icom`, pointing to the listener's base directory; it appends `patients/`. |
| TRF Explorer | TRF root and machine/site mappings as used by indexed TRF selection. |
| iView Database Explorer | Site `export-directories.iviewdb` and `icom`; `linac[].name`, `linac[].directories.qa`; optional `linac[].aliases.iview` maps the database's machine ID to that linac name. |
| Clinical Dashboard | `site[].mosaiq.hostname`, `port`, `alias`, and `physics_qcl_location`. A site missing any of these is omitted. |
| Mosaiq to CSV, MOSAIQ Claude Chat | A site name and Mosaiq hostname. Their shared selector currently reads but does not forward configured `port` or `alias`; its connection uses port 1433 and database `MOSAIQ`. |
| Anonymising Monaco Backend Files | Site Monaco `focaldata`/`clinic` and `export-directories.anonymised_monaco`. Review the output and exclusions before sharing. |
| Electron Insert Factor Modelling | `electron_insert_modelling.data_path` and `patterns.beam_model_name`/`patterns.applicator`, plus the Monaco site paths for file selection. See below. |
| DICOM Explorer, Sum Coincident DICOM Doses | File uploads; no site connection configuration required. |
| DICOM Pseudonymisation | May generate or use the `pseudo` values described below. |

The shared site export-directory helper expands `~` for `escan`,
`anonymised_monaco`, `iviewdb`, and `icom`. It silently omits missing
directories from its mapping, so a later app selection may fail. Linac QA and
Monaco paths are read directly.

Electron modelling configuration has this shape:

```toml
[electron_insert_modelling]
data_path = 'C:/Research/electrons/measurements.csv'

[electron_insert_modelling.patterns]
beam_model_name = '([0-9]+)MeV'
applicator = '([0-9]+)cm'
```

These expressions are illustrative and must match your source names, with the
intended value in capture group 1. The CSV column names, SSD selection, factor
definition, minimum measurement count, and verification steps are specified in
[the electron modelling guide](../tasks/electronfactors.md).

## Credentials and settings outside this file

Mosaiq usernames and passwords are handled through the OS keyring or explicit
library arguments, rather than site TOML keys. The storage identity includes
hostname, port, and database. Use an authorised read-only account; the driver's
read-only request is not a replacement for database permissions. See
[the Mosaiq guide](../tasks/mosaiq.md) for connection lifetime and parameters.

Experimental pseudonymisation stores `pseudo.pepper` (an ASCII string) and
`pseudo.epoch_jitter` (an integer) in configuration, generating them when
absent. The current implementation writes generated values to the default
`~/.pymedphys/config.toml`, including when the loaded configuration came through
a redirect. Keep that file protected and account for this write before using
a central redirect. These values are shared across this account's runs; they
do not provide the planned per-project de-identification policy. Some values
and UIDs are still hashed without the pepper. Read
[the current limitations](../background/dicom-deidentification.md).

`PYMEDPHYS_DATA_DIR` selects the downloaded-data cache; the default is
`~/.pymedphys/data`. It does not relocate the site configuration. The
[data helper reference](lib/data.rst) describes verification and extraction.

Streamlit has its own `~/.streamlit/config.toml`. GUI CLI options for server
address, browser usage, and allowed hosts are separate from this site file;
see the [GUI CLI reference](cli/gui.rst). Keep host settings aligned with the
actual way users reach the server.

**MOSAIQ Claude Chat** reads `ANTHROPIC_API_KEY` or an entered API key and
sends prompts and query results to Anthropic when used. This is an opt-in
external service; site TOML does not authorise data transfer.

Zenodo upload tooling stores its token in the OS keyring under service
`Zenodo` and account `zenodo.org`. Public demo downloads do not require an
upload token. See the [Zenodo CLI reference](cli/zenodo.rst).

## CLI logging

An optional table configures Python's `logging.basicConfig`:

```toml
[cli.logging]
level = "WARNING"
format = "%(asctime)s %(levelname)-8s %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
```

Without logging configuration, the default level is WARNING.
`pymedphys --verbose ...` overrides it to INFO, and `pymedphys --debug ...`
overrides it to DEBUG. These options precede the command name. The default
format and date format are those above; the default debug format adds source
filename and line number. Other supported `basicConfig` arguments such as
`filename`, `filemode`, and `encoding` are passed through. Configure them
according to the Python logging reference and keep destinations writable and
appropriately protected. Logs may contain paths and identifiers.

A missing default file is tolerated for CLI logging. A malformed file, redirect
loop, invalid level, or invalid logging arguments can stop CLI startup even
when the selected command would otherwise need no site configuration.

## Diagnose a configuration failure

Check the running account's home directory, the final redirect target, and
TOML syntax first. Then compare the failing feature against its required keys,
confirm absolute paths and permissions, and restart cached app readers.
For selectors with no available sites, check keys that cause sites to be
skipped. For Mosaiq/TRF mismatches, check machine names, port, database, and
timezone independently of filesystem configuration.

The relevant consumers are the
[configuration loader](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_config.py),
[shared app directories](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_streamlit/utilities/config.py),
[MetersetMap settings](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_streamlit/apps/metersetmap/_config.py),
[TRF orchestration](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_trf/manage/orchestration.py), and the app-specific
readers described above. These links identify implementation details for
contributors; they are not additional configuration interfaces.
