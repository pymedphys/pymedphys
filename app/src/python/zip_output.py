import os
import zipfile


def zipdir(path, zipfile_handle):
    for root, dirs, files in os.walk(path):
        for filename in files:
            zipfile_handle.write(os.path.join(root, filename))


with zipfile.ZipFile('output.zip', 'w',
                     zipfile.ZIP_DEFLATED) as zipfile_handle:
    zipdir('output', zipfile_handle)
