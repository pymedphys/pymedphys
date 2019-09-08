# Copyright (C) 2018 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Converts a trf file into a csv file.
"""


import os
from glob import glob

from .trf2pandas import trf2pandas


def trf2csv_by_directory(input_directory, output_directory):
    filepaths = glob(os.path.join(input_directory, "*.trf"))

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        new_filename = os.path.join(output_directory, filename)

        header_csv_filepath = "{}.header.csv".format(new_filename)
        table_csv_filepath = "{}.table.csv".format(new_filename)

        print("Converting {}".format(filepath))

        header, table = trf2pandas(filepath)
        header.to_csv(header_csv_filepath)
        table.to_csv(table_csv_filepath)


def trf2csv(trf_filepath, skip_if_exists=False):
    if not os.path.exists(trf_filepath):
        raise Exception("The provided trf filepath cannot be found.")

    extension_removed = os.path.splitext(trf_filepath)[0]
    header_csv_filepath = "{}_header.csv".format(extension_removed)
    table_csv_filepath = "{}_table.csv".format(extension_removed)

    # Skip if conversion has already occured
    if not skip_if_exists or not os.path.exists(table_csv_filepath):
        print("Converting {}".format(trf_filepath))
        header, table = trf2pandas(trf_filepath)

        header.to_csv(header_csv_filepath)
        table.to_csv(table_csv_filepath)
    # else:
    #     print("Skipping {}".format(trf_filepath))

    return header_csv_filepath, table_csv_filepath


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
