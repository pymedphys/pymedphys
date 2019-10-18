How to use the electron factors module
======================================

This is how to is currently a stub, however it does mention the need to install
shapely to use the electron factors module.



Installing shapely
==================

The ``electronfactors`` module makes use of the ``GEOS`` based package
``shapely``.

On MacOS or Linux simply running ``pip install shapely`` should be sufficient.

At this current point in time ``shapely`` cannot be installed directly from
pip on Windows. Instead you will be required to install shapely by downloading
the wheel from <https://www.lfd.uci.edu/~gohlke/pythonlibs/#shapely> and then
running the following command substituting in the name of the file you
downloaded:

.. code:: bash

    pip install ./Shapely‑1.6.4.post2‑cp37‑cp37m‑win_amd64.whl
