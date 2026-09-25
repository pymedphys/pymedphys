#####
DICOM
#####

*******
Summary
*******

.. automodule:: pymedphys.dicom
    :no-members:



***
API
***

Anonymisation
-------------

This is the legacy interface. It does not implement the planned DICOM
confidentiality profile. See :doc:`../../background/dicom-deidentification`
for current limitations and the planned transition before sharing output.

.. autofunction:: pymedphys.dicom.anonymise


Dose
----
A suite of functions for manipulating dose in a DICOM context.

.. autofunction:: pymedphys.dicom.zyx_and_dose_from_dataset

.. autofunction:: pymedphys.dicom.depth_dose

.. autofunction:: pymedphys.dicom.profile

.. autofunction:: pymedphys.dicom.dicom_dose_interpolate
