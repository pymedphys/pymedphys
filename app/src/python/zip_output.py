import os
from glob import glob
from zipfile import ZipFile


with ZipFile('output.zip', 'w') as myzip:
    files = glob('output/*')
    for filename in files:
        myzip.write(filename, os.path.basename(filename))
