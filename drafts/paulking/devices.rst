Profile Device Toolbox
======================

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

Device Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.devices.read_mapcheck_txt
    .. autofunction:: pymedphys.devices.read_profiler_prs

Profile Functions
---------------------------------------------------------

    .. autofunction:: pymedphys.dose.pulse
    .. autofunction:: pymedphys.dose.resample
    .. autofunction:: pymedphys.dose.overlay
    .. autofunction:: pymedphys.dose.edges
    .. autofunction:: pymedphys.dose.normalise_dose
    .. autofunction:: pymedphys.dose.normalise_distance
    .. autofunction:: pymedphys.dose.recentre
    .. autofunction:: pymedphys.dose.flatness
    .. autofunction:: pymedphys.dose.symmetry
    .. autofunction:: pymedphys.dose.symmetrise
    .. autofunction:: pymedphys.dose.is_wedged
