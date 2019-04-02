=====================================
Elekta Logfiles Decoding and Indexing
=====================================

Project aim
-----------
The aim of this project is to have an automated machine record based delivery
check between the treatment planning system, the information system, and the
Linac for every patient and fraction.


.. WARNING::

   **It is not the intent of this project to replace patient specific QA
   measurements**. Some reasons this is likely not a sufficient replacement:

   * Linac reported MLC and Jaw positions are not independent from the machine and
     a fault resulting in mispositioning of the collimation may not be reported
     within the logfiles.
   * The treatment planning system beam models (as well as potentially any
     independent calculation software) may not accurately model the MLCs [1]_, and
     therefore, checking leaf positon, without a dose measurement, may not be
     sufficient verification.


Overview
--------
The logfiles themselves are extracted from the Linac diagnostics backups, they
are then indexed according to patient name and ID using the delivery record within
Mosaiq. This extracting and indexing is set to run at a regular interval.

Once these logfiles are indexed they can be decoded into csv format for human
reading, or an MU Density can be calculated, or they can be mapped to a DICOM
file for the recalculation of dose.


Retrieving Logfiles from the Linac
----------------------------------


Indexing the Logfiles
---------------------


Orchestrating the process
-------------------------


Decoding Logfiles
-----------------


Including MU Density
--------------------


Mapping logfiles to RT DICOM plan
---------------------------------


Setting up a system to span multiple sites
------------------------------------------



References
----------

.. [1] Gholampourkashi, Sara, et al. "Monte Carlo and analytic modeling of an Elekta
   Infinity linac with Agility MLC: Investigating the significance of accurate
   model parameters for small radiation fields."
   *Journal of Applied Clinical Medical Physics* 20.1 (2019): 55-67. https://doi.org/10.1002/acm2.12485.