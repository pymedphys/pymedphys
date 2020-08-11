from pydicom import dcmread
from pynetdicom import AE, debug_logger
from pynetdicom.sop_class import CTImageStorage
import glob

debug_logger()

PORT=11112
DATASET='C:/Users/Public/Documents/vacunet/test_data/160563_images/with_transfer_syntax'
#DATASET='C:/Users/Public/Documents/vacunet/test_data/160563_images/with_transfer_syntax/1.2.840.113704.1.111.2564.1556080845.11529.dcm'


dicom_paths = glob.glob(DATASET + "/*.dcm")

dicom_files = [dcmread(file) for file in dicom_paths]

# Initialise the Application Entity
ae = AE()

# Add a requested presentation context
ae.add_requested_context(CTImageStorage)

# Read in our DICOM CT dataset
#ds = dcmread(DATASET, force=True)

# Associate with peer AE at IP 127.0.0.1 and port 11112
assoc = ae.associate('127.0.0.1', PORT)
if assoc.is_established:
    # Use the C-STORE service to send the dataset
    # returns the response status as a pydicom Dataset
    for ds in dicom_files:
    	status = assoc.send_c_store(ds)

    	# Check the status of the storage request
    	if status:
        	# If the storage request succeeded this will be 0x0000
        	print('C-STORE request status: 0x{0:04x}'.format(status.Status))
    	else:
        	print('Connection timed out, was aborted or received invalid response')

    # Release the association
    assoc.release()
else:
    print('Association rejected, aborted or never connected')
