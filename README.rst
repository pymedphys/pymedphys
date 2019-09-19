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

Bringing together Medical Physicists to create quality transparent software at
a price affordable by all our peers, no matter what country they are from (free).

PyMedPhys, a community powered by git and continuous integration. A place to
share, review, improve, and transparently learn off of each other’s code. 
It is a library of tools that we all have access to and, because of its
`license`_, will all have access to whatever it becomes in the future.
It is inspired by the collaborative work of our physics peers in
astronomy and their `Astropy Project`_.

.. _`Astropy Project`: http://www.astropy.org/

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

.. _`Matthew Jennings`: https://github.com/Matthew-Jennings


* `Phillip Chlap`_
    * `University of New South Wales`_, Australia
    * `South Western Sydney Local Health District`_, Australia

.. _`Phillip Chlap`: https://github.com/pchlap


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


* `Pedro Martinez`_
    * `University of Calgary`_, Canada
    * `Tom Baker Cancer Centre`_, Canada

.. _`Pedro Martinez`: https://github.com/peterg1t


|rccc| |rah| |jarmc| |nbcc| |uoc|


.. |rccc| image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/rccc_200x200.png
    :target: `Riverina Cancer Care Centre`_

.. |rah| image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/gosa_200x200.png
    :target: `Royal Adelaide Hospital`_

.. |jarmc| image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/jarmc_200x200.png
    :target: `Anderson Regional Cancer Center`_

.. |nbcc| image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/nbcc_200x200.png
    :target: `Northern Beaches Cancer Care`_

.. |uoc| image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/uoc_200x200.png
    :target: `University of Calgary`_

.. _`Riverina Cancer Care Centre`: http://www.riverinacancercare.com.au/

.. _`Royal Adelaide Hospital`: http://www.rah.sa.gov.au/

.. _`University of New South Wales`: https://www.unsw.edu.au/

.. _`South Western Sydney Local Health District`: https://www.swslhd.health.nsw.gov.au/

.. _`Anderson Regional Cancer Center`: http://www.andersonregional.org/CancerCenter.aspx

.. _`Northern Beaches Cancer Care`: http://www.northernbeachescancercare.com.au/

.. _`University of Calgary`: http://www.ucalgary.ca/

.. _`Tom Baker Cancer Centre`: https://www.ahs.ca/tbcc


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
