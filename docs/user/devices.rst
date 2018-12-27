Devices Toolbox
================

.. automodule:: pymedphys.devices
    :no-members:

Tools to read, write, adjust, & evaluate dose profiles.

Variables
---------------------------------------------------------

    +---------------------------------+-------------------------------------------+
    | dose_prof                       | [(dist, dose), ...]                       |
    +---------------------------------+-------------------------------------------+
    | dist_vals                       | [dist, dist, ...]                         |
    +---------------------------------+-------------------------------------------+
    | dist _strt, _stop, _step        | float start, stop, step                   |
    +---------------------------------+-------------------------------------------+
    | dose_vals                       | [dose, dose, ...]                         |
    +---------------------------------+-------------------------------------------+
    | dose, dose_step                 | float, in cGy                             |
    +---------------------------------+-------------------------------------------+
    | symmetry, flatness              | float, absolute                           |
    +---------------------------------+-------------------------------------------+

Distance Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.make_dist_vals
    .. autofunction:: pymedphys.dose.get_dist_vals

Dose Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.make_dose_vals
    .. autofunction:: pymedphys.dose.get_dose_vals

Profile Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.make_dose_prof
    .. autofunction:: pymedphys.dose.is_even_spaced
    .. autofunction:: pymedphys.dose.make_pulse_dose_prof
    .. autofunction:: pymedphys.dose.resample
    .. autofunction:: pymedphys.dose.align_to
    .. autofunction:: pymedphys.dose.is_wedged
    .. autofunction:: pymedphys.dose.is_fff

Slicing Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.find_strt_stop
    .. autofunction:: pymedphys.dose.slice_dose_prof
    .. autofunction:: pymedphys.dose.find_edges
    .. autofunction:: pymedphys.dose.find_umbra

Scaling Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.find_dose
    .. autofunction:: pymedphys.dose.find_dists
    .. autofunction:: pymedphys.dose.norm_dose_vals
    .. autofunction:: pymedphys.dose.norm_dist_vals
    .. autofunction:: pymedphys.dose.cent_dose_prof

Flatness & Symmetry Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.flatness
    .. autofunction:: pymedphys.dose.symmetry
    .. autofunction:: pymedphys.dose.make_dose_prof_sym

Device Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.devices.read_mapcheck_txt
    .. autofunction:: pymedphys.devices.read_profiler_prs


