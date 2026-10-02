Structure nomenclatures
=======================

.. automodule:: pymedphys.cli.nomenclature
    :no-members:

For example, to convert the copy of the TG-263 spreadsheet you downloaded from
AAPM:

.. code:: bash

    pymedphys nomenclature tg263 TG263_Nomenclature_Worksheet_20170815.xls tg263.json

and to convert your department's own list of structure names, saved from a
spreadsheet as "CSV UTF-8" with a ``Name`` column:

.. code:: bash

    pymedphys nomenclature roi-list site-roi-names.csv site-roi-names.json --list-version 2026-10

Command line options
--------------------

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: nomenclature
