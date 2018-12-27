Devices Toolbox
================

.. automodule:: pymedphys.devices
    :no-members:


API
---
Collection of tools for reading, writing, manipulating,
and analyzing dose profiles.

Data Types
----------
    dose_prof : list of tuples
        [(dist, dose), ...]
    dist_vals : list
     [dist, dist, ...]
    dose_vals : list
        [dose, dose, ...]
    dist : float
        +/- distance from CAX
    dose: float
        dose in cGy, eg 100.0
    dist_step: float
        distance increment in cm, eg 0.1
    dose_step: float
        dose increment in cGy, eg 0.001

Functions
---------

.. autofunction:: pymedphys.dose.make_dist_vals
.. autofunction:: pymedphys.dose.make_dose_vals
.. autofunction:: pymedphys.dose.get_dist_vals
.. autofunction:: pymedphys.dose.get_dose_vals
.. autofunction:: pymedphys.dose.find_strt_stop
.. autofunction:: pymedphys.dose.is_even_spaced
.. autofunction:: pymedphys.dose.make_dose_prof
.. autofunction:: pymedphys.dose.find_dose
.. autofunction:: pymedphys.dose.find_dists
.. autofunction:: pymedphys.dose.slice_dose_prof
.. autofunction:: pymedphys.dose.find_umbra
.. autofunction:: pymedphys.dose.find_edges
.. autofunction:: pymedphys.dose.norm_dist_vals
.. autofunction:: pymedphys.dose.cent_dose_prof
.. autofunction:: pymedphys.dose.make_dose_prof_sym
.. autofunction:: pymedphys.dose.symmetry
.. autofunction:: pymedphys.dose.flatness

.. autofunction:: pymedphys.devices.read_mapcheck_txt
.. autofunction:: pymedphys.devices.read_profiler_prs
.. autofunction:: pymedphys.dose.resample
.. autofunction:: pymedphys.dose.norm_dose_vals
.. autofunction:: pymedphys.dose.get_umbra
.. autofunction:: pymedphys.dose.align_to
.. autofunction:: pymedphys.dose.is_wedged
.. autofunction:: pymedphys.dose.is_fff

