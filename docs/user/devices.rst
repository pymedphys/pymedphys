Devices Toolbox
================

.. automodule:: pymedphys.devices
    :no-members:

Tools to read, write, adjust, & evaluate dose profiles.

Variables
---------------------------------------------------------

    +--------------------------------------+--------------------------------------+
    | dose_prof                            | [(dist, dose), ...]                  |
    +--------------------------------------+--------------------------------------+
    | dist_vals                            | [dist, dist, ...]                    |
    +--------------------------------------+--------------------------------------+
    | dist_strt, dist_stop, dist_step      | float                                |
    +--------------------------------------+--------------------------------------+
    | dose_vals                            | [dose, dose, ...]                    |
    +--------------------------------------+--------------------------------------+
    | dose, dose_step                      | float, in cGy                        |
    +--------------------------------------+--------------------------------------+
    | symmetry, flatness                   | float, absolute                      |
    +--------------------------------------+--------------------------------------+


Profile Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.shift_dose_prof
    .. autofunction:: pymedphys.dose.make_pulse_dose_prof
    .. autofunction:: pymedphys.dose.resample
    .. autofunction:: pymedphys.dose.align_to
    .. autofunction:: pymedphys.dose.is_wedged
    .. autofunction:: pymedphys.dose.find_edges
    .. autofunction:: pymedphys.dose.norm_dose_vals
    .. autofunction:: pymedphys.dose.norm_dist_vals
    .. autofunction:: pymedphys.dose.cent_dose_prof
    .. autofunction:: pymedphys.dose.flatness
    .. autofunction:: pymedphys.dose.symmetry
    .. autofunction:: pymedphys.dose.symmetrise

Device Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.devices.read_mapcheck_txt
    .. autofunction:: pymedphys.devices.read_profiler_prs


