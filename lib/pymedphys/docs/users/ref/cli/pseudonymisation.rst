Pseudonymisation Tool
=====================

This command uses the legacy experimental pseudonymisation engine. See
:doc:`../../background/dicom-deidentification` for its limitations and the
planned transition before sharing output. The replacement presets described
there are not available through this command.

.. automodule:: pymedphys.cli.experimental.dicom
    :no-members:

.. warning::

    ``pymedphys experimental dicom pseudonymise`` is deprecated and prints a
    notice on standard error when it runs. It will be removed in a later
    release. The :doc:`../lib/experimental/pseudonymisation` lists its
    security limitations.

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: experimental dicom pseudonymise
