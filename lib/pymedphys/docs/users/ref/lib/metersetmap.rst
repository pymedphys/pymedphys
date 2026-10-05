###########
MetersetMap
###########

*******
Summary
*******

.. automodule:: pymedphys.metersetmap
    :no-members:

See :doc:`../../tasks/delivery` for input shapes, geometry, and a synthetic
open-field calculation, and :doc:`../../tasks/apps` for app reports.


***
API
***

.. autofunction:: pymedphys.metersetmap.calculate

.. autofunction:: pymedphys.metersetmap.grid

.. autofunction:: pymedphys.metersetmap.display

Limitations notice
------------------

.. py:data:: pymedphys.metersetmap.WARNING_MESSAGE

   A string containing the module's warning about the limits of MetersetMap
   QA. It can be displayed in applications using these functions. MetersetMap
   is an exposure map in monitor units, not calculated or measured dose, and
   reported logfile positions need not equal physical leaf/jaw positions.
