Graphical apps
==============

After installing the ``user`` extra, run ``pymedphys gui`` to launch the
Streamlit app selector. See :doc:`the installation guide <../../get-started/quick-start>`
for environment setup. App-specific connections and configuration may also be
required.

Serving the apps
----------------

By default, ``pymedphys gui`` listens only on the loopback address
``127.0.0.1``, so only the computer that runs it can connect. It also accepts
only requests addressed to ``localhost`` or ``127.0.0.1``, which protects
against other web pages reaching the apps through DNS rebinding, and it turns
off Streamlit's usage statistics.

To serve other computers, for example from a department server, pass the
address to listen on with ``--address``. This serves every IPv4 interface on
port 8501:

.. code:: bash

    pymedphys gui --address 0.0.0.0 --port 8501

.. warning::

   The apps have no login and handle patient data. Anyone who can reach the
   address and port can use every app and download its outputs, and the
   connection is unencrypted HTTP. Serve on another address only on a network
   where that is acceptable.

With ``--address``, Streamlit accepts requests addressed to any host name. To
accept only the names that clients use, set ``server.allowedHosts`` in
Streamlit's configuration file, ``.streamlit/config.toml`` in the home
directory of the user who runs the GUI:

.. code:: toml

    [server]
    allowedHosts = ["physics-server", "physics-server.example.org"]

``pymedphys gui`` passes ``server.address``, ``browser.gatherUsageStats``, and,
without ``--address``, ``server.allowedHosts`` to Streamlit on the command
line, so these settings override Streamlit's configuration files and
environment variables.

Command line options
--------------------

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: gui
