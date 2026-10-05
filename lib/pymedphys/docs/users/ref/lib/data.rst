Downloaded data
===============

These public root helpers obtain packaged example/research datasets and return
resolved ``pathlib.Path`` objects. They may access the network and create or
repair files in the local cache. The default cache is ``~/.pymedphys/data``;
``PYMEDPHYS_DATA_DIR`` overrides it for the running process. This setting is
independent of site configuration.
Use an absolute directory value for the override; the helper does not expand
``~`` in it.

See :doc:`../../tasks/first-result` for a workflow that creates entirely
synthetic data locally, and :doc:`../configuration` for app demo modes.

One file
--------

.. autofunction:: pymedphys.data_path

``filename`` is the cache-relative name recorded in PyMedPhys's URL and hash
maps, or a caller-selected relative name with an explicit ``url`` and hash
file. Use a relative name beneath the cache, not an absolute destination path.
With the defaults, a valid cached file is returned without replacing it.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Argument
     - Behaviour
   * - ``check_hash=True``
     - Compare the file's SHA-256 with the recorded expected hash.
   * - ``redownload_on_hash_mismatch=True``
     - Remove a mismatching cached file and try downloading once more. A second mismatch raises ``ValueError``.
   * - ``delete_when_no_hash_found=True``
     - If no expected hash exists, remove an existing cached copy and raise ``NoHashFound`` (a ``KeyError`` subclass), without downloading.
   * - ``url=None``
     - Use the package's URL map. An explicit mirror URL may use HTTP, HTTPS, or ``file:``.
   * - ``hash_filepath=None``
     - Use the package's hash map. A supplied JSON file maps cache-relative names to expected SHA-256 strings.

``check_hash=False`` explicitly bypasses verification; it is not a workaround
for a trusted dataset that fails its expected hash. Obtain the expected hash
from an independent trusted source before using a custom mirror. The helpers
do not record a new expected hash automatically.

Downloads use a temporary file that is moved into place after transfer, with
a 60-second connection/read timeout and retries for transient network errors.
Permanent HTTP errors such as 403/404 fail immediately. Concurrent calls for
the same file are serialised. Missing URL-map entries, unsupported URL
schemes, failed downloads, and hash failures raise exceptions rather than
returning a path to accepted data.

ZIP archives
------------

.. autofunction:: pymedphys.zip_data_paths

The file/verification arguments are the same as ``data_path``.
``extract_directory=None`` selects a managed directory beneath the data cache,
named after the archive without its suffix. An archive-hash marker, expected
members, and member sizes determine whether that extraction needs refreshing.
Those checks are not per-member content hashes.

An explicit ``extract_directory`` adds only missing archive members. Existing
files there are preserved, including edited demo files. To get a fresh app
demo, extract into a new directory rather than assuming another call
overwrites prior edits.

The return value is a list of resolved paths to files, excluding directories.
Select a file by its name or relative path and check that the match is unique;
do not rely on ZIP ordering.

For example, obtain the approved app demonstration archive:

.. code-block:: python

   from pathlib import Path
   import pymedphys

   practice = Path("fresh-demo")
   paths = pymedphys.zip_data_paths(
       "metersetmap-gui-e2e-data.zip", extract_directory=practice
   )
   config_matches = [
       path for path in paths
       if path.name == "config.toml"
       and path.parent.name == "pymedphys-gui-demo"
   ]
   assert len(config_matches) == 1
   print(config_matches[0])

This downloads the registered archive if it is not already cached. The
:doc:`app guide <../../tasks/apps>` describes how to use the demo configuration
and interpret the resulting reports.

Registered Zenodo records
-------------------------

.. autofunction:: pymedphys.zenodo_data_paths

``record_name`` is a name registered in the installed package's Zenodo map,
not an arbitrary record number. An unknown record name raises ``ValueError``.
``filenames=None`` selects all listed files; a sequence of filenames selects
matching entries. Unknown filenames do not produce entries.

The helper retrieves the record's file listing from the Zenodo API, so a
previously downloaded file does not make a new process fully offline.
Each selected file uses the hash-checked cache path beneath the registered
record name; ZIP files are extracted with ``zip_data_paths``. The returned
list combines the selected ordinary files and extracted ZIP members.
``check_hash`` and ``redownload_on_hash_mismatch`` retain the meanings above.

Public downloads do not require a Zenodo upload token. Token storage is
documented separately in :doc:`../cli/zenodo`.
