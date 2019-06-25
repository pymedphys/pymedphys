#!/usr/bin/env python
# coding=utf-8

import re
import sys
import io
import yaml


def pinn_to_dict(filename):

    result = None
    pinn_yaml = ''
    with io.open(filename, "r", encoding='ISO-8859-1', errors='ignore') as fp:
        data = fp.readlines()

        # Split data into smaller chunks, if first line appears more than one
        # Useful for plan.Trial files with more than one Trial
        first_line = data[0]
        indices = [i for i, line in enumerate(data) if line == first_line]

        for i in range(len(indices)):

            next_index = -1

            if i+1 < len(indices):
                next_index = indices[i+1]

                # If there are multiple segments, return list, otherwise just the dict
                if not type(result) == list:
                    result = []

            split_data = data[indices[i]:next_index]

            if type(result) == list:
                d = yaml.safe_load(convert_to_yaml(split_data))
                result.append(d[list(d.keys())[0]])
            else:
                result = yaml.safe_load(convert_to_yaml(split_data))

    return result


def convert_to_yaml(data):

    out = ''
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
            line = ' ' * thisIndent + '- ' + re.sub("^\s*", "", line)

        # Replace ={ and = with : for assignment
        line = re.sub(" ={", " :", line)
        line = re.sub(" = ", " : ", line)

        # Remove semicolons at end of lines
        line = re.sub(";$", "", line)

        out += '' + line
        c += 1

    return out


def pinn_to_yaml(filename):

    with io.open(filename, "r", encoding='ISO-8859-1', errors='ignore') as fp:
        data = fp.readlines()
        return convert_to_yaml(data)
