Structure nomenclatures
=======================

.. automodule:: pymedphys.cli.nomenclature
    :no-members:

For example, to convert the copy of the TG-263 spreadsheet you downloaded from
AAPM:

.. code:: bash

    pymedphys nomenclature tg263 TG263_Nomenclature_Worksheet_20170815.xls tg263.json

Command line options
--------------------

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: nomenclature
