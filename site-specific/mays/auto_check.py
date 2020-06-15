import os

import tkinter

import pandas as pd

from compare import compare_to_mosaiq
from helpers import get_all_dicom_treatment_info
from pymedphys._mosaiq import connect
from pymedphys._mosaiq.helpers import get_all_treatment_data

root = tkinter.Tk()
root.withdraw()  # use to hide tkinter window

currdir = os.getcwd()

dicomFile = tkinter.filedialog.askopenfilename(
    parent=root, initialdir=currdir, title="Please select a Pinnacle RP file"
)
if len(dicomFile) > 0:
    print("You chose %s" % dicomFile)

dicom_table = get_all_dicom_treatment_info(dicomFile)

mrn = dicom_table.iloc[0]["mrn"]

# host_name = 'prwinvds006.utmsa.local'
with connect.connect("prwinvds006.utmsa.local") as cursor:
    mosaiq_table = get_all_treatment_data(cursor, mrn)

field_version = max(mosaiq_table["field_version"])
mosaiq_table = mosaiq_table[mosaiq_table["field_version"] == field_version]
mosaiq_table = mosaiq_table.reset_index(drop=True)

index = []
for j in dicom_table.iloc[:]["field_label"]:
    for i in range(len(mosaiq_table)):
        if mosaiq_table.iloc[i]["field_label"] == j:
            index.append(i)

remove = []
for i in mosaiq_table.iloc[:].index:
    if i not in index:
        remove.append(i)

mosaiq_table = mosaiq_table.drop(remove)
mosaiq_table = mosaiq_table.sort_values(by=["field_label"])

results = compare_to_mosaiq(dicom_table, mosaiq_table)
results = results.transpose()
