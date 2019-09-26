import os


def remove_file(filepath):
    """Remove a file. Suppress error if the file does not exist."""
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass


def remove_dir(dirpath):
    """Remove a directory. Suppress error if the directory does not
    exist."""
    try:
        os.rmdir(dirpath)
    except FileNotFoundError:
        pass
