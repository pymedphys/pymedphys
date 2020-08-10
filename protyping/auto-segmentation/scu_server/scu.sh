#!/bin/bash

DATA_PATH=/media/matthew/secondary/dicom_prostate_images
python -m pynetdicom storescu 127.0.0.1 11112 $DATA_PATH -v -cx
