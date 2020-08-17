import os


def make_directory(directory_path):
    if not os.path.exists(directory_path):
        os.mkdir(directory_path)
