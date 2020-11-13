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


import os

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .constants import GImplementationClassUID, GTransferSyntaxUID

# This function will create dicom image files for each slice using the
# condensed pixel data from file ImageSet_%s.img


def create_image_files(image, export_path):

    # TODO: Fix this function, output not working
    image.logger.warn("Creating image files: The output of these are not correct!")

    patient_info = image.pinnacle.patient_info
    image_header = image.image_header
    image_info = image.image_info
    image_set = image.image_set
    currentpatientposition = image_header["patient_position"]

    modality = "CT"
    try:
        # Also should come from header file, but not always present
        modality = image_header["modality"]
    except KeyError:
        pass  # Incase it is not present in header

    img_file = os.path.join(image.path, f"ImageSet_{image.image['ImageSetID']}.img")
    if os.path.isfile(img_file):
        allframeslist = []
        pixel_array = np.fromfile(img_file, dtype=np.short)
        # will loop over every frame
        for i in range(0, int(image_header["z_dim"])):
            frame_array = pixel_array[
                i
                * int(image_header["x_dim"])
                * int(image_header["y_dim"]) : (i + 1)
                * int(image_header["x_dim"])
                * int(image_header["y_dim"])
            ]
            allframeslist.append(frame_array)
    image.logger.debug("Length of frames list: %s", len(allframeslist))
    image.logger.debug(image_info[0])

    curframe = 0
    for info in image_info:
        sliceloc = -info["TablePosition"] * 10
        instuid = info["InstanceUID"]
        classuid = info["ClassUID"]
        slicenum = info["SliceNumber"]

        dateofscan = image_set["scan_date"]
        timeofscan = image_set["scan_time"]

        file_meta = pydicom.dataset.Dataset()
        file_meta.MediaStorageSOPClassUID = classuid
        file_meta.MediaStorageSOPInstanceUID = instuid
        file_meta.TransferSyntaxUID = GTransferSyntaxUID
        # this value remains static since implementation for creating
        # file is the same
        file_meta.ImplementationClassUID = GImplementationClassUID

        image_file_name = f"{modality}.{instuid}.dcm"
        ds = pydicom.dataset.FileDataset(
            image_file_name, {}, file_meta=file_meta, preamble=b"\x00" * 128
        )

        ds.SpecificCharacterSet = "ISO_IR 100"
        ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
        ds.AccessionNumber = ""
        ds.SOPClassUID = classuid
        ds.SOPInstanceUID = instuid
        ds.StudyDate = dateofscan
        ds.SeriesDate = dateofscan
        ds.AcquisitionDate = dateofscan
        ds.ContentDate = dateofscan
        ds.AcquisitionTime = timeofscan
        ds.Modality = modality
        # This should come from Manufacturer in header, but for some
        # patients it isn't set??
        ds.Manufacturer = ""
        ds.StationName = modality
        ds.PatientsName = patient_info["FullName"]
        ds.PatientID = patient_info["MedicalRecordNumber"]
        ds.PatientsBirthDate = patient_info["DOB"]
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1
        ds.RescaleIntercept = -1024
        ds.RescaleSlope = 1.0
        # ds.kvp = ?? This should be peak kilovoltage output of x ray
        # generator used
        ds.PatientPosition = currentpatientposition
        # this is probably x_pixdim * xdim = y_pixdim * ydim
        ds.DataCollectionDiameter = (
            float(image_header["x_pixdim"]) * 10 * float(image_header["x_dim"])
        )
        # ds.SpatialResolution = 0.35  # ???????
        # # ds.DistanceSourceToDetector = #???
        # # ds.DistanceSourceToPatient = #????
        # ds.GantryDetectorTilt = 0.0  # ??
        # ds.TableHeight = -158.0  # ??
        # ds.RotationDirection = "CW"  # ???
        # ds.ExposureTime = 1000  # ??
        # ds.XRayTubeCurrent = 398  # ??
        # ds.GeneratorPower = 48  # ??
        # ds.FocalSpots = 1.2  # ??
        # ds.ConvolutionKernel = "STND"  # ????
        ds.SliceThickness = float(image_header["z_pixdim"]) * 10
        ds.NumberOfSlices = int(image_header["z_dim"])
        # ds.StudyInstanceUID = studyinstuid
        # ds.SeriesInstanceUID = seriesuid
        ds.FrameOfReferenceUID = info["FrameUID"]
        ds.StudyInstanceUID = info["StudyInstanceUID"]
        ds.SeriesInstanceUID = info["SeriesUID"]
        # problem, some of these are repeated in image file so not sure
        # what to do with that
        ds.InstanceNumber = slicenum
        ds.ImagePositionPatient = [
            -float(image_header["x_pixdim"]) * 10 * float(image_header["x_dim"]) / 2,
            -float(image_header["y_pixdim"]) * 10 * float(image_header["y_dim"]) / 2,
            sliceloc,
        ]
        if "HFS" in currentpatientposition or "FFS" in currentpatientposition:
            ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, -0.0]
        elif "HFP" in currentpatientposition or "FFP" in currentpatientposition:
            ds.ImageOrientationPatient = [-1.0, 0.0, 0.0, 0.0, -1.0, -0.0]
        ds.PositionReferenceIndicator = "LM"  # ???
        ds.SliceLocation = sliceloc
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.Rows = int(image_header["x_dim"])
        ds.Columns = int(image_header["y_dim"])
        ds.PixelSpacing = [
            float(image_header["x_pixdim"]) * 10,
            float(image_header["y_pixdim"]) * 10,
        ]

        ds.PixelData = allframeslist[curframe].tostring()

        output_file = os.path.join(export_path, image_file_name)
        image.logger.info("Creating image: %s", output_file)
        ds.save_as(output_file)
        curframe = curframe + 1


def convert_image(image, export_path):

    image.logger.debug(
        "Converting image patient name, birthdate and id to match pinnacle"
    )

    dicom_directory = os.path.join(
        image.path, f"ImageSet_{image.image['ImageSetID']}.DICOM"
    )

    if not os.path.exists(dicom_directory):
        # Image set folder not found, need to ignore patient
        # Will want to call a function to be written that will create image set
        # files from the condensed pixel data file
        image.logger.info("Dicom Image files do not exist. Creating image files")
        create_image_files(image, export_path)
        return

    for file in os.listdir(dicom_directory):

        # try:
        imageds = pydicom.read_file(os.path.join(dicom_directory, file), force=True)

        imageds.PatientName = image.pinnacle.patient_info["FullName"]
        imageds.PatientID = image.pinnacle.patient_info["MedicalRecordNumber"]
        imageds.PatientBirthDate = image.pinnacle.patient_info["DOB"]

        if not "SOPInstanceUID" in imageds:
            image.logger.warn("Unable to process image: %s", file)
            continue

        preamble = getattr(imageds, "preamble", None)
        if not preamble:
            preamble = b"\x00" * 128

        output_file = os.path.join(
            export_path, f"{image.image['Modality']}.{imageds.SOPInstanceUID}.dcm"
        )

        imageds.save_as(output_file)
        image.logger.info("Exported: %s to %s", file, output_file)
