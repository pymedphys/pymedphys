PyMedPhys
=========

Description
-----------
Designed to be the Astropy for Medical Physicists.


A range of Python modules encompased under the PyMedPhys package, designed to
be built upon for Medical Physics applications. Work in progress documentation
for this package is available at https://pymedphys.com.

This package is available on pypi at https://pypi.org/project/pymedphys/,
conda at https://anaconda.org/conda-forge/pymedphys and GitLab at
https://gitlab.com/pymedphys/pymedphys.

Our Team
--------

We want you on this list. We want you, clinical Medical Physicist, to join our
team. Even if all you feel comfortable contributing to is documentation.

The aim of PyMedPhys is that it will be developed by an open community of
contributors. We use a shared copyright model that enables all contributors
to maintain the copyright on their contributions. All code is licensed under
the AGPLv3+ with additional terms from the Apache-2.0 license.

PyMedPhys' current maintainers listed in alphabetical order, with affilliation,
and main area of contribution:

* `Matthew Sobolewski`_, `Cancer Care Associates, Australia`_
* `Simon Biggs`_, `Cancer Care Associates, Australia`_

.. _`Cancer Care Associates, Australia`: http://cancercare.com.au/

.. _`Matthew Sobolewski`: https://github.com/msobolewski

.. _`Simon Biggs`: https://github.com/SimonBiggs

Beta stage development
----------------------

These libraries are currently under beta level development. As with any code
where the results matter, be cautious with the code in this library.

Throughout the lifetime of this library the following disclaimer will always
hold:

    In no event and under no legal theory, whether in tort
    (including negligence), contract, or otherwise, unless required by
    applicable law (such as deliberate and grossly negligent acts) or agreed
    to in writing, shall any Contributor be liable to You for damages,
    including any direct, indirect, special, incidental, or consequential
    damages of any character arising as a result of this License or out of
    the use or inability to use the Work (including but not limited to damages
    for loss of goodwill, work stoppage, computer failure or malfunction, or
    any and all other commercial damages or losses), even if such Contributor
    has been advised of the possibility of such damages.


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

## Contributing

To contribute to `pymedphys` you will need a working knowledge of git processes.
The [`contributing.md`](./contributing.md) document provides links to some tutorials that may help get you up to speed.
