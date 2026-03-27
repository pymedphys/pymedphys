|logo|

.. |logo| image:: https://github.com/pymedphys/pymedphys/raw/ca501275227f190a77e641a75af925d9070952b6/lib/pymedphys/docs/_static/pymedphys_title.svg
    :target: https://docs.pymedphys.com/

.. START_OF_DOCS_IMPORT

**A community effort to develop an open standard library for Medical Physics
in Python. We build high quality, transparent software together via peer review
and open source distribution. Open code is better science.**

|build| |pypi| |python| |license|

.. |build| image:: https://github.com/pymedphys/pymedphys/actions/workflows/ci.yml/badge.svg?branch=claude/debug-workflow-failure-AWhfc
   :target: https://github.com/pymedphys/pymedphys/actions/workflows/ci.yml

.. |pypi| image:: https://img.shields.io/pypi/v/pymedphys
    :target: https://pypi.org/project/pymedphys/

.. |python| image:: https://img.shields.io/pypi/pyversions/pymedphys
    :target: https://pypi.org/project/pymedphys/

.. |license| image:: https://img.shields.io/pypi/l/pymedphys
    :target: https://choosealicense.com/licenses/apache-2.0/


What is PyMedPhys?
==================

PyMedPhys is an open-source Medical Physics Python library built by an open
community that values code sharing, review, improvement, and learning from each
other. It is inspired by the collaborative work of our physics peers in
astronomy and the `Astropy Project`_. PyMedPhys is available on `PyPI`_ and
`GitHub`_.

PyMedPhys supports three main ways of working:

* a Python library for notebooks, scripts, and clinic-specific tooling
* a command line interface (CLI) for repeatable automation
* a point-and-click app layer for selected workflows

Beta level of development
*************************

PyMedPhys is currently within the ``beta`` stage of its life-cycle. It will
stay in this stage until the version number leaves ``0.x.x`` and enters
``1.x.x``. While PyMedPhys is in ``beta`` stage, **no API is guaranteed to be
stable from one release to the next.** Upgrading ``pymedphys`` can therefore
break existing scripts or workflows. We try to stay ahead of that by
documenting breaking changes in the `Release Notes`_.

Start here
**********

If you are new to PyMedPhys, start with these four questions in order:

1. `What PyMedPhys can do`_
2. `Choose your path`_
3. `Installation options`_
4. `Quick Start Guide`_

Common task areas
*****************

PyMedPhys is often used to:

* compare dose or fluence-like data with gamma, interpolation, and MetersetMap
* work with DICOM and pseudonymisation workflows
* work with delivery, logfile, and iCom data
* query or integrate with Mosaiq
* use point-and-click apps for selected workflows

Install PyMedPhys
*****************

PyMedPhys currently supports Python 3.10, 3.11, and 3.12.

For most users, we recommend using ``uv`` to create an environment and install
PyMedPhys:

.. code:: bash

    uv python install 3.12
    uv venv --python 3.12
    uv pip install "pymedphys[user]"

If you cannot use ``uv`` on your workstation, the `Quick Start Guide`_ also
includes a standard Python + ``venv`` + ``pip`` fallback path.

Choose the right interface
**************************

Use the **Python library** when you want notebooks, analysis, plots, and
clinic-specific workflows.

Use the **CLI** when you want repeatable commands, scheduled jobs, or shell
automation.

Use the **app layer** when you want the least coding and a graphical workflow.

For a fuller comparison, read `Choose your path`_.

Documentation
=============

The PyMedPhys documentation has two overarching guides:

1. **The Users Guide**: where you can `get started`_ with the library, the CLI,
   and the app layer; read task-focused `how-to guides`_; find
   `background information`_ on larger projects and concepts; and browse the
   `Technical Reference`_ when you already know the feature you need.

2. **The Contributors Guide**: for those who want to contribute to PyMedPhys.
   This includes the `Contributors Guide`_ landing page, detailed
   `workstation setup guides`_, important `repository information`_, and some
   `tips & tricks`_ for common problems.

Community
*********

PyMedPhys has a
`GitHub Discussions <https://github.com/pymedphys/pymedphys/discussions>`_
page to help users find their feet and to support collaboration and general
discussion.

.. END_OF_DOCS_IMPORT

Citing PyMedPhys
================

PyMedPhys' first paper in the Journal of Open Source Software contains more
background information, including the `Statement of Need`_. You can access the
paper `here <https://joss.theoj.org/papers/10.21105/joss.04555>`_.

When referencing PyMedPhys, please cite this paper as follows:

*Biggs, S., Jennings, M., Swerdloff, S., Chlap, P., Lane, D., Rembish, J.,
McAloney, J., King, P., Ayala, R., Guan, F., Lambri, N., Crewson, C.,
Sobolewski, M. (2022). PyMedPhys: A community effort to develop an open,
Python-based standard library for medical physics applications. Journal of Open
Source Software, 7(78), 4555, https://doi.org/10.21105/joss.04555*

Development
===========

PyMedPhys uses `uv`_ for package and project management.

After cloning the repository, install the PyMedPhys dependencies and set up
pre-commit by running:

.. code:: bash

    uv sync --extra all --group dev
    uv run -- pre-commit install

Run automated tests with:

.. code:: bash

    uv run -- pymedphys dev tests


Our Team
========

PyMedPhys is what it is today due to its maintainers and contributors, both
past and present. Here is our team.

Maintainers
***********

* `Simon Biggs`_
    * `Anthropic PBC`_

.. _`Simon Biggs`: https://github.com/SimonBiggs

* `Stuart Swerdloff`_
    * `SJS Targeted Solutions, LLP`_, New Zealand

.. _`Stuart Swerdloff`: https://github.com/sjswerdloff

* `Matthew Jennings`_
    * `Icon Group`_, Australia

.. _`Matthew Jennings`: https://github.com/Matthew-Jennings

* `Phillip Chlap`_
    * `Radformation Inc.`_, USA
    * `University of New South Wales`_, Australia

.. _`Phillip Chlap`: https://github.com/pchlap


|sjs| |rah|

Active contributors
*******************

* `Derek Lane`_
    * `ELEKTA AB`_, Houston TX

.. _`Derek Lane`: https://github.com/dg1an3

* `Marcelo Jordao`_
    * `ELEKTA AB`_, Hong Kong SAR

.. _`Marcelo Jordao`: https://github.com/mguerrajordao

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

* `Marcus Fisk`_
    * `Cancer Care Riverina`_, Australia

.. _`Marcus Fisk`: https://github.com/laser47-hue

|uth| |ccr|

Past contributors
*****************

* `Matthew Cooper <https://github.com/matthewdeancooper>`_
* `Pedro Martinez <https://github.com/peterg1t>`_
* `Rafael Ayala <https://github.com/ayalalazaro>`_
* `Matthew Sobolewski <https://github.com/msobolewski>`_
* `Paul King <https://github.com/kingrpaul>`_
* `Jacob McAloney <https://github.com/JacobMcAloney>`_

..
   Unfortunately :target: being a variable name is no longer supported by
   GitHub within README.rst files. So... unfortunately we have some duplication
   below.

.. |rah| image:: https://github.com/pymedphys/pymedphys/raw/3f8d82fc3b53eb636a75336477734e39fa406110/docs/logos/gosa_200x200.png
    :target: https://www.rah.sa.gov.au/

.. |uth| image:: https://github.com/pymedphys/pymedphys/raw/3f8d82fc3b53eb636a75336477734e39fa406110/docs/logos/UTHSA_logo.png
    :target: https://www.uthscsa.edu/academics/biomedical-sciences/programs/radiological-sciences-phd

.. |sjs| image:: https://github.com/pymedphys/pymedphys/raw/7e9204656e0468b0843533472553a03a99387386/logos/swerdloff.png
    :target: https://github.com/sjswerdloff

.. |ccr| image:: https://github.com/pymedphys/pymedphys/raw/ec61e4e63a8624f4df44a8e90931bd0bca748e20/logos/cancercareriverina_200x200.png
    :target: https://cancercare.com.au/clinics/cancer-care-riverina/

.. _`Anthropic PBC`: https://www.anthropic.com/

.. _`ELEKTA Pty Ltd`: https://www.elekta.com/

.. _`ELEKTA AB`: https://www.elekta.com/

.. _`Icon Group`: https://icongroup.global/

.. _`University of New South Wales`: https://www.unsw.edu.au/

.. _`South Western Sydney Local Health District`: https://www.swslhd.health.nsw.gov.au/

.. _`Anderson Regional Cancer Center`: https://www.andersonregional.org/services/cancer-care/

.. _`Northern Beaches Cancer Care`: https://www.northernbeachescancercare.com.au/

.. _`University of Calgary`: https://www.ucalgary.ca/

.. _`Tom Baker Cancer Centre`: https://www.ahs.ca/tbcc

.. _`UT Health San Antonio`: https://www.uthscsa.edu/academics/biomedical-sciences/programs/radiological-sciences-phd

.. _`Hospital General Universitario Gregorio Marañón`: https://www.comunidad.madrid/hospital/gregoriomaranon/

.. _`Swerdloff Family`: https://github.com/sjswerdloff

.. _`SJS Targeted Solutions, LLP`: https://github.com/sjswerdloff

.. _`Radformation Inc.`: https://radformation.com/

.. _`IRCCS Humanitas Research Hospital`: https://www.humanitas.net/

.. _`Saskatchewan Cancer Agency`: http://www.saskcancer.ca/

.. _`Humanitas University`: https://www.hunimed.eu/

.. _`Yale University School of Medicine`: https://medicine.yale.edu/

.. _`Cancer Care Riverina`: https://cancercare.com.au/clinics/cancer-care-riverina/

.. _`Astropy Project`: https://www.astropy.org/
.. _`PyPI`: https://pypi.org/project/pymedphys/
.. _`GitHub`: https://github.com/pymedphys/pymedphys

.. _`Release Notes`: ./CHANGELOG.md

.. _`Statement of Need`: https://docs.pymedphys.com/en/latest/statement-of-need.html
.. _`What PyMedPhys can do`: https://docs.pymedphys.com/en/latest/users/get-started/what-pymedphys-can-do.html
.. _`Choose your path`: https://docs.pymedphys.com/en/latest/users/get-started/choose-your-path.html
.. _`Installation options`: https://docs.pymedphys.com/en/latest/users/get-started/installation-options.html
.. _`Quick Start Guide`: https://docs.pymedphys.com/en/latest/users/get-started/quick-start.html
.. _`get started`: https://docs.pymedphys.com/en/latest/users/get-started/index.html
.. _`how-to guides`: https://docs.pymedphys.com/en/latest/users/howto/index.html
.. _`background information`: https://docs.pymedphys.com/en/latest/users/background/index.html
.. _`Technical Reference`: https://docs.pymedphys.com/en/latest/users/ref/index.html
.. _`Contributors Guide`: https://docs.pymedphys.com/en/latest/contrib/index.html
.. _`workstation setup guides`: https://docs.pymedphys.com/en/latest/contrib/setups/index.html
.. _`repository information`: https://docs.pymedphys.com/en/latest/contrib/info/index.html
.. _`tips & tricks`: https://docs.pymedphys.com/en/latest/contrib/tips/index.html
.. _`uv`: https://docs.astral.sh/uv/
