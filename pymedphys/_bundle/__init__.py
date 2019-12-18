import functools
import os
import pathlib
import platform
import shutil
import subprocess
import tempfile
import typing
import zipfile

import pymedphys

HERE: pathlib.Path = pathlib.Path(__file__).parent.resolve()

# https://stackoverflow.com/a/39110
# def file_contents_replace(file_path, pattern, subst):
#     fh, abs_path = tempfile.mkstemp()
#     with open(fh, "w") as new_file:
#         with open(file_path) as old_file:
#             for line in old_file:
#                 new_file.write(line.replace(pattern, subst))
#     os.remove(file_path)
#     shutil.move(abs_path, file_path)


if platform.system() == "Windows":
    EXECUTION_PREPEND: typing.List[str] = []
else:
    EXECUTION_PREPEND = ["wine"]


# def call_embedded_python(embedded_python_dir, *args):
#     embedded_python_exe = embedded_python_dir.joinpath("python.exe")
#     to_be_called = [str(item) for item in EXECUTION_PREPEND + [embedded_python_exe] + list(args)]
#     print(to_be_called)
#     subprocess.check_call(to_be_called, cwd=embedded_python_dir)


def main(args):
    cwd = pathlib.Path(os.getcwd())
    build = cwd.joinpath("build")
    python = build.joinpath("python")

    notebooks_dir = cwd.joinpath("notebooks")
    requirements_txt = cwd.joinpath("requirements.txt")

    if not notebooks_dir.exists():
        raise ValueError(
            "Need to have a `notebooks` directory where this command is called"
        )

    if not requirements_txt.exists():
        raise ValueError(
            "Need to have a `requirements.txt` file where this command is called"
        )

    copied_notebooks_dir = build.joinpath("notebooks")

    try:
        shutil.copytree(notebooks_dir, copied_notebooks_dir)
    except FileExistsError:
        pass

    build_files_to_copy = ["package.json", "yarn.lock"]
    build_dirs_to_copy = ["src"]

    for file_to_copy in build_files_to_copy:
        try:
            shutil.copy2(HERE.joinpath(file_to_copy), build.joinpath(file_to_copy))
        except FileExistsError:
            pass

    for dirs_to_copy in build_dirs_to_copy:
        try:
            shutil.copytree(HERE.joinpath(dirs_to_copy), build.joinpath(dirs_to_copy))
        except FileExistsError:
            pass

    if platform.system() != "Windows":
        compat_python = f"Z:{pathlib.PureWindowsPath(python)}"
    else:
        compat_python = python

    path_append_string = f"set PATH={compat_python};{compat_python}\\Scripts;%PATH%"

    if args.clean:
        shutil.rmtree(build, ignore_errors=True)

    miniconda_install_exe = pymedphys.data_path("miniconda.exe")

    install_miniconda = EXECUTION_PREPEND + [
        str(miniconda_install_exe),
        "/InstallationType=JustMe",
        "/RegisterPython=0",
        "/S",
        "/AddToPath=0",
        f"/D={compat_python}",
    ]

    subprocess.check_call(install_miniconda)

    for path in python.joinpath("Library", "bin").glob("*.dll"):
        try:
            shutil.copy2(path, python.joinpath("DLLs"))
        except FileExistsError:
            pass

    subprocess.check_call(
        EXECUTION_PREPEND
        + [
            "cmd",
            "/c",
            f"{path_append_string} && pip install jupyterlab jupyter_server",
        ]
    )

    subprocess.check_call(
        EXECUTION_PREPEND
        + [
            "cmd",
            "/c",
            f"{path_append_string} && conda install -y -c conda-forge nodejs",
        ]
    )

    subprocess.check_call(
        EXECUTION_PREPEND
        + ["cmd", "/c", f"{path_append_string} && pip install -r requirements.txt"]
    )

    fetch_jlab_build_call = " ".join(
        EXECUTION_PREPEND
        + [
            "cmd",
            "/c",
            '"'
            + path_append_string
            + " && set command=python -c 'import\\ pymedphys._jupyterlab.main;\\ pymedphys._jupyterlab.main.get_build()'"
            + '"',
        ]
    )

    print(fetch_jlab_build_call)

    subprocess.check_call(fetch_jlab_build_call, shell=True)

    subprocess.check_call(
        EXECUTION_PREPEND + ["cmd", "/c", f"{path_append_string} && jlpm"], cwd=build
    )

    subprocess.check_call(
        EXECUTION_PREPEND + ["cmd", "/c", f"{path_append_string} && jlpm dist"],
        cwd=build,
    )

    final_exe = cwd.joinpath("JupyterLab Setup.exe")
    try:
        final_exe.unlink()
    except FileNotFoundError:
        pass

    shutil.copy2(build.joinpath("release", "JupyterLab Setup 0.0.0.exe"), final_exe)
