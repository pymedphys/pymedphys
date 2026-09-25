Graphical apps
==============

After installing the ``user`` extra, run ``pymedphys gui`` to launch the
Streamlit app selector. See :doc:`the installation guide <../../get-started/quick-start>`
for environment setup. App-specific connections and configuration may also be
required.

The GUI serves on ``localhost`` by default, so only the computer running it
can connect. It has no login and can display patient data. Use ``--address``
to serve on another address, for example ``--address 0.0.0.0`` for every
network interface, only on a network where everyone who can reach it is
allowed to see that data. Streamlit's usage statistics are always disabled.
These settings are passed to Streamlit as command-line flags, so they take
precedence over any Streamlit configuration file.

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: gui
