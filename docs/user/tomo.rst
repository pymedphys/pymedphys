Tomotherapy Toolbox
===================

.. automodule:: pymedphys.tomo
    :no-members:

Variables
---------

    sinogram: list of lists of floats

    [ projection = [ leaf-open-time,
                     leaf-open-time, ... *64]
      projection = [ leaf-open-time,
                     leaf-open-time, ... *64]
      ... *num_projections ]

API
---

.. autofunction:: pymedphys.tomo.read_sin_csv_file

.. autofunction:: pymedphys.tomo.read_sin_bin_file

.. autofunction:: pymedphys.tomo.crop_sinogram

.. autofunction:: pymedphys.tomo.unshuffle

.. autofunction:: pymedphys.tomo.make_histogram

.. autofunction:: pymedphys.tomo.find_modulation_factor



