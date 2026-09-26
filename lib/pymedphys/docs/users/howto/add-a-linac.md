# Adding a Linac

```{note}
This guide describes a site-specific deployment at Cancer Care Associates.
Hostnames, addresses, accounts, paths, and service configuration are examples.
The installation instructions use the currently supported Python range;
the linked infrastructure repository records the original deployment.
```

## Background

PyMedPhys has a range of tools that interface with an Elekta Linac. All of
these interface points utilise "APIs" that the Elekta Linac exposes in its
default configuration. This document was written during the process of adding a
new Linac, at a remote site, to our already existing infrastructure within
Cancer Care Associates. We host the PyMedPhys application at one of our sites,
and that application is then able to access each Linac at all of our sites
by utilising SSH tunnels.

This document is written assuming that the servers within your centre being
utilised are Windows machines, however, it should be possible to adapt the
instructions here to work for other operating systems.

## Prerequisites

Before getting started you will need the following:

* The `Hospital DNS IP Address` that the NSS of the Linac was assigned.
  * Throughout this documentation it will be assumed that this is
    `192.168.17.40`.
* A name that can uniquely identify the Linac and will not change, eg. its
  serial number.
  * Throughout this document it will be assumed that this is `4299`.
* A login username and password to the NSS to be able to access its file shares
  that it is sharing with the centre's network via SAMBA.
* A server where you can run the iCom listener
  * Use a reliable network connection. [Issue #849](https://github.com/pymedphys/pymedphys/issues/849)
    records a listener-disconnection problem affecting treatment recording.
    It was closed in May 2025 after a report of a vendor fix in Integrity
    4.0.6.3. Treat Integrity versions before 4.0.6.3 as affected, and confirm
    with your vendor for your installed version.
  * You will need permission to create a service on this iCom server and to
    set that service to be able to boot on server start.
* A shared network drive at your centre where you will be storing the iCom and
  TRF records.
  * Throughout this document the iCom network path will be assumed to be
    `\\NBCCC-pdc\physics\NBCC-DataExchange\iCom`.
* A shared network drive at your centre which can be mounted by the iView to
  be utilised as a QA iView imaging database.

## The iCom listener

Elekta Linacs have an iCom protocol that can be utilised to determine various
parameters about the Linac state, eg. Gantry angle. This section details how
we have set up the [PyMedPhys iCom listener CLI tool](../ref/cli/icom.rst).

### Installing PyMedPhys on the iCom listener server

Use a dedicated virtual environment so the listener's dependencies are
isolated from other software on the server. Install uv using the
{doc}`quick start guide <../get-started/quick-start>`, then run in PowerShell,
replacing `DOMAIN\svc-icom` with the account the service will log on as:

```powershell
$env:UV_PYTHON_INSTALL_DIR = "C:\PyMedPhys\python"
$env:UV_LINK_MODE = "copy"
uv python install 3.12
uv venv --python 3.12 C:\PyMedPhys\icom\.venv
uv pip install --python C:\PyMedPhys\icom\.venv\Scripts\python.exe "pymedphys[icom]" "numpy<2"
icacls C:\PyMedPhys /grant "DOMAIN\svc-icom:(OI)(CI)RX" /T
C:\PyMedPhys\icom\.venv\Scripts\python.exe -m pymedphys icom listen --help
```

By default uv installs Python under the installing user's profile, and the
virtual environment refers back to that interpreter. A separate service
account normally cannot read another user's profile, so the service would
fail to start. `UV_PYTHON_INSTALL_DIR` places the interpreter alongside the
environment, and `UV_LINK_MODE=copy` copies packages from uv's cache instead
of hard-linking them, so they do not keep the cache's profile permissions.
The `numpy<2` constraint matches the cap in the current source; the `icom`
extra of the 0.41.0 release does not cap NumPy.

Choose a directory accessible to the service account, and use that same path
in the service definition below. Before creating the service, run the
`--help` command in a shell started as the service account (for example,
`runas /user:DOMAIN\svc-icom powershell`) to confirm it can read the
environment. Install and test the version approved for your site's
deployment; append `==VERSION` to the requirement to pin it. The original
embedded-Python 3.9 / PyMedPhys 0.36.1 procedure is obsolete for the current
source.

### The [physics-server](https://github.com/CCA-Physics/physics-server) git repository

To facilitate SSH tunnelling between the sites there is a server with the
hostname `physics-server` at each site. The relevant software
and configuration on these servers is stored within a public GitHub repository
at <https://github.com/CCA-Physics/physics-server>. All of the code snippets
presented within this iCom section are adapted from the code found within
that repository's
[NBCC/icom](https://github.com/CCA-Physics/physics-server/blob/8f09d1575106c57d1284146f3020ddba4fcbe884/NBCC/icom)
directory.

### Setting up the iCom listener as a Windows service

To convert the PyMedPhys CLI tool into a Windows service the
[NSSM](https://nssm.cc/) tool was utilised. It takes `.bat` files and converts
them into a Windows service. A file called `4299_listening.bat` was created
with the following contents:

```bat
@echo off
"C:\PyMedPhys\icom\.venv\Scripts\python.exe" -m pymedphys icom listen 192.168.17.40 "\\NBCCC-pdc\physics\NBCC-DataExchange\iCom"
```

The absolute Python path selects the listener's environment without changing
the machine's `PATH`. Here `192.168.17.40` is the Linac's hospital-network
address, and `\\NBCCC-pdc\physics\NBCC-DataExchange\iCom` is the output
directory. The service account needs access to that network share.

Once this `.bat` file was defined [NSSM](https://nssm.cc/) was downloaded with
its `.exe` placed at `C:\Users\Public\Documents\physics-server\bin`. Then,
to create the service the following `.bat` file was created and run as
administrator:

```bat
SET GIT_ROOT=C:\Users\Public\Documents\physics-server
SET PATH=%GIT_ROOT%\bin;%PATH%
SET HERE=%GIT_ROOT%\NBCC\icom

SET SERIAL=4299

nssm install icom_listening_%SERIAL% %SERIAL%_listening.bat

nssm set icom_listening_%SERIAL% Application %HERE%\%SERIAL%_listening.bat
nssm set icom_listening_%SERIAL% AppDirectory %HERE%

nssm set icom_listening_%SERIAL% AppStdout %HERE%\%SERIAL%_listening_log.txt
nssm set icom_listening_%SERIAL% AppStderr %HERE%\%SERIAL%_listening_log.txt

nssm set icom_listening_%SERIAL% AppRestartDelay 300000
```

Then, within the Windows services manager this service was set up so that its
`Startup Type` is set to `Automatic` and the `Log On As` setting was then set
to a user that had the appropriately scoped permissions.

## iView database

Not yet documented.

## TRF indexing

Not yet documented.

## Updating the `config.toml` file

Create `config.toml` in the `.pymedphys` directory under the home directory
of the account running the GUI. This is separate from the listener, whose
output directory is supplied on its command line. A
[historical site configuration](https://github.com/pymedphys/pymedphys/blob/9ebe4ad4261709c5a1c3bcef120be0660e715e84/site-specific/cancer-care-associates/config.toml)
shows a larger deployment.

To inspect service-mode iCom recordings with the draft **iCom Logs Explorer**
app, a minimal site configuration is:

```toml
[[site]]
name = "Example site"

[site.export-directories]
icom = 'C:\PyMedPhysData\iCom'
```

Use your real path. These TOML strings do not expand `%USERNAME%` or other
environment variables. The explorer app looks under the `patients` subdirectory
of the configured iCom export directory and selects subdirectories whose
names start with `Deliver` or `WLutz`, or contain `QA`.

For example, place a service-mode recording at:

```text
C:\PyMedPhysData\iCom\patients\QA\20250301_152405.xz
```

The filename stem must use `YYYYMMDD_HHMMSS`. You do not need to create all
three of `QA`, `Delivery`, and `WLutz`. The `[icom].patient_directories` setting
is used by other app workflows and is not the directory selector for this
explorer.

Run `pymedphys gui` from a `user` installation and open **iCom Logs Explorer**
in the draft apps. This GUI needs more dependencies than the listener-only
`icom` installation.

The [example data record](https://zenodo.org/records/4579973) contains the
**MU Density GUI e2e data** archive, including sample iCom `.xz` files under
`inputs/iCOM/patients/989898_PHYSICS, MOCK/`.
