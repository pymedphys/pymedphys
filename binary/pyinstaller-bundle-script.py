import os
import subprocess
import sys
import pathlib
import tarfile
import shutil


def boot_streamlit_app(installation_path):
    subprocess.check_call(
        "python.exe -m pymedphys gui", cwd=installation_path, shell=True
    )


def main():
    cwd = pathlib.Path(os.getcwd())
    installation_path = cwd.joinpath("python-embed")

    if installation_path.exists():
        boot_streamlit_app(installation_path)
    else:
        pyinstaller_temp_dir = pathlib.Path(
            sys._MEIPASS  # pylint: disable = no-member, protected-access
        )
        data_path = pyinstaller_temp_dir.joinpath("data")

        for filename in ["resolve-path.cmd", "pymedphys.bat"]:
            shutil.copy(data_path.joinpath(filename), cwd.joinpath(filename))

        python_xztar = data_path.joinpath("python-embed.tar.xz")

        installation_path.mkdir()

        with tarfile.open(python_xztar) as f:
            f.extractall(installation_path)

        boot_streamlit_app(installation_path)


if __name__ == "__main__":
    main()
