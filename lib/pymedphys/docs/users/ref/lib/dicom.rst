#####
DICOM
#####

*******
Summary
*******

.. automodule:: pymedphys.dicom
    :no-members:

See :doc:`../../tasks/dicom` for synthetic dose/contour examples, header
editing, local transfer, and output checks.



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

Contours
--------

.. autofunction:: pymedphys.dicom.merge_contours

``roi_contour_sequence`` is one ``ROIContourSequence`` item containing a
``ContourSequence``. The default ``inplace=False`` returns a shallow copy;
with pydicom datasets its element mapping can remain shared and replacing the
contours can also change the input. Pass ``copy.deepcopy(item)`` when the source
must be preserved. ``inplace=True`` replaces that item's contours and returns
``None``.
The implementation unions supported axial ``CLOSED_PLANAR`` polygons with a
common referenced image per plane, writes exterior rings, and rounds
coordinates to 0.1 mm. Holes are not preserved. Unexpected contour fields,
non-constant z, unsupported geometric types, and inconsistent image references
raise ``ValueError``. Check topology and references after merging.
