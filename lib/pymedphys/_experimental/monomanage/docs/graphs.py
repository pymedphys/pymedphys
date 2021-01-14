# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import textwrap
from glob import glob

ROOT = os.getcwd()


def write_graphs_rst(save_directory):
    search_string = os.path.join(save_directory, "*.svg")

    svg_files = [
        os.path.basename(filepath)
        for filepath in sorted(glob(search_string), key=os.path.splitext)
    ]

    modules = [remove_postfix(filepath, ".svg") for filepath in svg_files]
    images_paths = ["../graphs/{}.svg".format(module) for module in modules]

    sections = ".. This is automatically generated. DO NOT DIRECTLY EDIT.\n\n"
    for module, images_path in zip(modules, images_paths):
        header_border = "*" * len(module)
        sections += textwrap.dedent(
            """\
            {0}
            {1}
            {0}
            `Back to pymedphys <#pymedphys>`_

            .. raw:: html
                :file: {2}

        """.format(
                header_border, module, images_path
            )
        )

    save_file = os.path.join(save_directory, "graphs.txt")
    with open(save_file, "w") as file:
        file.write(sections)
