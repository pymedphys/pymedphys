# Tunnels

## Background

These pages record a deployment originally set up at Cancer Care Associates.
They are site-specific examples, not a statement about the organisation's
current infrastructure. PyMedPhys was deployed for use across multiple sites.
The sites needed access to the PyMedPhys Streamlit web server, and the server
needed access to their data. SSH tunnels provided encrypted port forwarding
between sites.

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
