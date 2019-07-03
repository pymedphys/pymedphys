==========
Interfaces
==========

Graphical User Interfaces
-------------------------

As of yet, no graphical user interfaces (GUIs) have been implemented for PyMedPhys.


Command Line Interfaces
-----------------------

PyMedPhys exposes a range of its library functions to the command line as a
command line interface (CLI). This provides the benefit of being able to call
PyMedPhys functions from a range of locations such as:

* Other programming languages
* Windows scheduler
* ``.bat`` and ``.sh`` files

In this section of the documentation the help texts from each of the CLI
commands are presented.

At the beginning of each of the CLI docs something like the following will
display:

.. argparse::
   :ref: pymedphys.cli.main.define_parser
   :prog: pymedphys
   :nosubcommands:

This presents what to write into the command prompt to use that CLI command.


.. toctree::
    :maxdepth: 1

    cli/dicom
    cli/trf
    cli/logfile
    cli/docker
    cli/pinnacle


