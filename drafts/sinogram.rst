Sinogram Toolbox
===================

.. automodule:: pymedphys.sinogram
    :no-members:

Variables
---------

    +------+----------------+----------------------+------------------+
    | sng  | sinogram       | [ proj, proj, ... ]  | 0 < len < np.inf |
    +------+----------------+----------------------+------------------+
    | prj  | projection     | [ lft, lft, ... ]    | len==64          |
    +------+----------------+----------------------+------------------+
    | lft  | leaf open time | float                | >= 0.0           |
    +------+----------------+----------------------+------------------+

API
---

.. autofunction:: pymedphys.sinogram.read_csv_file

.. autofunction:: pymedphys.sinogram.read_bin_file

.. autofunction:: pymedphys.sinogram.crop

.. autofunction:: pymedphys.sinogram.unshuffle

.. autofunction:: pymedphys.sinogram.make_histogram

.. autofunction:: pymedphys.sinogram.find_modulation_factor



