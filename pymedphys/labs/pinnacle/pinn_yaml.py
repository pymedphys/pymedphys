# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This work is derived from:
# https://github.com/AndrewWAlexander/Pinnacle-tar-DICOM
# which is released under the following license:

# Copyright (c) [2017] [Colleen Henschel, Andrew Alexander]

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import io
import re

from pymedphys._imports import yaml


def pinn_to_dict(filename):

    result = None
    with io.open(filename, "r", encoding="ISO-8859-1", errors="ignore") as fp:
        data = fp.readlines()

        # Split data into smaller chunks, if first line appears more than one
        # Useful for plan.Trial files with more than one Trial
        first_line = data[0]
        indices = [i for i, line in enumerate(data) if line == first_line]

        for i, _ in enumerate(indices):

            next_index = -1

            if i + 1 < len(indices):
                next_index = indices[i + 1]

                # If there are multiple segments, return list, otherwise just the dict
                if not isinstance(result, list):
                    result = []

            split_data = data[indices[i] : next_index]

            if isinstance(result, list):
                d = yaml.safe_load(convert_to_yaml(split_data))
                result.append(d[list(d.keys())[0]])
            else:
                result = yaml.safe_load(convert_to_yaml(split_data))

    return result


def convert_to_yaml(data):

    out = ""
    listIndents = []
    in_comment = False
    c = 0
    for _, line in enumerate(data, 0):

        # Remove comment lines
        if re.search(r"^\/\*", line) or in_comment:
            in_comment = True
            continue

        if re.search(r"\*\/", line):
            in_comment = False
            continue

        # Get the indentation of this line
        thisIndent = len(re.match(r"^\s*", line).group())

        # Check for start list/array
        if re.search("Array ={", line) or re.search("List ={", line):
            listIndents.append(thisIndent)

        # Check for end list/array
        if re.search("}", line) and thisIndent in listIndents:
            listIndents.pop()

        # If this is the end of an object, discard as not needed for YAML
        if re.search("}", line):
            continue

        # If this line is one indentation in from a start of list,
        # add '-' for YAML sequence
        if thisIndent - 2 in listIndents:
            spaces = " " * thisIndent
            subbed_line = re.sub(r"^\s*", "", line)
            line = f"{spaces}- {subbed_line}"

        # Replace ={ and = with : for assignment
        line = re.sub(" ={", " :", line)
        line = re.sub(" = ", " : ", line)

        # Remove semicolons at end of lines
        line = re.sub(";$", "", line)

        out += "" + line
        c += 1

    return out


def pinn_to_yaml(filename):

    with io.open(filename, "r", encoding="ISO-8859-1", errors="ignore") as fp:
        data = fp.readlines()
        return convert_to_yaml(data)
