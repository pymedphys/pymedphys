# Adding a Linac

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
  * This server should be able to have a guarantee that the connection
    between the server and the Linac will have near-zero network interruptions.
    This is due to the following bug at
    <https://github.com/pymedphys/pymedphys/issues/849> still being unresolved.
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
we have set up the [PyMedPhys iCom listener CLI tool](/cli/ref/icom.rst).

### Installing PyMedPhys on the iCom listener server

In our case, the server where the iCom listener is to be installed has the
requirement that the installation has minimal impact on the other software that
is also running on that same server. If you don't have that restriction you
can follow the [](get-started.rst) to install PyMedPhys in the usual fashion.

So that the Python installation itself has minimal impact on the system we
utilise Python's embedded distribution, an example download of one such
distribution is available at
<https://www.python.org/ftp/python/3.9.2/python-3.9.2-embed-amd64.zip>.

Also, given this installation of PyMedPhys is only going to be running as an
iCom listener it only needs a very minimal set of dependencies.

To install PyMedPhys within the embedded distribution
[these notes](https://www.christhoung.com/2018/07/15/embedded-python-windows/)
were followed, we followed these steps by doing the following:

* Extracted the Python embedded zip to `C:\Users\Public\Documents\python`
* Edited the `python39._pth`, uncommenting the last line to change from
  `#import site` to `import site`.
* Downloaded [get-pip.py](https://pip.pypa.io/en/stable/installing/#installing-with-get-pip-py)
  and then ran `C:\Users\Public\Documents\python\python.exe get-pip.py`
* Installed PyMedPhys by running `C:\Users\Public\Documents\python\python.exe -m pip install pymedphys[icom]==0.36.1`.

Make sure to adjust the above versions appropriately to match what is current.

### The [physics-server](https://github.com/CCA-Physics/physics-server) git repository

To facilitate SSH tunnelling between the sites there is
a server with the hostname `physics-server` at each site. The relevant software
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
SET PYTHON_DIR="C:\Users\Public\Documents\python"
cd %PYTHON_DIR%
SET PATH=%PYTHON_DIR%;%PYTHON_DIR%\Scripts;"%PATH%"

pymedphys icom listen 192.168.17.40 \\NBCCC-pdc\physics\NBCC-DataExchange\iCom
```

The key being that, given the way that Python and PyMedPhys was installed on
that server, the `pymedphys` CLI command was not found within the server's
`%PATH%` variable. As such, before utilising the `pymedphys` CLI the embedded
python distribution is temporarily added to the path. Here `192.168.17.40`
is the `Hospital DNS IP Address` of the Linac, and
`\\NBCCC-pdc\physics\NBCC-DataExchange\iCom` is the directory where the iCom
records are to be stored.

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

Not yet documented.
