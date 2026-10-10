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

This is the legacy interface. It does not implement a DICOM confidentiality
profile, and each call emits an
:class:`~pymedphys.dicom.AnonymisationLimitationWarning` describing its
limitations; this is not a deprecation. Read its limitations in
:doc:`../../background/dicom-deidentification` before sharing output.

.. autofunction:: pymedphys.dicom.anonymise

.. autoclass:: pymedphys.dicom.AnonymisationLimitationWarning


Dose
----
A suite of functions for manipulating dose in a DICOM context.

.. autofunction:: pymedphys.dicom.zyx_and_dose_from_dataset

.. autofunction:: pymedphys.dicom.depth_dose

.. autofunction:: pymedphys.dicom.profile

.. autofunction:: pymedphys.dicom.dicom_dose_interpolate
