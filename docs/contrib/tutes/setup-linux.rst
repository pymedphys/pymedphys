===================================
Linux Contributor Environment Setup
===================================

.. contents::
    :local:
    :backlinks: entry


Overview
========

* Install Python 3.7
* Install pip ``sudo apt-get install python3-pip``
* `Install Poetry`_
* Clone the PyMedPhys git repo
* Run ``poetry install`` within the root of the repo
* Run ``poetry run pre-commit install``
* Install ``pandoc`` via your package manager

  * eg. ``sudo apt-get install pandoc``

You're good to go.

.. _`Install Poetry`: https://poetry.eustace.io/docs/#installation


Opinionated Recommendations
===========================

* Install Python with pyenv
  * Install dependencies: ```sudo apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev \
libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
xz-utils tk-dev libffi-dev liblzma-dev python-openssl git```
   * `Install pyenv`_
   * `Configure pyenv`_
* Install `VSCode`_ as your code editor
* Install `Jupyter Lab`_ to work with Notebooks


.. _`Install pyenv`: https://github.com/pyenv/pyenv-installer#install
.. _`VSCode`: https://code.visualstudio.com/Download
.. _`Jupyter Lab`: https://jupyterlab.readthedocs.io/en/stable/getting_started/installation.html#pip
.. _`Configure pyenv`: https://amaral.northwestern.edu/resources/guides/pyenv-tutorial
