####################
Pinnacle Export Tool
####################

*******
Summary
*******

.. automodule:: pymedphys.pinnacle
    :no-members:

.. warning::

   ``pymedphys.pinnacle`` is part of the stable Python API surface, but the
   Pinnacle Export Tool remains intended for research purposes only.
   Parts of the DICOM conversion are hard-coded and may ignore source data.
   Compare its output against the ground truth exported by your Pinnacle
   version before relying on it for research workflows, and do not use it
   clinically.

.. seealso::

   For the command line interface, see :doc:`../cli/pinnacle`.

***
API
***

.. autoclass:: pymedphys.pinnacle.PinnacleExport
   :members:

.. autoclass:: pymedphys.pinnacle.PinnaclePlan
   :members:

.. autoclass:: pymedphys.pinnacle.PinnacleImage
   :members:
