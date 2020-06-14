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
