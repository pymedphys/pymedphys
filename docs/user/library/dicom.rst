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
A suite of functions related to DICOM dataset anonymisation.

.. _`pymedphys.geometry.cubify_cube_definition`:
   geometry.html#pymedphys.geometry.cubify_cube_definition

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
