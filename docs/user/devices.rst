Devices Toolbox
================

.. automodule:: pymedphys.devices
    :no-members:


API
---
Collection of tools for reading, writing, manipulating,
and analyzing dose profiles.

<<<<<<< HEAD
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
.. autofunction:: pymedphys.dose.is_even_spaced
.. autofunction:: pymedphys.dose.make_dist_vals
.. autofunction:: pymedphys.dose.get_dist_vals
.. autofunction:: pymedphys.dose.get_dose_vals
.. autofunction:: pymedphys.dose.find_strt_stop
=======
dose_profile : list of tuples [(distance, dose), ...]

>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409
.. autofunction:: pymedphys.devices.read_mapcheck_txt
.. autofunction:: pymedphys.devices.read_profiler_prs
.. autofunction:: pymedphys.dose.resample
.. autofunction:: pymedphys.dose.crossings
.. autofunction:: pymedphys.dose.edges
.. autofunction:: pymedphys.dose.normalise_dose
.. autofunction:: pymedphys.dose.normalise_distance
.. autofunction:: pymedphys.dose.recentre
.. autofunction:: pymedphys.dose.symmetrise
.. autofunction:: pymedphys.dose.get_umbra
.. autofunction:: pymedphys.dose.align_to
.. autofunction:: pymedphys.dose.symmetry
.. autofunction:: pymedphys.dose.flatness
.. autofunction:: pymedphys.dose.is_wedged
.. autofunction:: pymedphys.dose.is_fff

