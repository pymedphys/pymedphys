# Tunnels

## Background

At Cancer Care Associates PyMedPhys is deployed for use across multiple sites.
These sites need to all have access to the PyMedPhys Streamlit web server, and
in return data from each site needs to be able to be accessible to that very
same server. All of these communications between sites is handled via the
encrypted port forwarding capacity afforded by SSH tunnelling.

## Overview

These tunnel documents detail various how-to guides on how to achieve
individual components of this set up. These documents are not strictly
PyMedPhys specific, but they do detail how this multi-site deployment has been
achieved. As such, they are published here in the hope that they may be useful
to other system administrators who wish to deploy either PyMedPhys or similar
across their own network of centres.

## Index

```{toctree}
:maxdepth: 1

samba
rsync
```
