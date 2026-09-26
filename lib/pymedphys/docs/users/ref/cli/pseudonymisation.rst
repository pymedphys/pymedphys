Pseudonymisation Tool
=====================

This command uses the legacy experimental pseudonymisation engine. See
:doc:`../../background/dicom-deidentification` for its limitations and the
planned transition before sharing output. The replacement presets described
there are not available through this command.

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
