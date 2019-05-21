from pymedphys_dicom.dicom import DicomBase

dicom = DicomBase.from_dict({
    'Manufacturer': 'PyMedPhys',
    'PatientName': 'Python^Monte'
})

dicom.anonymise(inplace=True)

print(dicom.dataset)
