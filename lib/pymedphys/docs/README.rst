|logo|

.. |logo| image:: https://github.com/pymedphys/pymedphys/raw/ca501275227f190a77e641a75af925d9070952b6/lib/pymedphys/docs/_static/pymedphys_title.svg
    :target: https://docs.pymedphys.com/

.. START_OF_DOCS_IMPORT

**A community effort to develop an open standard library for Medical Physics
in Python. We build high quality, transparent software together via peer review
and open source distribution. Open code is better science.**

|build| |pypi| |python| |license|

.. |build| image:: https://img.shields.io/github/workflow/status/pymedphys/pymedphys/Library
    :target: https://github.com/pymedphys/pymedphys/actions

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

If you'd like more details around installing PyMedPhys go to the
`getting started`_ page within the docs.

The PyMedPhys documentation is split into four categories:

1. `Library Users Guide`_: for those building their own Python apps, scripts
   and other tools who wish to incorporate elements of the PyMedPhys library.
2. `CLI Users Guide`_: for those who wish to use PyMedPhys' ready-made command
   line interface (e.g. to help automate existing workflows with minimal
   programming).
3. `Contributors Guide`_: for those who wish to make new contributions to
   either the PyMedPhys library or the PyMedPhys app.
4. `General`_: Material that may apply to any visitor to PyMedPhys.


Our Team
========

PyMedPhys is what it is today due to its maintainers and contributors, both past
and present. Here is our team.

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


|sjs| |rah|

Active contributors
****************************

* `Phillip Chlap`_
    * `University of New South Wales`_, Australia
    * `Ingham Institute`_, Australia

.. _`Phillip Chlap`: https://github.com/pchlap

* `Derek Lane`_
    * `ELEKTA AB`_, Houston TX

.. _`Derek Lane`: https://github.com/dg1an3

* `Jake Rembish`_
    * `UT Health San Antonio`_, USA

.. _`Jake Rembish`: https://github.com/rembishj


|uth|

Past contributors
****************************

* `Matthew Cooper <https://github.com/matthewdeancooper>`_
* `Pedro Martinez <https://github.com/peterg1t>`_
* `Rafael Ayala <https://github.com/ayalalazaro>`_
* `Matthew Sobolewski <https://github.com/msobolewski>`_
* `Paul King <https://github.com/kingrpaul>`_
* `Jacob McAloney <https://github.com/JacobMcAloney>`_


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

.. END_OF_DOCS_IMPORT

.. _`getting started`: https://docs.pymedphys.com/lib/howto/get-started.html

.. _`Release Notes`: ./CHANGELOG.md

.. _`Library Users Guide`: https://docs.pymedphys.com/lib/index.html
.. _`CLI Users Guide`: https://docs.pymedphys.com/cli/index.html
.. _`Contributors Guide`: https://docs.pymedphys.com/contrib/index.html
.. _`General`: https://docs.pymedphys.com/general/index.html
