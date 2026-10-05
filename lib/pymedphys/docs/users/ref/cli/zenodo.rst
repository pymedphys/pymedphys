Zenodo
======

``pymedphys zenodo set-token`` stores a Zenodo access token in the operating
system keyring under service ``Zenodo`` and account ``zenodo.org``. It is used
by upload tooling; the command does not download data or publish an upload.

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: zenodo

The token is a positional argument, so it can be retained in shell history
or exposed to local process inspection. Keep tokens out of documentation,
logs, screenshots, and committed configuration. Use an appropriate protected
interactive session if this command is needed.

Public example downloads use :doc:`../lib/data` and do not need an upload
token.
