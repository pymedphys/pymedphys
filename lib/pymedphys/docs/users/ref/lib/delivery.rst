Delivery
========

``pymedphys.Delivery`` stores cumulative monitor units and collimation/angle
control points in one representation. Use the
:doc:`delivery task guide <../../tasks/delivery>` for a synthetic MetersetMap,
source selection, units, and interpretation. The class does not retain patient
identity, source timestamps, or leaf-pair widths.

Construction and fields
-----------------------

.. autoclass:: pymedphys.Delivery

The constructor takes ``monitor_units, gantry, collimator, mlc, jaw``.
Array-like inputs become immutable nested tuples. For ``N`` control points and
``L`` leaf pairs:

.. list-table::
   :header-rows: 1

   * - Field
     - Shape
     - Meaning
   * - ``monitor_units`` / ``mu``
     - ``(N,)``
     - Cumulative monitor units.
   * - ``gantry``, ``collimator``
     - ``(N,)``
     - Angles in degrees in the adapter's common convention.
   * - ``mlc``
     - ``(N, L, 2)``
     - Opposing bank positions in mm at isocentre, in bipolar coordinates.
   * - ``jaw``
     - ``(N, 2)``
     - Opposing jaw positions in mm at isocentre, in bipolar coordinates.

Keep arrays aligned by control point. Positive positions open each side away
from the central axis; signed values can represent crossing it. Provide the
actual leaf-pair widths separately for a MetersetMap calculation.

.. autoattribute:: pymedphys.Delivery.mu

Source adapters
---------------

.. automethod:: pymedphys.Delivery.from_dicom

.. automethod:: pymedphys.Delivery.from_trf

``from_trf`` reads an Elekta Agility TRF and extracts actual cumulative MU,
angles, MLC, and jaws. See :doc:`trf` for the decoded tables.

.. automethod:: pymedphys.Delivery.from_icom

``icom_stream`` is decompressed iCOM bytes, not a filename. Read an archived
``.xz`` file with ``lzma.open(path, "rb")`` first.

.. automethod:: pymedphys.Delivery.from_monaco

``tel_path`` is a Monaco raw plan ``tel.1`` path. This parser is oriented to
Elekta Agility data; it is not a general RT Plan importer.

.. automethod:: pymedphys.Delivery.from_mosaiq

``field_id`` is the internal Mosaiq ``TxField.FLD_ID``. It is not the displayed
field label or a patient identifier. Use an authorised connection and check
the returned field's control points.

Combining and calculating
-------------------------

.. automethod:: pymedphys.Delivery.combine

``combine(delivery_a, delivery_b, ...)`` constructs a combined Delivery.
At least one delivery is required.

.. automethod:: pymedphys.Delivery.merge

``delivery_a.merge(delivery_b, ...)`` concatenates control points and derives
cumulative MU from non-negative increments. Negative differences, including
MU resets between deliveries, are clipped to zero. Confirm starting MU and
totals for the source records before combining them.

.. automethod:: pymedphys.Delivery.metersetmap

With no gantry selection, the result is one combined two-dimensional array.
With multiple selected angles, it is a list of arrays; ``output_always_list``
forces a list even for one result. Explicit ``gantry_angles`` must be iterable.
The gantry selection expects each selected angular block to be contiguous;
separated beams at the same angle are not fully supported. The geometry
arguments follow :func:`pymedphys.metersetmap.calculate`.

.. automethod:: pymedphys.Delivery.to_dicom

This updates a compatible RT Plan template; it does not create every required
DICOM attribute from delivery data. Check fraction-group selection, beam
matching, machine details, and resulting references independently.

Compatibility methods
----------------------

.. automethod:: pymedphys.Delivery.from_logfile

``from_logfile`` is deprecated in favour of ``from_trf``.

.. automethod:: pymedphys.Delivery.mudensity

``mudensity`` is deprecated in favour of ``metersetmap``. New examples use the
current names; no removal date is asserted here.
