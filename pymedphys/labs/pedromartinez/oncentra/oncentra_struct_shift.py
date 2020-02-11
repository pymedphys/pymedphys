###########################################################################################
#
#   Script name: oncentra_struct_shift
#
#   Description: Tool for processing of Oncentra structure files
#
#   Example usage: python oncentra_struct_shift.py "/structure file/" -m dx dy dz -o "/output structure file/"
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2019-05-10
#
###########################################################################################


import argparse
import os
import sys

import numpy as np

import pydicom

os.environ["ETS_TOOLKIT"] = "wx"
np.set_printoptions(threshold=sys.maxsize)


def PolyArea(x, y):
    return 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def process_struct(filename, meas_params, dirname, structname_o):
    print("Starting struct calculation")
    dataset = pydicom.dcmread(filename)

    k = 0
    for elem in dataset[0x3006, 0x0020]:
        print(elem[0x3006, 0x0028].value, k)
        k = k + 1

    while True:  # example of infinite loops using try and except to catch only numbers
        line = input("Select the structure to shift > ")
        try:
            num1 = int(line.lower())  # temporarily since allows any range of numbers
            break
        except ValueError:  # pylint: disable = bare-except
            print("Please enter a valid option:")

    # struct_sel_name = dataset[0x3006, 0x0020][num1][0x3006, 0x0028].value

    dz = abs(
        dataset[0x3006, 0x0039][num1][0x3006, 0x0040][2][0x3006, 0x0050][2]
        - dataset[0x3006, 0x0039][num1][0x3006, 0x0040][1][0x3006, 0x0050][2]
    )
    print("dz=", dz)
    print(meas_params)

    elem = dataset[0x3006, 0x0039][num1]

    try:
        for contour in elem[
            0x3006, 0x0040
        ]:  # the area between the two surfaces must be calculated for every contour if there are two areas in each of the contours
            for i in range(0, contour[0x3006, 0x0050].VM, 3):
                contour[0x3006, 0x0050].value[i] = (
                    contour[0x3006, 0x0050].value[i] + meas_params[0]
                )
                contour[0x3006, 0x0050].value[i + 1] = (
                    contour[0x3006, 0x0050].value[i + 1] + meas_params[1]
                )
                contour[0x3006, 0x0050].value[i + 2] = (
                    contour[0x3006, 0x0050].value[i + 2] + meas_params[2]
                )

    except:  # pylint: disable = bare-except
        print("no contour data")

    if structname_o is not None:
        print(dirname, structname_o)
        dataset.save_as(dirname + "/" + structname_o + ".dcm")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # parser.add_argument('-s', '--structure', nargs='?', type=argparse.FileType('r'), help='structure file, in DICOM format')
    parser.add_argument("structure", type=str, help="Input the structure file")
    parser.add_argument(
        "-o",
        "--output",
        nargs="?",
        type=argparse.FileType("w"),
        help="output structure filename, the file will be located in the same folder as the original, in DICOM format",
    )
    parser.add_argument(
        "-m",
        "--measurement",
        nargs=3,
        metavar=("x", "y", "z"),
        help="Specify the shift in x, y, z in mm",
        type=float,
        default=[0, 0, 0],
    )
    args = parser.parse_args()

    mp = args.measurement

    # f = plt.figure()
    # ax = f.add_subplot(111, projection="3d")
    # ax.set_xlabel("x distance [mm]")
    # ax.set_ylabel("y distance [mm]")
    # ax.set_zlabel("z distance [mm]")

    if args.structure:
        sname = args.structure
        dname = os.path.dirname(sname)
        if args.output:
            sname_o = args.output
            process_struct(sname, mp, dname, sname_o.name)
        else:
            process_struct(sname, mp, dname, None)
