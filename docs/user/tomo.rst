Tomotherapy Toolbox
===================

.. automodule:: pymedphys.tomo
    :no-members:

Variables
---------

    +------+----------------+----------------------+------------------+
    | sng  | sinogram       | [ proj, proj, ... ]  | 0 < len < np.inf |
    +------+----------------+----------------------+------------------+
    | prj  | projection     | [ lft, lft, ... ]    | len=64           |
    +------+----------------+----------------------+------------------+
    | lft  | leaf open time | float                | >= 0.0           |
    +------+----------------+----------------------+------------------+

API
---

.. autofunction:: pymedphys.tomo.read_sng_csv_file

.. autofunction:: pymedphys.tomo.read_sng_bin_file

.. autofunction:: pymedphys.tomo.crop_sinogram

.. autofunction:: pymedphys.tomo.unshuffle

.. autofunction:: pymedphys.tomo.make_histogram

.. autofunction:: pymedphys.tomo.find_modulation_factor



