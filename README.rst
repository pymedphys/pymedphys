|logo|

.. |logo| image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/pymedphys_title.png
    :target: https://docs.pymedphys.com/

.. START_OF_DOCS_IMPORT

**A community effort to develop an open standard library for Medical Physics
in Python. Building quality transparent software together via peer review
and open source distribution. Open code is better science.**

|build| |pypi| |python| |license|

.. |build| image:: https://img.shields.io/endpoint.svg?url=https%3A%2F%2Factions-badge.atrox.dev%2Fpymedphys%2Fpymedphys%2Fbadge&label=build&logo=none
    :target: https://actions-badge.atrox.dev/pymedphys/pymedphys/goto

.. |pypi| image:: https://img.shields.io/pypi/v/pymedphys
    :target: https://pypi.org/project/pymedphys/

.. |python| image:: https://img.shields.io/pypi/pyversions/pymedphys
    :target: https://pypi.org/project/pymedphys/

.. |license| image:: https://img.shields.io/pypi/l/pymedphys
    :target: https://choosealicense.com/licenses/apache-2.0/


Docs under construction
-----------------------

This documentation is currently undergoing a major revamp. At this point in
time many of the below links will take you to empty pages. If you are able to
help, drop me a line at `me@simonbiggs.net`_.

.. _`me@simonbiggs.net`: mailto:me@simonbiggs.net


First steps
-----------

Are you new to PyMedPhys or new to Python programming? Then these resources are
for you:

* From scratch: `New to Python`_ | `Installation`_
* Tutorials: `Part 1: Name`_ | `Part 2: Name`_

How the documentation is organised
----------------------------------

Here is a high level overview of how the documentation is organised to help
you to know where to look for things:

* `Tutorials`_ take you by the hand through a series of steps to create a tool
  built with PyMedPhys for use within a Medical Physics clinic. Start here if
  you're new to PyMedPhys or Python programming.
* `How-To guides`_ are recipes. They guide you through the steps involved in
  addressing key problems and use-cases. They are more advanced than tutorials
  and assume some knowledge of how to build tools with PyMedPhys.
* `Reference Documents`_ is the technical reference for the public APIs exposed
  by both the ``pymedphys`` library and the ``pymedphys`` command line tool.
* `Explanatory documents`_ provide the higher level descriptions of the
  implementation of the tools and provides justifications for development
  decisions.

The above layout has been heavily inspired by both the `Django documentation`_
and `Daniele Procida's writeup`_.

.. figure:: https://github.com/pymedphys/pymedphys/raw/master/docs/img/docs-structure.png

    A slide from `Daniele Procida's writeup`_ describing the documentation
    layout.

.. _`Daniele Procida's writeup`: https://www.divio.com/blog/documentation/
.. _`Django documentation`: https://docs.djangoproject.com

Beyond the user documentation there are two other sections, the
`contributor documentation`_ aimed at those who wish to become a PyMedPhys
contributor, and the `labs documentation`_ which details code contributed by
the community that aims to one day be refined to become part of the primary
``pymedphys`` library.

What is PyMedPhys?
------------------

A place to share, review, improve, and transparently learn off of each other’s
code. It is an open-source library of tools that we all have access to.
It is inspired by the collaborative work of our physics peers in astronomy and
their `Astropy Project`_. PyMedPhys is available on `PyPI`_, `GitHub`_ and
`conda-forge`_.

.. _`Astropy Project`: http://www.astropy.org/
.. _`PyPI`: https://pypi.org/project/pymedphys/
.. _`GitHub`: https://github.com/pymedphys/pymedphys
.. _`conda-forge`: https://anaconda.org/conda-forge/pymedphys

PyMedPhys is currently within the ``beta`` stage of its life-cycle. It will
stay in this stage until the version number leaves ``0.x.x`` and enters
``1.x.x``. While PyMedPhys is in ``beta`` stage, **no API is guaranteed to be
stable from one release to the next.** In fact, it is very likely that the
entire API will change multiple times before a ``1.0.0`` release. In practice,
this means that upgrading ``pymedphys`` to a new version will possibly break
any code that was using the old version of pymedphys. We try to be abreast of
this by providing details of any breaking changes from one release to the next
within the `Release Notes`_.

Our Team
--------

PyMedPhys is what it is today due to its contributors.
Core contributors and contributors who have been active in the last six months
as well as their respective employers are presented below.

Core contributors
.................

* `Simon Biggs`_
    * `Riverina Cancer Care Centre`_, Australia

.. _`Simon Biggs`: https://github.com/SimonBiggs


* `Matthew Jennings`_
    * `Royal Adelaide Hospital`_, Australia

.. _`Matthew Jennings`: https://github.com/Matthew-Jennings

Active contributors
...................

* `Jake Rembish`_
    * `UT Health San Antonio`_, USA

.. _`Jake Rembish`: https://github.com/rembishj

* `Phillip Chlap`_
    * `University of New South Wales`_, Australia
    * `South Western Sydney Local Health District`_, Australia

.. _`Phillip Chlap`: https://github.com/pchlap

* `Pedro Martinez`_
    * `University of Calgary`_, Canada
    * `Tom Baker Cancer Centre`_, Canada

.. _`Pedro Martinez`: https://github.com/peterg1t

* `Jacob McAloney`_
    * `Riverina Cancer Care Centre`_, Australia

.. _`Jacob McAloney`: https://github.com/JacobMcAloney


|rccc| |rah| |uth| |uoc|

Past contributors
.................

* `Matthew Sobolewski <https://github.com/msobolewski>`_
* `Paul King <https://github.com/kingrpaul>`_


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

.. |uth| image:: https://github.com/pymedphys/pymedphys/raw/master/docs/logos/UTHSA_logo.png
    :target: `UT Health San Antonio`_

.. _`Riverina Cancer Care Centre`: http://www.riverinacancercare.com.au/

.. _`Royal Adelaide Hospital`: http://www.rah.sa.gov.au/

.. _`University of New South Wales`: https://www.unsw.edu.au/

.. _`South Western Sydney Local Health District`: https://www.swslhd.health.nsw.gov.au/

.. _`Anderson Regional Cancer Center`: http://www.andersonregional.org/CancerCenter.aspx

.. _`Northern Beaches Cancer Care`: http://www.northernbeachescancercare.com.au/

.. _`University of Calgary`: http://www.ucalgary.ca/

.. _`Tom Baker Cancer Centre`: https://www.ahs.ca/tbcc

.. _`UT Health San Antonio`: https://www.uthscsa.edu/academics/biomedical-sciences/programs/radiological-sciences-phd


.. END_OF_DOCS_IMPORT


.. _`New to Python` : https://docs.pymedphys.com/tutes/python
.. _`Installation` : https://docs.pymedphys.com/tutes/install
.. _`Part 1: Name` : https://docs.pymedphys.com/tutes/part-1
.. _`Part 2: Name` : https://docs.pymedphys.com/tutes/part-2


.. _`Tutorials`: https://docs.pymedphys.com/tutes
.. _`How-To guides`: https://docs.pymedphys.com/howto
.. _`Reference Documents`: https://docs.pymedphys.com/ref
.. _`Explanatory documents`: https://docs.pymedphys.com/explain

.. _`contributor documentation`: https://docs.pymedphys.com/contrib
.. _`labs documentation`: https://docs.pymedphys.com/labs

.. _`Release Notes`: http://docs.pymedphys.com/getting-started/changelog.html
