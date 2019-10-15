===================================
Linux Contributor Environment Setup
===================================

.. contents::
    :local:
    :backlinks: entry


Overview
========

* Install Python 3.7
* `Install Poetry`_
* Clone the PyMedPhys git repo
* Run ``poetry install`` within the root of the repo
* Run ``poetry run pre-commit install``
* Install ``pandoc`` via your package manager
  - eg. ``sudo apt-get install pandoc``

You're good to go.

.. _`Install Poetry`: https://poetry.eustace.io/docs/#installation


Opinionated Recommendations
===========================

* Install Python with `pyenv`_
* Install `VSCode`_ as your code editor
* Install `Jupyter Lab`_ to work with Notebooks


.. _`pyenv`: https://github.com/pyenv/pyenv-installer#install
.. _`VSCode`: https://code.visualstudio.com/Download
.. _`Jupyter Lab`: https://jupyterlab.readthedocs.io/en/stable/getting_started/installation.html#pip
