###########################################################################################
#
#   Script name: oncentra_struct_rot
#
#   Description: Tool for rotating structures a given angle by the user or make the structures slices parallel to the <xy> axis
#   Example usage: python oncentra_struct_rot.py "/structure file/" -o "/output structure file/"
#
#   Author: Pedro Martinez
#   pedro.enrique.83@gmail.com
#   5877000722
#   Date:2019-05-10
#
###########################################################################################


import argparse
import math
import os

import numpy as np
from scipy.spatial.transform import Rotation as R

import pydicom

import inquirer


def rotate(dataset, filename, outname, struct_process):

    # we first find the center of mass of the strcuture
    k = 0
    elem = dataset[0x3006, 0x0039][struct_process]
    xs_el = []
    ys_el = []
    zs_el = []
    try:
        for contour in elem[0x3006, 0x0040]:
            for i in range(0, contour[0x3006, 0x0050].VM, 3):
                xs_el.append(contour[0x3006, 0x0050][i])
                ys_el.append(contour[0x3006, 0x0050][i + 1])
                zs_el.append(contour[0x3006, 0x0050][i + 2])
    except:  # pylint: disable = bare-except
        print("no contour data")

    k = k + 1
    coords_elem = np.transpose(np.vstack((xs_el, ys_el, zs_el)))
    cm_elem = np.average(coords_elem, 0)
    #    print(coords_elem,cm_elem)
    coords_offset = np.zeros_like(
        coords_elem
    )  # creating the matrix for the shifted coordinates
    coords_out = np.zeros_like(
        coords_elem
    )  # creating the matrix for the output coordinates

    # we shift the structure to the center of mass where we will rotate the structres around the axis
    coords_offset[:, 0] = coords_elem[:, 0] - cm_elem[0]
    coords_offset[:, 1] = coords_elem[:, 1] - cm_elem[1]
    coords_offset[:, 2] = coords_elem[:, 2] - cm_elem[2]

    questions = [
        inquirer.List(
            "type",
            message="Select the axis to apply the rotation",
            choices=["x", "y", "z"],
        )
    ]
    answers = inquirer.prompt(questions)
    print("The rotation will be applied around axis ->", answers["type"])

    if answers["type"] == "x":
        axis = "x"

    elif answers["type"] == "y":
        axis = "y"

    elif answers["type"] == "z":
        axis = "z"

    while True:  # example of infinite loops using try and except to catch only numbers
        line = input("Select the angle to rotate around the axis > ")
        try:
            angle = float(line.lower())  # temporarily since allows any range of numbers
            break
        except ValueError:  # pylint: disable = bare-except
            print("Please enter a valid option:")

    r1 = R.from_euler(
        axis, angle, degrees=True
    )  # this line builds the rotation matrix (in this case around the z axis)
    coords_rot1 = np.matmul(np.asarray(r1.as_dcm()), np.transpose(coords_offset))

    coords_out[:, 0] = coords_rot1[0, :] + cm_elem[0]
    coords_out[:, 1] = coords_rot1[1, :] + cm_elem[1]
    coords_out[:, 2] = coords_rot1[2, :] + cm_elem[2]

    try:
        k = 0
        for contour in elem[0x3006, 0x0040]:
            contour_slice = (
                []
            )  # we need to store the  x,y,z triplet values sequentially in a list
            for i in range(0, contour[0x3006, 0x0046].value):
                contour_slice.append(coords_out[k, 0])
                contour_slice.append(coords_out[k, 1])
                contour_slice.append(coords_out[k, 2])
                k = k + 1
            contour[
                0x3006, 0x0050
            ].value = contour_slice  # a slice of data gets written at a time

    except Exception as e:  # pylint: disable = broad-except
        print("no contour data", e)

    print("Writing output file")
    dirname = os.path.dirname(filename)
    if outname is not None:
        dataset.save_as(dirname + "/" + outname + ".dcm")  # this is working fine


def make_parallel(dataset, filename, outname, struct_process):

    # we first find the center of mass of the strcuture
    k = 0
    elem = dataset[0x3006, 0x0039][struct_process]
    xs_el = []
    ys_el = []
    zs_el = []
    try:
        for contour in elem[0x3006, 0x0040]:
            for i in range(0, contour[0x3006, 0x0050].VM, 3):
                xs_el.append(contour[0x3006, 0x0050][i])
                ys_el.append(contour[0x3006, 0x0050][i + 1])
                zs_el.append(contour[0x3006, 0x0050][i + 2])
    except:  # pylint: disable = bare-except
        print("no contour data")

    k = k + 1
    coords_elem = np.transpose(np.vstack((xs_el, ys_el, zs_el)))
    cm_elem = np.average(coords_elem, 0)
    print("cm_elem", cm_elem)
    coords_offset = np.zeros_like(
        coords_elem
    )  # creating the matrix for the shifted coordinates
    coords_out = np.zeros_like(
        coords_elem
    )  # creating the matrix for the output coordinates

    coords_offset[:, 0] = coords_elem[:, 0] - cm_elem[0]
    coords_offset[:, 1] = coords_elem[:, 1] - cm_elem[1]
    coords_offset[:, 2] = coords_elem[:, 2] - cm_elem[2]

    # print(coords_offset)
    # now the structure has been shifted to the coordinate origin we can proceed to find the normal of the first slice
    # for this we need to select the first three points (which presumably will belong to the same slice and find the vectors)
    n_points_slice0 = elem[0x3006, 0x0040][0][0x3006, 0x0046].value

    # selecting 3 points to define a plane
    x1 = np.transpose(coords_offset[int((n_points_slice0 - 1) / 3), :])
    x2 = np.transpose(coords_offset[int((n_points_slice0 - 1) / 2), :])
    x3 = np.transpose(coords_offset[int(n_points_slice0 - 1), :])

    v1 = x2 - x1
    v2 = x3 - x1

    #    print(v1)i
    #    print(v2)

    n_vec = np.cross(v1, v2)

    #    taking only the components in the <xy> plane
    n_vec_xy = n_vec[0:2]

    theta = math.acos(
        np.dot(n_vec, [0, 0, 1]) / np.linalg.norm(n_vec)
    )  # angle between the normal and the z-axis
    phi = math.acos(
        np.dot(n_vec_xy, [1, 0]) / np.linalg.norm(n_vec_xy)
    )  # angle between the projection of the normal and the x-axis

    if theta > math.pi / 2:
        theta = np.abs(math.pi - theta)

    if phi > math.pi / 2:
        phi = np.abs(math.pi - phi)

    #    print(math.degrees(theta),math.degrees(phi))

    r1 = R.from_euler(
        "z", -math.degrees(phi), degrees=True
    )  # this line builds the rotation matrix (in this case around the z axis)
    coords_rot1 = np.matmul(np.asarray(r1.as_dcm()), np.transpose(coords_offset))

    r2 = R.from_euler(
        "y", -math.degrees(theta), degrees=True
    )  # this line builds the rotation matrix (in this case around the x axis)
    coords_rot2 = np.matmul(np.asarray(r2.as_dcm()), coords_rot1)

    r3 = R.from_euler(
        "z", math.degrees(phi), degrees=True
    )  # this line builds the rotation matrix (in this case around the x axis)
    coords_rot3 = np.matmul(np.asarray(r3.as_dcm()), coords_rot2)

    coords_out[:, 0] = np.round(
        coords_rot3[0, :] + cm_elem[0], 2
    )  # restoring to the original location and rounding to two decimal places
    coords_out[:, 1] = np.round(coords_rot3[1, :] + cm_elem[1], 2)
    coords_out[:, 2] = np.round(coords_rot3[2, :] + cm_elem[2], 2)

    try:
        k = 0
        for contour in elem[0x3006, 0x0040]:
            contour_slice = (
                []
            )  # we need to store the  x,y,z triplet values sequentially in a list
            for i in range(0, contour[0x3006, 0x0046].value):
                contour_slice.append(coords_out[k, 0])
                contour_slice.append(coords_out[k, 1])
                contour_slice.append(coords_out[k, 2])
                k = k + 1
            contour[
                0x3006, 0x0050
            ].value = contour_slice  # a slice of data gets written at a time

    except Exception as e:  # pylint: disable = broad-except
        print("no contour data", e)

    print("Writing output file")
    dirname = os.path.dirname(filename)
    if outname is not None:
        dataset.save_as(dirname + "/" + outname + ".dcm")  # this is working fine


def process_struct(filename, outname):
    print("Starting struct calculation")
    dataset = pydicom.dcmread(filename)

    k = 0
    for elem in dataset[0x3006, 0x0020]:
        print(elem[0x3006, 0x0028].value, k)
        k = k + 1

    while True:  # example of infinite loops using try and except to catch only numbers
        line = input("Select the structure from the list > ")
        try:
            num1 = int(line.lower())  # temporarily since allows any range of numbers
            break
        except ValueError:  # pylint: disable = bare-except
            print("Please enter a valid option:")

    struct_process = num1
    # struct_process_name = [dataset[0x3006, 0x0020][num1][0x3006, 0x0028].value]

    questions = [
        inquirer.List(
            "type",
            message="Select the type of processing",
            choices=[
                "Rotation by an arbitrary angle",
                "Make slices parallel to the <xy> axis",
            ],
        )
    ]
    answers = inquirer.prompt(questions)
    print(answers["type"])

    if answers["type"] == "Rotation by an arbitrary angle":
        print("Please enter a valid option:")
        rotate(dataset, filename, outname, struct_process)
    elif answers["type"] == "Make slices parallel to the <xy> axis":
        make_parallel(dataset, filename, outname, struct_process)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o",
        "--output",
        nargs="?",
        type=argparse.FileType("w"),
        help="output file, in DICOM format",
    )
    parser.add_argument(
        "structure", type=str, help="Input the structure file, in DICOM format"
    )
    args = parser.parse_args()

    # parser.add_argument('-m' ,'--measurement' , nargs=3, metavar=('x', 'y', 'z'),
    #                        help="Specify the shift in x, y, z in mm", type=float,
    #                        default=[0,0,0])

    if args.structure:
        structname = args.structure
        if args.output:
            outf = args.output
            process_struct(structname, outf.name)
        else:
            process_struct(structname, None)
