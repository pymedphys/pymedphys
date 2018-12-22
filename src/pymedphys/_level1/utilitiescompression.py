# Copyright (C) 2018 Simon Biggs

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


import lzma

from glob import glob

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def compress_test_file(filepath):
    with open(filepath, 'rb') as load_file:
        with lzma.open('{}.xz'.format(filepath), 'w') as save_file:
            save_file.write(load_file.read())


def compress_test_files(glob_string, exclude_xz_files=True):
    files_to_compress = glob(glob_string, recursive=True)

    for filepath in files_to_compress:
        if not filepath.endswith(".xz") or not exclude_xz_files:
            compress_test_file(filepath)


def decompress_test_files():
    pass
