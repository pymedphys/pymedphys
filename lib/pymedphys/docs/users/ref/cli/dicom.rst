DICOM Files
===========

.. automodule:: pymedphys.cli.dicom
    :no-members:

The ``anonymise`` subcommand is a legacy interface. It prints a notice of its
limitations on standard error when it runs. Read its limitations in
:doc:`../../background/dicom-deidentification` before sharing output.

The ``dicom listen`` command accepts connections from the local computer only by
default (``127.0.0.1``). To receive data from another computer on a
trusted network, explicitly provide ``--host`` with the interface address,
or ``--host 0.0.0.0`` to listen on all interfaces. The listener does not
provide authentication and must not be exposed to the public internet.

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: dicom
