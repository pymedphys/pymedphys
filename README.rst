=========
PyMedPhys
=========

|build| |pypi| |conda| |python| |license|

.. |build| image:: https://dev.azure.com/pymedphys/pymedphys/_apis/build/status/pymedphys.pymedphys?branchName=master
    :target: https://dev.azure.com/pymedphys/pymedphys/_build/latest?definitionId=4&branchName=master

.. |pypi| image:: https://img.shields.io/pypi/v/pymedphys.svg
    :target: https://pypi.org/project/pymedphys/

.. |conda| image:: https://img.shields.io/conda/vn/conda-forge/pymedphys.svg
    :target: https://anaconda.org/conda-forge/pymedphys/

.. |python| image:: https://img.shields.io/pypi/pyversions/pymedphys.svg
    :target: https://pypi.org/project/pymedphys/

.. |license| image:: https://img.shields.io/pypi/l/pymedphys.svg
    :target: https://choosealicense.com/licenses/agpl-3.0/


.. START_OF_ABOUT_IMPORT

PyMedPhys aims to be a Medical Physics open source `monorepo`_ where we
can all store, review, use, and learn off of each other's code. It is a
library of tools that we all have access to and, because of its
`license`_, will all have access to whatever it becomes in the future.
It is inspired by the collaborative work of our physics peers in
astronomy and their `Astropy Project`_.

It is structured and glued together with Python, but certainly not
limited to one programming language. A great place to begin sharing is
the labs, a range of experimental modules where you can learn to use git
and begin the process of code sharing and review. For example, feel free
to submit to the labs your most useful MatLab scripts which we can help
you glue together with Python using `oct2py`_.

.. _`oct2py`: http://blink1073.github.io/oct2py/

.. _`Astropy Project`: http://www.astropy.org/

.. _`monorepo`: https://cacm.acm.org/magazines/2016/7/204032-why-google-stores-billions-of-lines-of-code-in-a-single-repository/fulltext

.. _`license`: https://choosealicense.com/licenses/agpl-3.0/


This package is available on `PyPI`_, `GitHub`_ and `conda-forge`_. You
can access the Documentation `here <https://pymedphys.com>`__.


.. _`PyPI`: https://pypi.org/project/pymedphys/
.. _`GitHub`: https://github.com/pymedphys/pymedphys
.. _`conda-forge`: https://anaconda.org/conda-forge/pymedphys


PyMedPhys is currently within the ``beta`` stage of its lifecycle. It will
stay in this stage until the version number leaves ``0.x.x`` and enters
``1.x.x``. While PyMedPhys is in ``beta`` stage, **no API is guaranteed to be
stable from one release to the next.** In fact, it is very likely that the
entire API will change multiple times before a ``1.0.0`` release. In practice,
this means that upgrading ``pymedphys`` to a new version will possibly break
any code that was using the old version of pymedphys. We try to be abreast of
this by providing details of any breaking changes from one release to the next
within the `Release Notes
<http://pymedphys.com/getting-started/changelog.html>`__.


Our Team
--------

PyMedPhys is what it is today due to its maintainers and developers. The
currently active developers and maintainers of PyMedPhys are given below
along with their affiliation:

* `Simon Biggs`_
    * `Riverina Cancer Care Centre`_, Australia

.. _`Simon Biggs`: https://github.com/SimonBiggs


* `Matthew Jennings`_
    * `Royal Adelaide Hospital`_, Australia

.. _`Matthew Jennings`: https://github.com/centrus007


* `Paul King`_
    * `Anderson Regional Cancer Center`_, United States

.. _`Paul King`: https://github.com/kingrpaul


* `Matthew Sobolewski`_
    * `Riverina Cancer Care Centre`_, Australia
    * `Northern Beaches Cancer Care`_, Australia

.. _`Matthew Sobolewski`: https://github.com/msobolewski


* `Jacob McAloney`_
    * `Riverina Cancer Care Centre`_, Australia

.. _`Jacob McAloney`: https://github.com/JacobMcAloney

|

.. image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/RCCC_logo.png
    :target: `Riverina Cancer Care Centre`_
    :align: center
    :width: 400 px

|

.. image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/GOSA_logo2.png
    :target: `Royal Adelaide Hospital`_
    :align: center
    :width: 200 px

|

.. image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/JARMC_logo.png
    :target: `Anderson Regional Cancer Center`_
    :align: center
    :width: 400 px

|

.. image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/NBCCC_logo.png
    :target: `Northern Beaches Cancer Care`_
    :align: center
    :width: 400 px

|

.. _`Riverina Cancer Care Centre`: http://www.riverinacancercare.com.au/

.. _`Royal Adelaide Hospital`: http://www.rah.sa.gov.au/

.. _`Anderson Regional Cancer Center`: http://www.andersonregional.org/CancerCenter.aspx

.. _`Northern Beaches Cancer Care`: http://www.northernbeachescancercare.com.au/


We want you on this list. We want you, whether you are a  clinical
Medical Physicist, PhD or Masters student, researcher, or even just
someone with an interest in Python to join our team. We want you if you
have a desire to create and validate a toolbox we can all use to improve
how we care for our patients.

The aim of PyMedPhys is that it will be developed by an open community
of contributors. We use a shared copyright model that enables all
contributors to maintain the copyright on their contributions. All code
is licensed under the AGPLv3+ with additional terms from the Apache-2.0
license.


.. END_OF_ABOUT_IMPORT


Beta stage development
----------------------

These libraries are currently under beta level development.
Be prudent with the code in this library.

Throughout the lifetime of this library the following disclaimer will
always hold:

    In no event and under no legal theory, whether in tort (including
    negligence), contract, or otherwise, unless required by applicable
    law (such as deliberate and grossly negligent acts) or agreed to in
    writing, shall any Contributor be liable to You for damages,
    including any direct, indirect, special, incidental, or
    consequential damages of any character arising as a result of this
    License or out of the use or inability to use the Work (including
    but not limited to damages for loss of goodwill, work stoppage,
    computer failure or malfunction, or any and all other commercial
    damages or losses), even if such Contributor has been advised of the
    possibility of such damages.

Where the definition of License is taken to be the
AGPLv3+ with additional terms from the Apache 2.0. The definitions of
Contributor, You, and Work are as defined within the Apache 2.0 license.


.. END_OF_FRONTPAGE_IMPORT


Installation
------------

For instructions on how to install see the documentation at
https://pymedphys.com/getting-started/installation.html.


Contributing
------------

See the contributor documentation at
https://pymedphys.com/developer/contributing.html
if you wish to create and validate open source Medical Physics tools
together.
