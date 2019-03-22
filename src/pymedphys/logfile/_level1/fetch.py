# Copyright (C) 2019 Cancer Care Associates

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


import os
import shutil
from glob import glob

from ...libutils import get_imports
IMPORTS = get_imports(globals())


def fetch_system_diagnostics(ip, storage_directory):
    r"""Fetches and stores locally Linac system diagnositc files.

    For an Elekta Linac the system diagnostic backups are stored at
    \\IP\Backup\TCS\SDD+*.zip. These are copied to a defined local directory.

    Need to have logged in to this directory and ticked "remember credentials".
    You will need to use a login for the Linac NSS supplied by an Elekta
    engineer to access this file share.
    """

    backup_share_path = "\\\\{}\\Backup\\TCS\\".format(ip)
    diagnostic_file_search = "{}\\SDD+*.zip".format(backup_share_path)
    diagnostic_filepaths = glob(diagnostic_file_search)

    storage_filepaths = [
        os.path.join(storage_directory, os.path.basename(filepath))
        for filepath in diagnostic_filepaths
    ]

    for nss_filepath, storage_filepath in zip(diagnostic_filepaths,
                                              storage_filepaths):
        if not os.path.exists(storage_filepath):
            shutil.copyfile(nss_filepath, storage_filepath)
