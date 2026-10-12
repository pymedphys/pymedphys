Pseudonymisation Tool
=====================

This command uses the legacy experimental pseudonymisation engine. Read its
limitations in :doc:`../../background/dicom-deidentification` before sharing
output.

.. automodule:: pymedphys.cli.experimental.dicom
    :no-members:

.. warning::

    ``pymedphys experimental dicom pseudonymise`` prints a notice of its
    security limitations on standard error when it runs. The
    :doc:`../lib/experimental/pseudonymisation` describes them.

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: experimental dicom pseudonymise
