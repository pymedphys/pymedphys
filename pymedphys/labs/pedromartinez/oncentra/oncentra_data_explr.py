#############################START LICENSE##########################################
# Copyright (C) 2019 Pedro Martinez
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#############################END LICENSE##########################################


"""
###########################################################################################
#
#   Script name: Oncentra_DataExplr
#
#   Description: Tool for processing of Oncentra dose files
#
#   Example usage: python Oncentra_DataExplr.py "/file/"
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2019-05-10
#
###########################################################################################
"""

import argparse
import os

import pydicom


def process_directory(directy):
    """Process directory."""
    filetype = ""
    desc = ""
    print(directy)
    for subdir, dirs, files in os.walk(directy):  # pylint: disable = unused-variable
        for file in sorted(files):
            if os.path.splitext(file)[1] == ".dcm":
                dataset = pydicom.dcmread(os.path.join(subdir, file))
                # print(str.split(os.path.splitext(file)[0]))
                if str.split(os.path.splitext(file)[0])[0] == "RP":
                    try:
                        filetype = "Plan"
                        desc = dataset[0x300A, 0x0004].value
                    except:  # pylint: disable = bare-except
                        print("no description found")
                elif str.split(os.path.splitext(file)[0])[0] == "RD":
                    try:
                        filetype = "Dose"
                        desc = dataset[0x3004, 0x0006].value
                    except:  # pylint: disable = bare-except
                        print("no description found")
                elif str.split(os.path.splitext(file)[0])[0] == "RS":
                    # print(dataset)
                    # exit(0)
                    filetype = "Structure"
                    try:
                        desc = dataset[0x3006, 0x0006].value
                    except:  # pylint: disable = bare-except
                        print("no description found")
                else:
                    continue

                print(
                    "Type=", filetype, "Description=", desc, "Filepath=", directy + file
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory", help="path to folder")
    args = parser.parse_args()

    if args.directory:
        dirname = args.directory
        process_directory(dirname)
