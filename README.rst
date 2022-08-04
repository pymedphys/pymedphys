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

Statement of need
*****************

Medical radiation applications are subject to fast-paced technological
advancements. This is particularly true in the field of radiation oncology,
where the implementation of increasingly sophisticated technologies requires
increasingly complex processes to maintain the improving standard of care. To
help address this challenge, software tools that improve the quality, safety
and efficiency of clinical tasks are increasingly being developed in-house.
Commercial options are often prohibitively expensive or insufficiently tailored
to an individual clinic's needs. On the other hand, in-house development
efforts are often limited to a single institution. Similar tools that could
otherwise be shared are instead "reinvented" in clinics worldwide on a routine
basis. Moreover, individual institutions typically lack the personnel and
resources to incorporate simple aspects of good development practice or to
properly maintain in-house software.

By creating and promoting an open-source repository, PyMedPhys aims to improve
the quality and accessibility of existing software solutions to problems faced
across a range of medical radiation applications, especially those
traditionally within the remit of medical physicists. These solutions can be
broadly categorised in two areas: data extraction/conversion of proprietary
formats from a variety of radiotherapy systems, and manipulation of standard
radiotherapy data to perform quality assurance (QA) tasks that are otherwise
time-consuming or lack commercial solutions with the desired flexibility or
true function.

Data extraction and conversion currently includes: two treatment planning
systems, an oncology information system, and a linear accelerator vendor
family of systems. Data in proprietary formats from these systems are
extracted and converted to allow for integration in a myriad of applications.
Applications that use planning system information include: electron cut-out
factor determination, CT extension, and extraction of dose information for
patient QA purposes. Applications that use the oncology information systems
include: clinical dashboards that summarise data, quality task tracking, and
comparison of dose information to planning systems. Applications that use the
linear accelerator data include: patient specific QA analysis against planning
data, and analysis of machine performance such as the Winston-Lutz test.

QA tasks using standard radiotherapy data include: anonymisation, extraction
of dose data for analysis, manipulation of contour files to allow merging or
adjustments/scaling of relative electron density, modifying machine names
in plans, and most frequently used, the calculation of a Gamma index, a widely
recognised metric in radiotherapy analysis that quantifies the difference
between measured and calculated dose distributions on a point-by-point basis
in terms of both dose and distance to agreement (DTA) differences.

Many of these tools are in use clinically at affiliated sites, and
additionally, aspects of PyMedPhys are implemented around the world for some
applications. Many parties have embraced the gamma analysis module
[`Milan et al., 2019`_; `Galic et al., 2020`_; `Rodriguez et al., 2020`_; `Cronholm et al., 2020`_;
`Spezialetti et al., 2021`_; `Tsuneda et al., 2021`_; `Pastor-Serrano & Perko, 2021`_;
`Gajewski et al., 2021`_; `Lysakovski et al., 2021`_; `Castle et al., 2022`_; `Yang et al., 2022`_],
while implementations of the electron cutout factor module and others
[`Baltz & Kirsner, 2021`_; `Douglass & Keal, 2021`_; `Rembish, 2021`_] have also
been reported. Additionally, the work has been recognized by the European
Society for Radiotherapy and Oncology (ESTRO) and referenced as recommended
literature in their 3rd Edition of Core Curriculum for Medical Physics Experts
in Radiotherapy [`Bert et al., 2021`_].

.. _`Milan et al., 2019`: https://aapm.onlinelibrary.wiley.com/doi/10.1002/mp.13491
.. _`Galic et al., 2020`: https://doi.org/10.4103/jmp.JMP_51_19
.. _`Rodriguez et al., 2020`: https://doi.org/10.1088/1361-6560/abb71b
.. _`Cronholm et al., 2020`: http://www.spectronic.se/files/Whitepaper_TFE_202106.pdf
.. _`Spezialetti et al., 2021`: https://doi.org/10.1109/SMC52423.2021.9658879
.. _`Tsuneda et al., 2021`: https://doi.org/10.1002/mp.15164
.. _`Pastor-Serrano & Perko, 2021`: https://doi.org/10.48550/arXiv.2109.03951
.. _`Gajewski et al., 2021`: https://doi.org/10.3389/fphy.2020.567300
.. _`Lysakovski et al., 2021`: https://doi.org/10.3389/fphy.2021.741453
.. _`Castle et al., 2022`: https://doi.org/10.1002/acm2.13556
.. _`Yang et al., 2022`: https://doi.org/10.1088/1361-6560/ac8269
.. _`Baltz & Kirsner, 2021`: https://doi.org/10.1002/acm2.13430
.. _`Douglass & Keal, 2021`: https://doi.org/10.1016/j.ejmp.2021.08.012
.. _`Rembish, 2021`: https://www.proquest.com/docview/2564568968
.. _`Bert et al., 2021`: https://www.efomp.org/uploads/595e3c8a-52d9-440f-b50b-183c3a00cb00/Radiotherapy_cc_2022.pdf

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


|sjs| |rah|

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

.. _`Quick Start Guide`: https://docs.pymedphys.com/en/latest/users/get-started/quick-start.html
.. _`get started`: https://docs.pymedphys.com/en/latest/users/get-started/index.html
.. _`how-to guides`: https://docs.pymedphys.com/en/latest/users/howto/index.html
.. _`background information`: https://docs.pymedphys.com/en/latest/users/background/index.html
.. _`Technical Reference`: https://docs.pymedphys.com/en/latest/users/ref/index.html
.. _`workstation setup guides`: https://docs.pymedphys.com/en/latest/contrib/setups/index.html
.. _`repository information`: https://docs.pymedphys.com/en/latest/contrib/info/index.html
.. _`tips & tricks`: https://docs.pymedphys.com/en/latest/contrib/tips/index.html
