import os
from glob import glob

filelist = glob("./original/*.jpg")
new_filenames = [f"./new/{os.path.basename(filepath)}" for filepath in filelist]

for old, new in zip(filelist, new_filenames):
    os.system(f"~/bin/wavelet/jpeg {old} temp.jpg")
    os.system(f"convert temp.jpg {new}")
