# -----
# Uploaded by lipteck 10-Feb-2022, credit of Simon Biggs.
# -----
# This mm.py script performs batch MetersetMap (mm) comparison of
# Elekta TRF files with dicom RTPlan (trf vs dcm) on a D drive
# The Metsersetmap gamma results and calculation time are shown as it processes the data.
# -----
# Create directories with folders as below:
# D:/mm/new/dcm    # put dcm files RTPlan here e.g. FP12345678_testplan.dcm
# D:/mm/new/trf    # create folders of patientID manually here and put the trf files inside
# one after all the beams of the plan are delivered
# e.g. D:/mm/new/trf/FP12345678/beam1.trf
# e.g. D:/mm/new/trf/FP12345678/beam2.trf
# e.g. D:/mm/new/trf/FP12345678/beam3.trf
# This approach works around the issue of trf with file name Z .trf
# Ensure that each patient folder with trf has a corresponding dcm for this script to work.
# D:/mm/completed/dcm    # processed dcm files will be moved here
# D:/mm/completed/trf    # processed patient folders with trf files will be moved here
# D:/mm/mmresults.csv    # create a blank mmresults.txt and rename extention to csv
# The script will append the batch results in this csv file.
# Afterthat, we can then run mmplot.py to make a boxplot of the accumulative results
# tested with pymedphys 0.37.1
# This script does not handle situation of patients with multiple plans concurrently
# because we use patientID as the folder name for trf.
# It has to be analysed one after another.
# -----

# Importing the required libraries
import pathlib  # for filepath path tooling
import os
from datetime import datetime
import numpy as np  # for array tooling, and compiling trf metersetmaps
import matplotlib.pyplot as plt  # for plotting
import pymedphys

# File Path Configurations

# trf directory
trf_directory = pathlib.Path(r"D:\mm\new\trf")

# dcm directory
dcm_directory = pathlib.Path(r"D:\mm\new\dcm")

output_directory = pathlib.Path(r"D:\mm\completed\pdf")
pdf_filepath = output_directory
png_directory = pathlib.Path(r"D:\mm\completed\png")
pdf_filepath = pdf_directory

# MU Density and Gamma configuration
GRID = pymedphys.metersetmap.grid()
COORDS = (GRID["jaw"], GRID["mlc"])

GAMMA_OPTIONS = {
    "dose_percent_threshold": 2,
    "distance_mm_threshold": 0.5,
    "local_gamma": True,
    "quiet": True,
    "max_gamma": 2,
}

# loop metersetmap by the patient_folders available in the trf_source directory
trf_source = r"D:\mm\new\trf"
dcm_source = r"D:\mm\new\dcm"

patient_folders = os.listdir(trf_source)
dcm_files = os.listdir(dcm_source)

# Ensure the number of patient_folders match the number of dcm files
if len(patient_folders) == len(dcm_files) and len(patient_folders) > 0:
    print("There are", len(patient_folders), "patient folders:")
    # list of patient folders
    print(patient_folders)
    print()
    index = 1

    # record the datetime in HH:MM:SS format
    begin = datetime.now()

    # loop though all patient folders
    for patient_id in patient_folders:
        start = datetime.now()
        print("Working on patient index", index, "/", len(patient_folders), "...")
        # paths to dcm and trf
        dcm_path = list(dcm_directory.glob(f"{patient_id}*.dcm"))[-1]
        trf_paths = trf_directory.glob(f"{patient_id}/*.trf")
        print("Calculating metersetmap...")
        # Creating the Delivery Objects for trf files and dcm
        # delivery_trf = pymedphys.Delivery.from_trf(trf_paths)
        # compiling the trf metersetmaps by Simon Biggs
        collected_meterset_maps = []
        for path in trf_paths:
            delivery = pymedphys.Delivery.from_trf(path)
            meterset_map = delivery.metersetmap()
            collected_meterset_maps.append(meterset_map)
        combined_meterset_map = np.sum(collected_meterset_maps, axis=0)

        delivery_dcm = pymedphys.Delivery.from_dicom(dcm_path)

        # metersetmap for trf and dcm
        metersetmap_trf = combined_meterset_map
        metersetmap_dcm = delivery_dcm.metersetmap()

        # Calculating Gamma
        # PyMedPhys also has within it tooling to calculate Gamma. This is done below.
        def to_tuple(array):
            return tuple(map(tuple, array))

        gamma = pymedphys.gamma(
            COORDS,
            to_tuple(metersetmap_dcm),
            COORDS,
            to_tuple(metersetmap_trf),
            **GAMMA_OPTIONS,
        )

        # Create Plotting and Reporting Functions
        # So that we can view the result as well as create a PDF that can be stored
        # within Mosaiq the following functions create these plots using the matplotlib library.

        def plot_gamma_hist(gamma, percent, dist):
            valid_gamma = gamma[~np.isnan(gamma)]
            plt.hist(valid_gamma, 50, density=True)
            pass_ratio = np.sum(valid_gamma <= 1) / len(valid_gamma)
            print("Metersetmap Results:")
            print("PatientID:", patient_id)
            print("Started:", start)
            print(
                "Local Gamma ({0}%/{1}mm) | Percent Pass: {2:.2f} % | Mean Gamma: {3:.2f} | Max Gamma: {4:.2f}".format(
                    percent,
                    dist,
                    pass_ratio * 100,
                    np.mean(valid_gamma),
                    np.max(valid_gamma),
                )
            )

            # Append the metersetmap results to mmresults.txt file
            # Date,PatientID,Gamma,Mean Gamma,Max Gamma
            with open(r"D:\mm\mmresults.csv", "a") as file:
                file.write(str(start))
                file.write(",")
                file.write(patient_id)
                file.write(",")
                file.write(str(pass_ratio * 100))
                file.write(",")
                file.write(str(np.mean(valid_gamma)))
                file.write(",")
                file.write(str(np.max(valid_gamma)))
                file.write("\n")

            plt.title(
                "Local Gamma ({0}%/{1}mm) | Percent Pass: {2:.2f} % | Mean Gamma: {3:.2f} | Max Gamma: {4:.2f}".format(
                    percent,
                    dist,
                    pass_ratio * 100,
                    np.mean(valid_gamma),
                    np.max(valid_gamma),
                )
            )

        def plot_and_save_results(
            metersetmap_dcm,
            metersetmap_trf,
            gamma,
            png_filepath,
            pdf_filepath,
            header_text="",
            footer_text="",
        ):
            # diff = metersetmap_trf - metersetmap_tel
            evaluation_metersetmap = metersetmap_trf
            reference_metersetmap = metersetmap_dcm  # or metersetmap_tel
            diff = evaluation_metersetmap - reference_metersetmap
            # largest_item = np.max(np.abs(diff))
            largest_metersetmap = np.max(
                [np.max(evaluation_metersetmap), np.max(reference_metersetmap)]
            )
            largest_diff = np.max(np.abs(diff))
            widths = [1, 1]
            heights = [0.5, 1, 1, 1, 0.4]
            gs_kw = dict(width_ratios=widths, height_ratios=heights)
            fig, axs = plt.subplots(5, 2, figsize=(10, 16), gridspec_kw=gs_kw)
            gs = axs[0, 0].get_gridspec()

            for ax in axs[0, 0:]:
                ax.remove()

            for ax in axs[1, 0:]:
                ax.remove()

            for ax in axs[4, 0:]:
                ax.remove()

            axheader = fig.add_subplot(gs[0, :])
            axhist = fig.add_subplot(gs[1, :])
            axfooter = fig.add_subplot(gs[4, :])

            axheader.axis("off")
            axfooter.axis("off")

            axheader.text(0, 0, header_text, ha="left", wrap=True, fontsize=21)
            axfooter.text(0, 1, footer_text, ha="left", va="top", wrap=True, fontsize=6)

            plt.sca(axs[2, 0])
            pymedphys.metersetmap.display(
                GRID, reference_metersetmap, vmin=0, vmax=largest_metersetmap
            )
            axs[2, 0].set_title("Reference MetersetMap")

            plt.sca(axs[2, 1])
            pymedphys.metersetmap.display(
                GRID, evaluation_metersetmap, vmin=0, vmax=largest_metersetmap
            )
            axs[2, 1].set_title("Evaluation MetersetMap")

            plt.sca(axs[3, 0])
            pymedphys.metersetmap.display(
                GRID, diff, cmap="seismic", vmin=-largest_diff, vmax=largest_diff
            )
            plt.title("Evaluation - Reference")

            plt.sca(axs[3, 1])
            pymedphys.metersetmap.display(GRID, gamma, cmap="coolwarm", vmin=0, vmax=2)
            plt.title(
                "Local Gamma | "
                f"{GAMMA_OPTIONS['dose_percent_threshold']}%/"
                f"{GAMMA_OPTIONS['distance_mm_threshold']}mm"
            )

            plt.sca(axhist)
            plot_gamma_hist(
                gamma,
                GAMMA_OPTIONS["dose_percent_threshold"],
                GAMMA_OPTIONS["distance_mm_threshold"],
            )

            return fig

        # results - call this function
        plot_and_save_results(
            metersetmap_dcm,
            metersetmap_trf,
            gamma,
            png_filepath,
            pdf_filepath,
            header_text="",
            footer_text="",
        )
        end = datetime.now()
        print("Ended:", end)
        print("Execution time:", end - start)
        print()
        index += 1
        # show plot, for running single case, disabled for batch calculation
        # plt.show()   # show report

    # record the finishing time
    finish = datetime.now()
    print("Summary:")
    print("Started:", begin)
    print("Ended:", finish)
    print("Total execution time:", finish - begin)
    print()

    # move processed data to a completed directory
    import os
    import shutil

    # move dcm files
    src_dcm = r"D:/mm/new/dcm/"
    dst_dcm = r"D:/mm/completed/dcm/"
    filelist = os.listdir(src_dcm)
    for file in filelist:
        shutil.move(src_dcm + file, dst_dcm + file)

    # move trf folders
    src_trf = r"D:/mm/new/trf/"
    dst_trf = r"D:/mm/completed/trf/"
    folderlist = os.listdir(src_trf)
    for folder in folderlist:
        shutil.move(src_trf + folder, dst_trf + folder)

    # Run mmplot.py to make a boxplot

# a simple number of patient folders vs dcm files check
else:
    print("The number of patient folders and dcm files are not equal")
    print("or no patient folders present!")
    print(len(patient_folders), "patient folders vs", len(dcm_files), "dcm files")

# end
