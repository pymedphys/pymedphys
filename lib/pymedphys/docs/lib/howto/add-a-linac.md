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

* The hospital/centre network IP that the NSS of the Linac was assigned
* A name that can uniquely identify the Linac and will not change, eg. its
  serial number.
* A login username and password to the NSS to be able to access its file shares
* A server where you can run the iCom listener
  * This server should be able to have a guarantee that the connection
    between the server and the Linac will have near-zero network interruptions.
    This is due to the following bug at
    <https://github.com/pymedphys/pymedphys/issues/849> still being unresolved.
  * You will need permission to create a service on this iCom server and to
    set that service to be able to boot on server start.
* A shared network drive at your centre where you will be storing the iCom and
  TRF records.
* A shared network drive at your centre which can be mounted by the iView to
  be utilised as a QA iView imaging database.

## Installing PyMedPhys on the iCom listener server

In our case, the server where the iCom listener is to be installed has the
requirement that the installation has minimal impact on the other software that
is also running on that same server. If you don't have that restriction you
can follow the [](get-started.rst) to install PyMedPhys in the usual fashion.

So that the Python installation itself has minimal impact on the system we
utilise Python's embedded distribution, an example download of one of those
distributions is available at
<https://www.python.org/ftp/python/3.9.2/python-3.9.2-embed-amd64.zip>.

Also, given this installation of PyMedPhys is only going to be running as an
iCom listener it doesn't need any extra dependencies.

To install PyMedPhys within the embedded distribution
[these notes](https://www.christhoung.com/2018/07/15/embedded-python-windows/)
were followed, we followed these steps by doing the following:

* Extracted the Python embedded zip to `C:\Users\Public\Documents\python`
* Edited the `python39._pth`, uncommenting the last line to change from
  `#import site` to `import site`.
* Downloaded [get-pip.py](https://pip.pypa.io/en/stable/installing/#installing-with-get-pip-py)
  and then ran `C:\Users\Public\Documents\python\python.exe get-pip.py`
* Installed PyMedPhys by running `C:\Users\Public\Documents\python\python.exe -m pip install pymedphys==0.36.0`.

Make sure to adjust the above versions appropriately to match what is current.
