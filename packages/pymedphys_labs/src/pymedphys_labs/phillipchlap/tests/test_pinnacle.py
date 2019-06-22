import pytest
import pydicom
import numpy
import os
import shutil
import tempfile

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "data")

pinn_archive = os.path.join(DATA_DIRECTORY, 'pinn/test_pinnacle_16.0.tar.gz')
pinn_path = 'Institution_2812/Mount_0/Patient_16218'
gt_dose_path = os.path.join(
    DATA_DIRECTORY, 'dcm/1.3.46.670589.13.997910418.20181018190715.183309.dcm')
working_path = tempfile.mkdtemp()
archive_path = os.path.join(working_path, 'pinn')
export_path = os.path.join(working_path, 'output')


@pytest.fixture(scope='session')
def archive():
    import tarfile

    shutil.rmtree(working_path, ignore_errors=True)
    os.makedirs(working_path)

    t = tarfile.open(pinn_archive)

    for m in t.getmembers():
        if not ':' in m.name:
            t.extract(m, path=archive_path)
    return os.path.join(archive_path, pinn_path)


@pytest.fixture
def pinn(archive):
    from pymedphys_labs.phillipchlap import Pinnacle
    return Pinnacle(archive, None)


def test_pinnacle(pinn):
    plans = pinn.get_plans()
    assert len(plans) == 3


def test_dose(pinn):

    os.makedirs(export_path)

    export_plan = None

    for p in pinn.get_plans():
        if p.plan_info['PlanName'] == 'Plan_2':
            export_plan = p
            break

    assert export_plan != None

    pinn.export_dose(export_plan, export_path)

    # Get the exported RTDOSE file
    for f in os.listdir(export_path):
        if f.startswith('RD'):
            exported_dose = pydicom.read_file(os.path.join(export_path, f))
            assert exported_dose.Modality == 'RTDOSE'
            break

    # Get the ground truth RTDOSE file
    pinn_dose = pydicom.read_file(gt_dose_path)
    assert pinn_dose.Modality == 'RTDOSE'

    # Get the dose volumes
    exported_vol = exported_dose.pixel_array.astype(numpy.int16)
    pinn_vol = pinn_dose.pixel_array.astype(numpy.int16)

    # Ensure dose volumes are the same size
    assert exported_vol.shape == pinn_vol.shape

    # Apply dose grid scaling
    exported_vol = exported_vol * exported_dose.DoseGridScaling
    pinn_vol = pinn_vol * pinn_dose.DoseGridScaling

    # Make sure the maximum values are in the same locations
    assert exported_vol.argmax() == pinn_vol.argmax()

    # Get the absolute difference between these volumes
    diff = exported_vol - pinn_vol
    abs_diff = numpy.absolute(diff)

    # Make sure the absolute difference is (close to) zero
    for val in numpy.nditer(abs_diff):
        assert val < 0.01
