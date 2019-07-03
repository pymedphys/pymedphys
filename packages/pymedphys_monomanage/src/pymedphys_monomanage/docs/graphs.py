# Copyright (C) 2019 Simon Biggs

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
import textwrap

from glob import glob
from ..draw.utilities import remove_postfix

ROOT = os.getcwd()


def write_graphs_rst(save_directory):
    search_string = os.path.join(save_directory, "*.svg")

    svg_files = [
        os.path.basename(filepath)
        for filepath in sorted(glob(search_string), key=os.path.splitext)
    ]

    modules = [remove_postfix(filepath, '.svg') for filepath in svg_files]
    images_paths = ["../graphs/{}.svg".format(module) for module in modules]

    sections = ".. This is automatically generated. DO NOT DIRECTLY EDIT.\n\n"
    for module, images_path in zip(modules, images_paths):
        header_border = '*' * len(module)
        sections += textwrap.dedent("""\
            {0}
            {1}
            {0}
            `Back to pymedphys <#pymedphys>`_

            .. raw:: html
                :file: {2}

        """.format(header_border, module, images_path))

    save_file = os.path.join(save_directory, 'graphs.rst')
    with open(save_file, 'w') as file:
        file.write(sections)
