|logo|

.. |logo| image:: https://github.com/pymedphys/pymedphys/raw/ca501275227f190a77e641a75af925d9070952b6/lib/pymedphys/docs/_static/pymedphys_title.svg
    :target: https://docs.pymedphys.com/

.. START_OF_DOCS_IMPORT

**A community effort to develop an open standard library for Medical Physics
in Python. We build high quality, transparent software together via peer review
and open source distribution. Open code is better science.**

|build| |pypi| |python| |license|

.. |build| image:: https://img.shields.io/github/workflow/status/pymedphys/pymedphys/Library
    :target: https://github.com/pymedphys/pymedphys/actions?query=branch%3Amain

.. |pypi| image:: https://img.shields.io/pypi/v/pymedphys
    :target: https://pypi.org/project/pymedphys/

.. |python| image:: https://img.shields.io/pypi/pyversions/pymedphys
    :target: https://pypi.org/project/pymedphys/

.. |license| image:: https://img.shields.io/pypi/l/pymedphys
    :target: https://choosealicense.com/licenses/apache-2.0/


What is PyMedPhys?
==================

PyMedPhys is an open-source Medical Physics python library built by an open
community that values and prioritises code sharing, review, improvement, and
learning from each other. It is inspired by the collaborative work of our
physics peers in astronomy and the `Astropy Project`_. PyMedPhys is available
on `PyPI`_ and `GitHub`_.

PyMedPhys first paper in the Journal of Open Source Software contains more
background information, including a statement of need. You can access the paper
`here <https://joss.theoj.org/papers/10.21105/joss.04555>`_. When referencing
PyMedPhys, please cite this paper as follows:

*Biggs, S., Jennings, M., Swerdloff, S., Chlap, P., Lane, D., Rembish, J.,
McAloney, J., King, P., Ayala, R., Guan, F. and Lambri, N.., (2022).
PyMedPhys: A community effort to develop an open, Python-based standard
library for medical physics applications. Journal of Open Source Software,
7(78), 4555, https://doi.org/10.21105/joss.04555*

.. _`Astropy Project`: http://www.astropy.org/
.. _`PyPI`: https://pypi.org/project/pymedphys/
.. _`GitHub`: https://github.com/pymedphys/pymedphys

Beta level of development
*************************

PyMedPhys is currently within the ``beta`` stage of its life-cycle. It will
stay in this stage until the version number leaves ``0.x.x`` and enters
``1.x.x``. While PyMedPhys is in ``beta`` stage, **no API is guaranteed to be
stable from one release to the next.** In fact, it is very likely that the
entire API will change multiple times before a ``1.0.0`` release. In practice,
this means that upgrading ``pymedphys`` to a new version will possibly break
any code that was using the old version of pymedphys. We try to be abreast of
this by providing details of any breaking changes from one release to the next
within the `Release Notes`_.

Community
**************

PyMedPhys has a `Discourse community <https://pymedphys.discourse.group/>`_
to both help you find your feet using PyMedPhys and to facilitate collaboration
and general discussion. Please reach out over there and we'd love to get to
know you!

Documentation
=============

PyMedPhys can be installed with:

.. code:: bash

    pip install pymedphys[user]

Further user installation instructions can be found in the `Quick Start Guide`_.

The PyMedPhys documentation contains two overarching guides:

1. **The Users Guide**: where you can find instructions to `get started`_ with
   the library and the CLI, in-depth `how-to guides`_ (examples for users) on PyMedPhys' various
   tools, some `background information`_ on individual PyMedPhys projects as
   well as the `Technical Reference`_.

2. **The Contributors Guide**: for those who wish to make new contributions
   to the PyMedPhys library, CLI or app. Here you'll find detailed `workstation
   setup guides`_ to enable contributions, important `repository information`_,
   and some `tips & tricks`_ to overcome common issues.

Development
=============

The PyMedPhys project is managed using `Poetry`_.

After cloning the repository, install the PyMedPhys dependencies and set up pre-commit by running:

.. code:: bash

    poetry install -E all
    poetry run pre-commit install

Run automated tests with:

.. code:: bash

    poetry run pymedphys dev tests


Our Team
========

PyMedPhys is what it is today due to its maintainers and contributors, both
past and present. Here is our team.

Maintainers
***********

* `Simon Biggs`_
    * `Radiotherapy AI`_, Australia

.. _`Simon Biggs`: https://github.com/SimonBiggs

* `Stuart Swerdloff`_
    * `ELEKTA Pty Ltd`_: New Zealand

.. _`Stuart Swerdloff`: https://github.com/sjswerdloff

* `Matthew Jennings`_
    * `Royal Adelaide Hospital`_, Australia

.. _`Matthew Jennings`: https://github.com/Matthew-Jennings

* `Phillip Chlap`_
    * `University of New South Wales`_, Australia
    * `Ingham Institute`_, Australia

.. _`Phillip Chlap`: https://github.com/pchlap


|rai| |sjs| |rah|

Active contributors
****************************

* `Derek Lane`_
    * `ELEKTA AB`_, Houston TX

.. _`Derek Lane`: https://github.com/dg1an3

* `Jake Rembish`_
    * `UT Health San Antonio`_, USA

.. _`Jake Rembish`: https://github.com/rembishj

* `Nicola Lambri`_
    * `IRCCS Humanitas Research Hospital`_, Italy
    * `Humanitas University`_, Italy

.. _`Nicola Lambri`: https://github.com/nlambriICH

* `Cody Crewson`_
    * `Saskatchewan Cancer Agency`_, Canada

.. _`Cody Crewson`: https://github.com/crcrewso

* `Fada Guan`_
    * `Yale University School of Medicine`_, USA

.. _`Fada Guan`: https://github.com/guanfada

|uth|

Past contributors
****************************

* `Matthew Cooper <https://github.com/matthewdeancooper>`_
* `Pedro Martinez <https://github.com/peterg1t>`_
* `Rafael Ayala <https://github.com/ayalalazaro>`_
* `Matthew Sobolewski <https://github.com/msobolewski>`_
* `Paul King <https://github.com/kingrpaul>`_
* `Jacob McAloney <https://github.com/JacobMcAloney>`_

.. |rai| image:: https://github.com/pymedphys/pymedphys/raw/286deacdea2b3af9322796d413d0da6e1d8935a9/logos/rai.png
    :target: `Radiotherapy AI`_

.. |rah| image:: https://github.com/pymedphys/pymedphys/raw/3f8d82fc3b53eb636a75336477734e39fa406110/docs/logos/gosa_200x200.png
    :target: `Royal Adelaide Hospital`_

.. |uth| image:: https://github.com/pymedphys/pymedphys/raw/3f8d82fc3b53eb636a75336477734e39fa406110/docs/logos/UTHSA_logo.png
    :target: `UT Health San Antonio`_

.. |sjs| image:: https://github.com/pymedphys/pymedphys/raw/7e9204656e0468b0843533472553a03a99387386/logos/swerdloff.png
    :target: `Swerdloff Family`_

.. _`Radiotherapy AI`: https://radiotherapy.ai/

.. _`ELEKTA Pty Ltd`: https://www.elekta.com/

.. _`ELEKTA AB`: https://www.elekta.com/

.. _`Royal Adelaide Hospital`: https://www.rah.sa.gov.au/

.. _`University of New South Wales`: https://www.unsw.edu.au/

.. _`South Western Sydney Local Health District`: https://www.swslhd.health.nsw.gov.au/

.. _`Anderson Regional Cancer Center`: https://www.andersonregional.org/services/cancer-care/

.. _`Northern Beaches Cancer Care`: https://www.northernbeachescancercare.com.au/

.. _`University of Calgary`: https://www.ucalgary.ca/

.. _`Tom Baker Cancer Centre`: https://www.ahs.ca/tbcc

.. _`UT Health San Antonio`: https://www.uthscsa.edu/academics/biomedical-sciences/programs/radiological-sciences-phd

.. _`Hospital General Universitario Gregorio Marañón`: https://www.comunidad.madrid/hospital/gregoriomaranon/

.. _`Swerdloff Family`: https://github.com/sjswerdloff

.. _`Ingham Institute`: https://inghaminstitute.org.au/

.. _`IRCCS Humanitas Research Hospital`: https://www.humanitas.net/

.. _`Saskatchewan Cancer Agency`: http://www.saskcancer.ca/

.. _`Humanitas University`: https://www.hunimed.eu/

.. _`Yale University School of Medicine`: https://medicine.yale.edu/

.. END_OF_DOCS_IMPORT

.. _`Release Notes`: ./CHANGELOG.md

.. _`Statement of Need`: https://docs.pymedphys.com/en/latest/statement-of-need.html
.. _`Quick Start Guide`: https://docs.pymedphys.com/en/latest/users/get-started/quick-start.html
.. _`get started`: https://docs.pymedphys.com/en/latest/users/get-started/index.html
.. _`how-to guides`: https://docs.pymedphys.com/en/latest/users/howto/index.html
.. _`background information`: https://docs.pymedphys.com/en/latest/users/background/index.html
.. _`Technical Reference`: https://docs.pymedphys.com/en/latest/users/ref/index.html
.. _`workstation setup guides`: https://docs.pymedphys.com/en/latest/contrib/setups/index.html
.. _`repository information`: https://docs.pymedphys.com/en/latest/contrib/info/index.html
.. _`tips & tricks`: https://docs.pymedphys.com/en/latest/contrib/tips/index.html
.. _`Poetry`: https://python-poetry.org/
