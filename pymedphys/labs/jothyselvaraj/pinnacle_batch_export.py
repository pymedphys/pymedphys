# Copyright (C) 2019 Jothy Selvaraj

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


import os
import re
import shutil
import tarfile

import numpy as np

import xlrd
from pymedphys.labs.pinnacle import PinnacleExport


class DCMExporter:
    WorkingPath = ""
    PinnPath = ""
    PinnArchive = ""
    PinnArchivePat = ""
    ArchivePath = ""
    CurPatientFolder = ""
    CurPatFilePath = ""
    PatNamesList = []
    CurPatDatasetFolder = ""
    ExportPath = ""

    def __init__(self, WorkingPath, PinnPath, PinnArchive, ExportFolder):
        self.WorkingPath = WorkingPath
        self.PinnPath = PinnPath
        self.PinnArchive = PinnArchive
        self.ExportPath = ExportFolder
        self.Initialize()

    def Initialize(self):
        self.ArchivePath = os.path.join(self.WorkingPath, "Pinn")
        # self.ExportPath=os.path.join(self.WorkingPath,"Output")
        shutil.rmtree(self.ExportPath, ignore_errors=True)
        os.makedirs(self.ExportPath)

    def ExportDCM(self):
        print("Extracting tar file...")
        t = tarfile.open(self.CurPatFilePath)
        for m in t.getmembers():
            if not ":" in m.name:
                t.extract(m, path=self.CurPatientPinnFolder)
        # print('Extraction done.')

        SubFolders = os.listdir(self.CurPatientPinnFolder)
        r = re.compile("Patient_", re.IGNORECASE)
        DatasetFolder = list(filter(r.match, SubFolders))[0]
        self.CurPatDatasetFolder = self.CurPatientPinnFolder + "\\" + DatasetFolder

        pinn = PinnacleExport(self.CurPatDatasetFolder, None)
        pinn.logger.setLevel(
            "ERROR"
        )  # Set the log level to DEBUG/INFO to see much more verbose log output

        # Find all avialable plans
        for p in pinn.plans:
            print("Exporting datasets for plan: ", p.plan_info["PlanName"])
            export_plan = p
            # Export primary CT imageset, RTSS, RTDOSE adn RTPLAN for this plan
            # pinn.export_image(export_plan.primary_image, export_path=self.CurPatientOutputFolder)
            # pinn.export_plan(export_plan, self.CurPatientOutputFolder)
            # pinn.export_struct(export_plan, self.CurPatientOutputFolder)
            try:
                pinn.export_dose(export_plan, self.CurPatientOutputFolder)
            except:
                print("Error exporting: ", p.plan_info["PlanName"])

    def CreatePatientFolders(self):
        Str1 = self.PinnArchivePat.split("\\")[-1]
        Str2 = Str1.split(".gz")[0]
        self.CurPatientOutputFolder = self.ExportPath + "\\" + Str2
        os.mkdir(self.CurPatientOutputFolder)
        self.CurPatientPinnFolder = self.PinnPath + "\\" + Str2
        os.mkdir(self.CurPatientPinnFolder)
        # print(self.CurPatientPinnFolder)

        # PatName should be in format LASTName_FirstName

    def SearchForPatient(self, PatName):
        InputFiles = []
        InputFiles = os.listdir(self.PinnArchive)
        # print(InputFiles)
        r = re.compile(PatName, re.IGNORECASE)
        Newlist = list(filter(r.match, InputFiles))
        return Newlist

    def BatchExport(self):
        NumPts = np.size(self.PatNamesList)
        for x in range(0, NumPts, 1):
            try:
                CurPat = self.PatNamesList[x]
                Matches = self.SearchForPatient(CurPat)
                if np.size(Matches) >= 1:
                    print("Found :", CurPat, "in", Matches[0])
                    self.PinnArchivePat = self.PinnPath + "\\" + Matches[0]
                    self.CreatePatientFolders()
                    self.CurPatFilePath = self.PinnArchive + "\\" + Matches[0]
                    self.ExportDCM()
            except:
                print("Error exporting: ", CurPat)

    # Reads patients' names from a excel sheet naems should be in format Lastname_Firstname
    def ReadPatNames(self, FilePath, SheetName, NamesColNum):
        curFile = xlrd.open_workbook(FilePath)
        curSheet = curFile.sheet_by_name(SheetName)
        NamesLst = curSheet.col_values(NamesColNum)
        return NamesLst


# Example usage
WorkingPath = "D:\PinExport"
PinnPath = "D:\PinExport\Pinn"
PinnArchive = "\\\\N12000\PlanningData"  #'D:\PinExport\Input'
ExportFolder = "D:\PinExport\Output"

exp = DCMExporter(WorkingPath, PinnPath, PinnArchive, ExportFolder)
exp.PatNamesList = exp.ReadPatNames(
    "D:/OzCAT/Data/lung_cohort_for_dose_export.xlsx", "Sheet1", 2
)
# print(exp.PatNamesList)
exp.BatchExport()
