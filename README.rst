PyMedPhys
=========

Description
-----------
Designed to be the astropy for Medical Physicists.


A range of python modules encompased under the pymedphys package, designed to
be built upon for Medical Physics applications. Work in progress documentation
for this package is available at https://pymedphys.com.

This package is available on pypi at https://pypi.org/project/pymedphys/
and GitLab at https://gitlab.com/pymedphys/pymedphys.

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

* `Matthew Sobolewski`_, `Northern Beaches Cancer Care, Australia`_

.. image:: docs/logos/NBCCC_logo.png
    :target: `Northern Beaches Cancer Care, Australia`_

.. _`Matthew Sobolewski`: https://github.com/msobolewski

.. _`Northern Beaches Cancer Care, Australia`: http://www.northernbeachescancercare.com.au/

* `Simon Biggs`_, `Riverina Cancer Care Centre, Australia`_

.. image:: docs/logos/RCCC_logo.png
    :target: `Riverina Cancer Care Centre, Australia`_

.. _`Simon Biggs`: https://github.com/SimonBiggs

.. _`Riverina Cancer Care Centre, Australia`: http://www.riverinacancercare.com.au/


Beta stage development
----------------------

These libraries are currently under beta level development.
Be prudent with the code in this library.

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


Contributing
------------

See the contributor documentation at https://pymedphys.com/en/latest/contributing.html
if you wish to create and validate open source Medical Physics tools together.
