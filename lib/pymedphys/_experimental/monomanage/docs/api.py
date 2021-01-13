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

from ..draw import draw_all
from .graphs import write_graphs_rst


def pre_docs_build(pymedphys_dir):
    docs_directory = os.path.join(pymedphys_dir, "docs")
    docs_graphs = os.path.join(docs_directory, "graphs")

    draw_all(docs_graphs)
    write_graphs_rst(docs_graphs)
