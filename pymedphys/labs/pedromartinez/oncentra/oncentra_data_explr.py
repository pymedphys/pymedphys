#############################START LICENSE##########################################
# Copyright (C) 2019 Pedro Martinez
#
# # This program is free software: you can redistribute it and/or modify
# # it under the terms of the GNU Affero General Public License as published
# # by the Free Software Foundation, either version 3 of the License, or
# # (at your option) any later version (the "AGPL-3.0+").
#
# # This program is distributed in the hope that it will be useful,
# # but WITHOUT ANY WARRANTY; without even the implied warranty of
# # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# # GNU Affero General Public License and the additional terms for more
# # details.
#
# # You should have received a copy of the GNU Affero General Public License
# # along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# # ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# # Affero General Public License. These additional terms are Sections 1, 5,
# # 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# # where all references to the definition "License" are instead defined to
# # mean the AGPL-3.0+.
#
# # You should have received a copy of the Apache-2.0 along with this
# # program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.
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
