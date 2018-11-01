Installation
------------

To install use the `Anaconda Python distribution`_ with the
`conda-forge channel`_

.. _`Anaconda Python distribution`: https://www.continuum.io/anaconda-overview

.. _`conda-forge channel`: https://conda-forge.org/

.. code:: bash

    conda config --add channels conda-forge
    conda install pymedphys

You can of course also use pip to install, but you may have trouble with some
of the dependencies without conda

.. code:: bash

    pip install pymedphys

To run a development install, which may often be required during the alpha
development stage, clone this repository and then use pip

.. code:: bash

    git clone https://gitlab.com/pymedphys/pymedphys.git
    cd pymedphys
    pip install -e .