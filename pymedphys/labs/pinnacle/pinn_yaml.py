# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

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
# The following needs to be removed before leaving labs
# pylint: skip-file

import io
import re
import sys

import yaml


def pinn_to_dict(filename):

    result = None
    pinn_yaml = ""
    with io.open(filename, "r", encoding="ISO-8859-1", errors="ignore") as fp:
        data = fp.readlines()

        # Split data into smaller chunks, if first line appears more than one
        # Useful for plan.Trial files with more than one Trial
        first_line = data[0]
        indices = [i for i, line in enumerate(data) if line == first_line]

        for i in range(len(indices)):

            next_index = -1

            if i + 1 < len(indices):
                next_index = indices[i + 1]

                # If there are multiple segments, return list, otherwise just the dict
                if not type(result) == list:
                    result = []

            split_data = data[indices[i] : next_index]

            if type(result) == list:
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
    for i, line in enumerate(data, 0):

        # Remove comment lines
        if re.search("^\/\*", line) or in_comment:
            in_comment = True
            continue

        if re.search("\*\/", line):
            in_comment = False
            continue

        # Get the indentation of this line
        thisIndent = len(re.match("^\s*", line).group())

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
            line = " " * thisIndent + "- " + re.sub("^\s*", "", line)

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
