# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.create import dicom_dataset_from_dict


@pytest.mark.pydicom
def test_dicom_from_dict():
    baseline_dataset = pydicom.Dataset()
    baseline_dataset.Manufacturer = "PyMedPhys"
    beam_sequence = pydicom.Dataset()
    beam_sequence.Manufacturer = "PyMedPhys"
    baseline_dataset.BeamSequence = [beam_sequence]

    created_dataset = dicom_dataset_from_dict(
        {"Manufacturer": "PyMedPhys", "BeamSequence": [{"Manufacturer": "PyMedPhys"}]}
    )

    assert created_dataset == baseline_dataset


def _template(is_implicit_VR=None, is_little_endian=None, transfer_syntax_uid=None):
    """Create a template dataset that carries only the given encoding hints."""
    template = pydicom.Dataset()
    if is_implicit_VR is not None:
        template.is_implicit_VR = is_implicit_VR
    if is_little_endian is not None:
        template.is_little_endian = is_little_endian
    if transfer_syntax_uid is not None:
        template.file_meta = pydicom.dataset.FileMetaDataset()
        template.file_meta.TransferSyntaxUID = transfer_syntax_uid
    return template


@pytest.mark.pydicom
@pytest.mark.parametrize(
    ("template", "expected_transfer_syntax_uid"),
    [
        pytest.param(None, pydicom.uid.ImplicitVRLittleEndian, id="no template"),
        pytest.param(
            _template(),
            pydicom.uid.ImplicitVRLittleEndian,
            id="template without encoding hints",
        ),
        pytest.param(
            _template(is_implicit_VR=True, is_little_endian=True),
            pydicom.uid.ImplicitVRLittleEndian,
            id="implicit VR little endian flags",
        ),
        pytest.param(
            _template(is_implicit_VR=False, is_little_endian=True),
            pydicom.uid.ExplicitVRLittleEndian,
            id="explicit VR little endian flags",
        ),
        pytest.param(
            _template(is_implicit_VR=False, is_little_endian=False),
            pydicom.uid.ExplicitVRBigEndian,
            id="explicit VR big endian flags",
        ),
        pytest.param(
            _template(is_implicit_VR=False),
            pydicom.uid.ExplicitVRLittleEndian,
            id="only is_implicit_VR set",
        ),
    ],
)
def test_dicom_from_dict_sets_transfer_syntax(template, expected_transfer_syntax_uid):
    """Datasets built from a dictionary always declare a transfer syntax.

    Implicit VR Little Endian is used unless the template's encoding flags
    say otherwise.
    """
    dataset = dicom_dataset_from_dict(
        {"PatientName": "Test^Patient"}, template_ds=template
    )

    assert dataset.file_meta.TransferSyntaxUID == expected_transfer_syntax_uid


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "transfer_syntax_uid",
    [pydicom.uid.ExplicitVRBigEndian, pydicom.uid.JPEGBaseline8Bit],
)
def test_dicom_from_dict_keeps_template_transfer_syntax(transfer_syntax_uid):
    """A transfer syntax declared by the template is never overridden."""
    template = _template(transfer_syntax_uid=transfer_syntax_uid)

    dataset = dicom_dataset_from_dict(
        {"PatientName": "Test^Patient"}, template_ds=template
    )

    assert dataset.file_meta.TransferSyntaxUID == transfer_syntax_uid


@pytest.mark.pydicom
def test_dicom_from_dict_only_top_level_dataset_gets_file_meta():
    """Sequence items are not files and must not carry file meta information."""
    dataset = dicom_dataset_from_dict(
        {
            "Manufacturer": "PyMedPhys",
            "BeamSequence": [{"BeamNumber": 1}, {"BeamNumber": 2}],
            "ReferencedRTPlanSequence": [
                {"ReferencedBeamSequence": [{"ReferencedBeamNumber": 1}]}
            ],
        }
    )

    assert dataset.file_meta.TransferSyntaxUID == pydicom.uid.ImplicitVRLittleEndian
    assert not hasattr(dataset.BeamSequence[0], "file_meta")
    assert not hasattr(dataset.BeamSequence[1], "file_meta")
    assert not hasattr(
        dataset.ReferencedRTPlanSequence[0].ReferencedBeamSequence[0], "file_meta"
    )


@pytest.mark.pydicom
def test_dicom_from_dict_round_trips_through_pydicom(tmp_path):
    """The declared transfer syntax is sufficient for pydicom to write and read."""
    dataset = dicom_dataset_from_dict({"PatientName": "Test^Patient"})
    filepath = tmp_path / "from_dict.dcm"

    dataset.save_as(filepath)
    reloaded = pydicom.dcmread(filepath, force=True)

    assert reloaded.file_meta.TransferSyntaxUID == pydicom.uid.ImplicitVRLittleEndian
    assert reloaded.PatientName == "Test^Patient"
