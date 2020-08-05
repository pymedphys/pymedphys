from collections import Counter

import numpy as np

from matplotlib import pyplot as plt

import pydicom


def list_structures(label_paths):
    structs = []
    for path in label_paths:
        dicom_structures = pydicom.dcmread(path, force=True)
        dcm_rs_struct_names = [
            structure.ROIName for structure in dicom_structures.StructureSetROISequence
        ]
        structs.append(dcm_rs_struct_names)

    structs = [item for sublist in structs for item in sublist]
    structs = Counter(structs)
    mydict = structs
    common_structs = structs.most_common()

    structs = sorted(structs.items())

    print("\n")
    print("ext.list_structures")
    print("===============")
    structs_in_all = [
        struct for struct, number in mydict.items() if number == len(label_paths)
    ]
    print("Structures in all cases:", len(structs_in_all), "\n")
    for struct in structs_in_all:
        print(struct)

    print("\n")
    print("----------")
    print("Structures:", len(structs), "\n")
    for struct, number in structs:
        print(struct, ":", number)
    print("\n")


def count_structure_occurs(input_paths, label_paths, structure_names):
    num_occurs = {name: 0 for name in structure_names}
    num_slices = len(input_paths)

    for path in label_paths:
        dicom_structures = pydicom.dcmread(path, force=True)
        dcm_rs_struct_names = [
            structure.ROIName for structure in dicom_structures.StructureSetROISequence
        ]
        names_to_pull = [
            name for name in dcm_rs_struct_names if name in structure_names
        ]
        structure_indexes = [dcm_rs_struct_names.index(name) for name in names_to_pull]
        for mask_index, structure_index in enumerate(structure_indexes):
            struct_name = structure_names[mask_index]
            z = [
                z_slice.ContourData[2::3][0]
                for z_slice in dicom_structures.ROIContourSequence[
                    structure_index
                ].ContourSequence
            ]
            # only want unique slices so we can count
            z = list(set(z))
            number_contour_slices = len(z)
            num_occurs[struct_name] += number_contour_slices

    for struct_name in num_occurs:
        num_occurs[struct_name] /= num_slices

    print("\n")
    print("Slice occurance ratio:")
    print("===============")
    for struct_name in num_occurs:
        print(struct_name, ":", num_occurs[struct_name])
    print("\n")


def get_images(paths):
    images = []
    for img_path in paths:
        dcm = pydicom.dcmread(img_path, force=True)
        try:
            dcm.file_meta.TransferSyntaxUID
        except AttributeError:
            dcm.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
        img = dcm.pixel_array
        images.append(img)

    return images


def plot_batch_predict(model, test_inputs, test_truths, x=10, batch_size=5):

    y_input = test_inputs[x : x + batch_size]
    y_true = test_truths[x : x + batch_size]

    print("Input shape:", y_input.shape)
    print("Truth shape: ", y_true.shape)

    y_pred = model.predict(y_input)
    print("Predict shape:", y_pred.shape)

    y_pred_round = np.round(y_pred)

    diff = y_pred_round - y_true

    # define the figure size and grid layout properties
    cols = 4 * y_true.shape[-1] + 1
    rows = batch_size
    figsize = np.array([cols, rows]) * 10

    fig, axs = plt.subplots(rows, cols, figsize=figsize, sharey=True)

    for ax in axs.flat:
        ax.set_xticks([])
        ax.set_yticks([])

    for batch, row in enumerate(axs):
        x = 0
        for i in range(y_true.shape[-1]):
            row[i + x].imshow(y_input[batch, ..., i])
            row[i + x].set_title("Truth")
            x += 1
            row[i + x].imshow(y_true[batch, ..., i])
            row[i + x].set_title("Truth")
            x += 1
            row[i + x].imshow(y_pred[batch, ..., i])
            row[i + x].set_title("Probability")
            x += 1
            row[i + x].imshow(y_pred_round[batch, ..., i])
            row[i + x].set_title("Prediction")
            x += 1
            row[i + x].imshow(diff[batch, ..., i])
            row[i + x].set_title("Difference")
