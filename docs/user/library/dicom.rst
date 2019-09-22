############
DICOM Module
############

*******
Summary
*******

.. automodule:: pymedphys_dicom.dicom
    :no-members:



***
API
***

Anonymisation
-------------
A suite of functions related to DICOM anonymisation.

You can find the list of DICOM keywords that are included in default
anonymisation `here <https://github.com/pymedphys/pymedphys/blob/master/packages/pymedphys_dicom/src/pymedphys_dicom/dicom/identifying_keywords.json>`__.
These were drawn from `DICOM Supp 142 <https://www.dicomstandard.org/supplements/>`__

None of these functions anonymise UIDs, but plans are afoot to support this.

**We do not yet claim conformance to any DICOM Application Level
Confidentiality Profile**, but plan to be in a position to do so in the
not-to-distant future.

.. autofunction:: pymedphys.dicom.anonymise_dataset

.. autofunction:: pymedphys.dicom.anonymise_file

.. autofunction:: pymedphys.dicom.anonymise_directory

.. autofunction:: pymedphys.dicom.is_anonymised_dataset

.. autofunction:: pymedphys.dicom.is_anonymised_file

.. autofunction:: pymedphys.dicom.is_anonymised_directory



Coordinates
-----------
A suite of functions assist with coordinate handling for DICOM datasets of a
relevant modality, such as 'CT' or 'RTDOSE'.

.. autofunction:: pymedphys.dicom.coords_from_xyz_axes

.. autofunction:: pymedphys.dicom.xyz_axes_from_dataset



Dose
-------
A suite of functions for manipulating dose in a DICOM context.

.. autofunction:: pymedphys.dicom.create_dvh

.. autofunction:: pymedphys.dicom.dose_from_dataset

.. autofunction:: pymedphys.dicom.find_dose_within_structure



RT Structure
------------
A suite of functions that apply specifically to DICOM RT Structure sets

.. autofunction:: pymedphys.dicom.get_structure_aligned_cube
