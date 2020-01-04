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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Create a report of csv file comparisons.
"""

import os

import numpy as np
import pandas as pd

from csv_compare import compare as _compare
from IPython.display import HTML, Markdown, display
from jinja2 import Template


def _create_comparison_table(data):
    """Create a table for displaying the results.
    """
    keys = np.sort(list(data.keys()))
    return pd.DataFrame(
        columns=["Result"], index=keys, data=[data[key] for key in keys]
    )


def create_reports(input_directory, output_directory):
    """Create a report for every timestamp within the input directory.
    """
    all_comparison_data = _compare(input_directory)

    for timestamp, comparison_data in all_comparison_data.items():

        key = comparison_data.keys()
        assert len(key) == 1, "More than one comparison report not yet implemented"
        centre_names = list(key)[0]

        field_overviews = {
            centre_name: pd.read_csv(
                os.path.join(input_directory, timestamp, centre_name, "fields.csv"),
                index_col=0,
            )
            for centre_name in centre_names
        }

        output_filepath = r"{}\\{}_timestamp_{}.html".format(
            output_directory, os.path.basename(input_directory), timestamp
        )
        _create_report(output_filepath, comparison_data[centre_names], field_overviews)


def _create_report(output_filepath, comparison_data, field_overviews):
    """Create the report according to report_template.html.
    """
    nbccc_fields = field_overviews["nbccc"]
    rccc_fields = field_overviews["rccc"]
    tests = _create_comparison_table(comparison_data)

    with open("report_template.html") as file:
        template_string = file.read()

    template = Template(template_string)
    html = template.render(
        nbccc_fields=nbccc_fields.to_html(),
        rccc_fields=rccc_fields.to_html(),
        results=tests.to_html(),
    )

    display(Markdown("# Filepath: {}".format(output_filepath)))
    display(HTML(html))

    with open(output_filepath, "w") as html_file:
        html_file.write(html)
