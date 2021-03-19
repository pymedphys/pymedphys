==================
Adding a Linac
==================

Background
==========

PyMedPhys has a range of tools that interface with an Elekta Linac. All of
these interface points utilise "APIs" that the Elekta Linac exposes in its
default configuration. This document was written during the process of adding a
new Linac, at a remote site, to our already existing infrastructure within
Cancer Care Associates. We host the PyMedPhys application at one of our sites,
and that application is then able to access each Linac at all of our sites
by utilising SSH tunnels.


Prerequisites
==============

Before getting started you will need the following:

* The hospital/centre network IP that the NSS of the Linac was assigned
* A login username and password to the NSS to be able to access its file shares
* A server where you can run the iCom listener
  * This server should be able to have a guarantee that the connection
    between the server and the Linac will have near-zero network interruptions.
    This is due to the following bug at
    <https://github.com/pymedphys/pymedphys/issues/849> still being unresolved.
  * You will need permission to create a service on this iCom server and to
    set that service to be able to boot on server start.
