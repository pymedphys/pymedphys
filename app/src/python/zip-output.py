# pylint: disable=import-error

import os
from glob import glob
from zipfile import ZipFile


files = glob("output/*")

with ZipFile("output.zip", "w") as myzip:
    for filename in files:
        myzip.write(filename, os.path.basename(filename))
