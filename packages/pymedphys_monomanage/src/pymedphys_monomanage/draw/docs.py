import os
import textwrap

from glob import glob
from .utilities import remove_postfix

ROOT = os.getcwd()


def write_graphs_rst(save_directory):
    search_string = os.path.join(save_directory, "*.svg")

    svg_files = [
        os.path.basename(filepath)
        for filepath in sorted(glob(search_string))
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
