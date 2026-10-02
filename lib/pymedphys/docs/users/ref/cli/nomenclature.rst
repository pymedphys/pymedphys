Structure nomenclatures
=======================

.. automodule:: pymedphys.cli.nomenclature
    :no-members:

For example, to download and convert the pinned edition of the TG-263
spreadsheet:

.. code:: bash

    pymedphys nomenclature tg263 tg263.json

On a computer without internet access, convert a copy you downloaded
elsewhere:

.. code:: bash

    pymedphys nomenclature tg263 tg263.json --spreadsheet TG263_Nomenclature_Worksheet_20170815.xls

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
