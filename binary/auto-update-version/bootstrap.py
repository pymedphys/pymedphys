import sys
import urllib.request
import tempfile
import pathlib
import shutil
import subprocess

PYTHON_ENVIRONMENT_POINTER = "https://bootstrap.pymedphys.com/python-urls/win-amd64"
GET_PYMEDPHYS_URL = "https://bootstrap.pymedphys.com/get-pymedphys.py"


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        python_environment_url_filepath = pathlib.Path(temp_dir).joinpath("python-url")
        get_pymedphys_filepath = pathlib.Path(temp_dir).joinpath("get-pymedphys.py")

        urllib.request.urlretrieve(
            PYTHON_ENVIRONMENT_POINTER, python_environment_url_filepath
        )
        urllib.request.urlretrieve(GET_PYMEDPHYS_URL, get_pymedphys_filepath)

        with open(python_environment_url_filepath) as f:
            python_environment_url = f.readline()

        python_environment_zip = pathlib.Path(temp_dir).joinpath("python.zip")
        urllib.request.urlretrieve(python_environment_url, python_environment_zip)

        python_environment_directory = pathlib.Path(temp_dir).joinpath("python")
        python_exe = python_environment_directory.joinpath("python.exe")

        shutil.unpack_archive(python_environment_zip, python_environment_directory)
        command = [str(python_exe), str(get_pymedphys_filepath)] + sys.argv[1:]

        subprocess.check_call(
            command,
            cwd=python_environment_directory,
        )


if __name__ == "__main__":
    main()
