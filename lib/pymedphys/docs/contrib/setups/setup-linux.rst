===================================
Linux Setup
===================================

Overview
========

* Install Python 3.8
* `Install Poetry`_
* Clone the PyMedPhys git repo
* Run ``poetry install -E dev`` within the root of the repo
* Run ``poetry run pre-commit install``
* Install ``pandoc`` via your package manager

  * eg. ``sudo apt-get install pandoc``

You're good to go.

.. _`Install Poetry`: https://poetry.eustace.io/docs/#installation


Opinionated Recommendations
===========================

* Install Python with pyenv

  * `Install prerequisites`_
  * `Install pyenv`_
  * `Configure pyenv`_
* Install `VSCode`_ as your code editor
* Install `Jupyter Lab`_ to work with Notebooks


.. _`Install pyenv`: https://github.com/pyenv/pyenv-installer#install
.. _`Install prerequisites`: https://github.com/pyenv/pyenv/wiki/common-build-problems#prerequisites
.. _`VSCode`: https://code.visualstudio.com/Download
.. _`Jupyter Lab`: https://jupyterlab.readthedocs.io/en/stable/getting_started/installation.html#pip
.. _`Configure pyenv`: https://amaral.northwestern.edu/resources/guides/pyenv-tutorial
