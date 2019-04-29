############
DICOM Module
############

*******
Summary
*******

.. automodule:: pymedphys_dicom.dicom
    :no-members:

|

***
API
***

General
-------
A suite of functions that apply DICOM datasets of any modality

.. _`pymedphys.geometry.cubify_cube_definition`:
   geometry.html#pymedphys.geometry.cubify_cube_definition

.. autofunction:: pymedphys.dicom.anonymise_dataset

.. autofunction:: pymedphys.dicom.anonymise_file

.. autofunction:: pymedphys.dicom.anonymise_directory

.. autofunction:: pymedphys.dicom.is_anonymised_dataset

.. autofunction:: pymedphys.dicom.is_anonymised_file

.. autofunction:: pymedphys.dicom.is_anonymised_directory

|

RT Dose
-------
A suite of functions that apply to DICOM RT Dose datasets

.. autofunction:: pymedphys.dicom.extract_iec_patient_xyz

.. autofunction:: pymedphys.dicom.extract_iec_fixed_xyz

.. autofunction:: pymedphys.dicom.extract_dicom_patient_xyz

.. autofunction:: pymedphys.dicom.dose_from_dataset

|

RT Structure
------------
A suite of functions that apply to DICOM RT Structure sets

.. autofunction:: pymedphys.dicom.get_structure_aligned_cube

|

Multiple DICOM Modality Combinations
------------------------------------
A suite of functions that apply to some combination of two or more different
DICOM modalities

.. autofunction:: pymedphys.dicom.find_dose_within_structure

.. autofunction:: pymedphys.dicom.create_dvh

