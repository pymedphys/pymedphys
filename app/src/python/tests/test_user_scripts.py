import os
import runpy
import zipfile

import pytest

HERE = os.path.abspath(__file__)
USER_SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "..", "user-scripts"))
DEMO_ZIP = os.path.abspath(
    os.path.join(HERE, "..", "..", "..", "data", "demo-files.zip")
)


@pytest.fixture(scope="session")
def temp_workingdir(tmpdir_factory):
    workingdir = tmpdir_factory.mktemp("workingdir")

    input_dir = os.path.join(workingdir, "input")
    ourput_dir = os.path.join(workingdir, "output")

    os.mkdir(input_dir)
    os.mkdir(ourput_dir)

    with zipfile.ZipFile(DEMO_ZIP) as a_zip:
        a_zip.extractall(input_dir)

    return workingdir


@pytest.mark.slow
def test_gamma_calc(temp_workingdir):
    os.chdir(temp_workingdir)
    scriptpath = os.path.join(USER_SCRIPTS, "gamma.py")

    runpy.run_path(scriptpath)


@pytest.mark.slow
def test_mu_density_diff(temp_workingdir):
    os.chdir(temp_workingdir)
    scriptpath = os.path.join(USER_SCRIPTS, "mu-density-diff.py")

    runpy.run_path(scriptpath)
