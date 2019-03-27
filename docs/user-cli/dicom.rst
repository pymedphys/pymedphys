DICOM CLI
=========

The DICOM CLI exposes the following CLI commands:

.. code-block:: bash

   pymedphys dicom adjust-machine-name
   pymedphys dicom adjust-RED
   pymedphys dicom adjust-RED-by-structure-name


Adjust machine name

.. argparse::
   :ref: pymedphys.cli.main.define_parser
   :prog: pymedphys
   :path: dicom