# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Converts a trf file into a csv file."""

import logging
import os
import pathlib
import tempfile
from glob import glob

from .trf2pandas import trf2pandas


def _redact_progress_paths():
    """Opt in when conversion logs may leave a clinical workstation."""
    return os.environ.get("PYMEDPHYS_REDACT_TRF_PATHS") == "1"


def _write_private_csv(frame, destination):
    """Write clinical CSV through a private temporary file, then replace atomically.

    A normal DataFrame.to_csv(path) creates a new file using the process umask
    (often 0644). The temporary file is 0600 even if the destination previously
    existed with broader permissions. Replacing a symlink does not follow it.
    """
    destination = pathlib.Path(destination)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    try:
        frame.to_csv(temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def trf2csv_by_directory(input_directory, output_directory):
    filepaths = glob(os.path.join(input_directory, "*.trf"))

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        new_filename = os.path.join(output_directory, filename)

        header_csv_filepath = "{}.header.csv".format(new_filename)
        table_csv_filepath = "{}.table.csv".format(new_filename)

        if _redact_progress_paths():
            print("Converting TRF file")
        else:
            print("Converting {}".format(filepath))

        header, table = trf2pandas(filepath)
        _write_private_csv(header, header_csv_filepath)
        _write_private_csv(table, table_csv_filepath)


def trf2csv(trf_filepath, output_directory=None):
    trf_filepath = pathlib.Path(trf_filepath)

    if not trf_filepath.exists():
        raise ValueError("The provided trf filepath cannot be found.")

    if output_directory is None:
        output_directory = trf_filepath.parent
    else:
        output_directory = pathlib.Path(output_directory)

    filepaths = {
        contents: output_directory.joinpath(f"{trf_filepath.stem}_{contents}.csv")
        for contents in ["header", "table"]
    }

    if _redact_progress_paths():
        logging.info("Converting TRF file")
    else:
        logging.info("Converting %(trf_filepath)s", {"trf_filepath": trf_filepath})

    dataframes = dict()
    dataframes["header"], dataframes["table"] = trf2pandas(trf_filepath)

    for key, df in dataframes.items():
        _write_private_csv(df, filepaths[key])

    return filepaths["header"], filepaths["table"]


def trf2csv_cli(args):
    for glob_string in args.filepaths:
        glob_string = glob_string.replace("[", "<[>")
        glob_string = glob_string.replace("]", "<]>")
        glob_string = glob_string.replace("?", "[?]")

        glob_string = glob_string.replace("<[>", "[[]")
        glob_string = glob_string.replace("<]>", "[]]")

        filepaths = glob(glob_string)

        for filepath in filepaths:
            trf2csv(filepath)
