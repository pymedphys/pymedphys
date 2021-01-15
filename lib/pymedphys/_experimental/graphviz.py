# Copyright (C) 2019,2021 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pathlib
import shutil
import subprocess
import tempfile


def dot_string_to_svg(dot_contents, output_path):
    tred = shutil.which("tred")
    dot = shutil.which("dot")

    if not tred or not dot:
        raise ValueError(
            "Graph not drawn, please install `graphviz` and add it to "
            "your path.\nOn Windows this is done with "
            "`choco install graphviz.portable`."
        )

    with tempfile.TemporaryDirectory() as directory:
        dot_file = pathlib.Path(directory).joinpath("initial.dot")
        with open(dot_file, "w") as f:
            f.write(dot_contents)

        tred_process = subprocess.Popen([tred, dot_file], stdout=subprocess.PIPE)
        data = tred_process.stdout.read()
        tred_process.wait()

        reduced_dot_file = pathlib.Path(directory).joinpath("reduced.dot")
        with open(reduced_dot_file, "wb") as f:
            f.write(data)

        svg_path = pathlib.Path(directory).joinpath("graph.svg")
        subprocess.check_output([dot, "-Tsvg", reduced_dot_file, "-o", svg_path])

        shutil.move(svg_path, output_path)
