from datetime import datetime
from collections import namedtuple
import os.path
import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                              'data',
                              'dcmplan')

# TODO: Finalise later
Field = namedtuple('Field', 'label name description JawX JawY')

HAS_MLC = False  # TODO: remove later
HAS_WEDGE = False  # TODO: remove later
HAS_APPLICATOR = False  # TODO: remove later


def generate_rtplan(field_list, save_path):

    # Generate new pydicom Dataset containing main DICOM RT PLan file info
    ds = generate_rtplan_skeleton()

    # Fraction Group Sequence & Fraction Group
    frxn_gp_sequence = Sequence()

    frxn_gp = Dataset()
    frxn_gp.FractionGroupNumber = "1"
    frxn_gp.NumberOfFractionsPlanned = "1"
    frxn_gp.NumberOfBeams = len(field_list)
    frxn_gp.NumberOfBrachyApplicationSetups = "0"

    # Beam Sequence & Referenced Beam Sequence
    beam_sequence = Sequence()
    refd_beam_sequence = Sequence()

    # Generate beams to add to Beam & Refd Beam Sequences
    for field in field_list:

        beam_data, refd_beam_data = generate_rtplan_beam(field)

        beam_sequence.append(beam_data)
        refd_beam_sequence.append(refd_beam_data)

    # Assign Sequences to Dataset
    frxn_gp.ReferencedBeamSequence = refd_beam_sequence
    frxn_gp_sequence.append(frxn_gp)
    ds.FractionGroupSequence = frxn_gp_sequence
    ds.BeamSequence = beam_sequence

    #
    ds.is_implicit_VR = True
    ds.is_little_endian = True
    ds.save_as(save_path, write_like_original=False)


def generate_rtplan_file_meta():
    # File meta info data elements
    file_meta = Dataset()

    # Radiation Therapy Plan Storage
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.5'

    # Recommended here: https://github.com/pydicom/pydicom/issues/316#issuecomment-280547547
    file_meta.MediaStorageSOPInstanceUID = generate_uid(
        prefix='1.2.840.10008.5.1.4.1.1.481.5.')

    # Implicit VR Endian: Default Transfer Syntax for DICOM
    file_meta.TransferSyntaxUID = '1.2.840.10008.1.2'

    # PYDICOM_IMPLEMENTATION_UID (TODO: Obtain one for PyMedPhys here?:
    # http://www.medicalconnections.co.uk/FreeUID.html)
    file_meta.ImplementationClassUID = '1.2.826.0.1.3680043.8.498.1'

    return file_meta


def generate_rtplan_skeleton():

    ds = Dataset()

    # ----- File meta -----
    file_meta = generate_rtplan_file_meta()
    ds.file_meta = file_meta

    # ----- Patient Module -----
    ds.PatientName = 'PyMedPhys'  # Required - can be empty - could fill in?
    ds.PatientID = 'PMP'  # Required - can be empty - could fill in?
    ds.PatientSex = 'O'  # Required - can be empty
    ds.PatientBirthDate = ''  # Required - can be empty TODO: check if RS happy

    ds.StudyInstanceUID = pydicom.uid.generate_uid()
    ds.StudyDate = ''  # Required - can be empty
    ds.StudyTime = ''  # Required - can be empty'
    ds.ReferringPhysicianName = ''  # Required - can be empty'
    ds.StudyID = ''  # Required - can be empty'
    ds.AccessionNumber = ''  # Required - can be empty'

    # ----- RT Series Module -----
    ds.Modality = 'RTPLAN'
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.SeriesNumber = ""  # Required - can be empty'
    ds.OperatorsName = ''  # Required - can be empty'

    # ----- Frame of Reference Module -----
    ds.FrameOfReferenceUID = pydicom.uid.generate_uid()
    ds.PositionReferenceIndicator = ''  # Required - can be empty'

    # ----- General Equipment Module -----
    ds.Manufacturer = ''  # Required - can be empty TODO: Check if RS is happy'
    # ds.ManufacturerModelName = '' # Optional TODO: Check if RS is happy'

    # ----- RT General Plan Module -----
    ds.RTPlanLabel = 'PyMedPhys'  # Set from field definition?
    ds.RTPlanName = 'PyMedPhys'  # Optional, Set from field definition?
    ds.RTPlanDescription = 'PyMedPhys'  # Optional, Set from field definition?
    # Required - can be empty TODO: Check if RS is happy
    ds.RTPlanDate = datetime.now().strftime("%Y%m%d")
    # Required - can be empty TODO: Check if RS is happy
    ds.RTPlanTime = datetime.now().strftime("%H%M%S")
    ds.PlanIntent = 'VERIFICATION'
    ds.RTPlanGeometry = 'TREATMENT_DEVICE'  # Structure Set will probably not exist

    # ----- RT Patient Setup Sequence & Patient Setup -----
    patient_setup_sequence = Sequence()
    ds.PatientSetupSequence = patient_setup_sequence

    patient_setup = Dataset()
    patient_setup.PatientSetupNumber = '1'  # or "ASYMX"
    patient_setup.PatientPosition = "HFS"
    patient_setup_sequence.append(patient_setup)

    # ----- SOP Common Module -----
    ds.SpecificCharacterSet = 'ISO_IR 192'
    ds.InstanceCreationDate = ''  # Optional, could fill in?
    ds.InstanceCreationTime = ''  # Optional, could fill in?'
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.ApprovalStatus = 'UNAPPROVED'

    return ds


def generate_rtplan_beam(field):

    beam = Dataset()
    beam.BeamNumber = 1  # TODO: Required, need to auto-set
    beam.BeamName = "3x3 J"  # TODO: Optional, want to auto-set
    beam.BeamDescription = "3x3 J - generated by PyMedPhys"  # Optional, want to auto-set
    beam.BeamType = "STATIC"
    beam.RadiationType = "PHOTON"  # TODO: Handle electrons

    # Primary Fluence Mode Sequence & Fluence Mode (assume 1)
    primary_fluence_mode_sequence = Sequence()
    beam.PrimaryFluenceModeSequence = primary_fluence_mode_sequence
    primary_fluence_mode = Dataset()
    primary_fluence_mode.FluenceMode = 'STANDARD'
    primary_fluence_mode_sequence.append(primary_fluence_mode)

    # beam.HighDoseTechniqueType = "HDR" # TODO: Check this - might be needed for FFF?

    # Treatment Machine Required for ARIA/Eclipse (Must match existing machine in
    # database). Should we handle this in our TPS Dose Toolbox?
    beam.TreatmentMachineName = "TS2_TBHD"
    beam.PrimaryDosimeterUnit = 'MU'

    # Optional, but probably should set (user?)
    beam.SourceAxisDistance = "1000"

    # ----- Beam Limiting Device Sequence -----
    beam_limiting_device_sequence = Sequence()
    beam.BeamLimitingDeviceSequence = beam_limiting_device_sequence

    # Beam Limiting Device Sequence: Beam Limiting Device 1 ( X Jaws)
    beam_limiting_device1 = Dataset()
    beam_limiting_device1.RTBeamLimitingDeviceType = 'X'  # or "ASYMX"
    beam_limiting_device1.NumberOfLeafJawPairs = "1"
    beam_limiting_device_sequence.append(beam_limiting_device1)

    # Beam Limiting Device Sequence: Beam Limiting Device 2 ( Y Jaws)
    beam_limiting_device2 = Dataset()
    beam_limiting_device2.RTBeamLimitingDeviceType = 'Y'  # or "ASYMY"
    beam_limiting_device2.NumberOfLeafJawPairs = "1"
    beam_limiting_device_sequence.append(beam_limiting_device2)

    if HAS_MLC:
        # Beam Limiting Device Sequence: Beam Limiting Device 3 ( X MLC)
        beam_limiting_device3 = Dataset()
        beam_limiting_device3.RTBeamLimitingDeviceType = 'MLCX'
        beam_limiting_device3.NumberOfLeafJawPairs = "1"
        beam_limiting_device_sequence.append(beam_limiting_device3)

        # Beam Limiting Device Sequence: Beam Limiting Device 4 ( Y MLC)
        beam_limiting_device4 = Dataset()
        beam_limiting_device4.RTBeamLimitingDeviceType = 'MLCY'
        beam_limiting_device4.NumberOfLeafJawPairs = "1"
        beam_limiting_device_sequence.append(beam_limiting_device4)

    # Optional but might be best to set.
    beam.TreatmentDeliveryType = 'TREATMENT'

    # ----- Wedge Sequence TODO: Handle wedges -----

    # Assume no wedge or same wedge throughout beam (0 or 1)
    beam.NumberOfWedges = 0
    if HAS_WEDGE:
        wedge_sequence = Sequence()
        beam.WedgeSequence = wedge_sequence

        # Wedge Sequence: Wedge
        wedge = Dataset()
        wedge.WedgeNumber = 1  # Unique within beam
        wedge.WedgeType = "DYNAMIC"  # or "STANDARD" or "MOTORIZED"
        wedge.WedgeID = ""  # Optional, TODO: check if needed
        wedge.AccessoryCode = ""  # Optional TODO: check if needed
        wedge.WedgeAngle = 60
        wedge.WedgeFactor = ""  # Required but can leave empty
        # Degrees relative to Beam Limiting Device TODO: (always 0 for EDW?)
        wedge.WedgeOrientation = 0
        wedge_sequence.append(wedge)

    beam.NumberOfCompensators = '0'  # ASSUME NO COMPENSATORS
    beam.NumberOfBoli = '0'  # ASSUME NO BOLI

    # ASSUME NO BLOCKS (TODO: check if used for electrons)
    beam.NumberOfBlocks = '0'

    # ----- Applicator Sequence (electrons & SRS) TODO: Handle cones -----
    if HAS_APPLICATOR:
        applicator_sequence = Sequence()
        beam.ApplicatorSequence = applicator_sequence

        # Applicator Sequence: Applicator
        applicator = Dataset()
        applicator.ApplicatorID = "<machine supplied ID>"  # TODO: check cone ID
        applicator.AccessoryCode = ""  # Optional TODO: check if needed
        applicator.ApplicatorType = "ELECTRON_SQUARE"  # many others possible
        applicator.ApplicatorGeometrySequence = [Dataset()]
        # RECTANGLE and CIRCULAR also possible
        applicator.ApplicatorGeometrySequence[0].ApplicatorApertureShape = "SYM_SQUARE"
        # Required for SQUARE and CIRCLE = length of side or diameter
        applicator.ApplicatorGeometrySequence[0].ApplicatorOpening = 10
        # Required if RECTANGLE
        applicator.ApplicatorGeometrySequence[0].ApplicatorOpeningX
        # Required if RECTANGLE
        applicator.ApplicatorGeometrySequence[0].ApplicatorOpeningY
        # Optional TODO: decide whether to set cone desc
        applicator.ApplicatorDescription = ""
        applicator_sequence.append(applicator)

    # ASSUME NO ACCESSORIES? TODO: check if this includes cutouts

    beam.FinalCumulativeMetersetWeight = "1"
    beam.NumberOfControlPoints = "2"

    # ----- Control Point Sequence -----
    cp_sequence = Sequence()
    beam.ControlPointSequence = cp_sequence

    # Control Point Sequence: Control Point 0
    cp0 = Dataset()
    cp0.ControlPointIndex = "0"
    cp0.CumulativeMetersetWeight = "0"
    cp0.NominalBeamEnergy = "6"  # TODO: User supplied
    cp0.DoseRateSet = "600"  # TODO: User supplied

    # Wedge Position Sequence
    if HAS_WEDGE:
        wedge_position_sequence = Sequence()
        cp0.WedgePositionSequence = wedge_position_sequence

        # Wedge Position Sequence: Wedge
        wedge_position = Dataset()
        wedge_position.ReferencedWedgeNumber = 1  # Assume never more than 1 wedge
        wedge_position.WedgePosition = "IN"  # Also "OUT"
        wedge_position_sequence.append(wedge_position)

    # Beam Limiting Device Position Sequence
    beam_limiting_device_position_sequence = Sequence()
    cp0.BeamLimitingDevicePositionSequence = beam_limiting_device_position_sequence

    # Beam Limiting Device Position Sequence: Beam Limiting Device Position 1
    beam_limiting_device_position1 = Dataset()
    # or "ASYMX" TODO: User supplied
    beam_limiting_device_position1.RTBeamLimitingDeviceType = 'X'
    beam_limiting_device_position1.LeafJawPositions = [
        '-15', '15']  # TODO: User supplied
    beam_limiting_device_position_sequence.append(
        beam_limiting_device_position1)

    # Beam Limiting Device Position Sequence: Beam Limiting Device Position 2
    beam_limiting_device_position2 = Dataset()
    # or "ASYMY" TODO: User supplied
    beam_limiting_device_position2.RTBeamLimitingDeviceType = 'Y'
    beam_limiting_device_position2.LeafJawPositions = [
        '-15', '15']  # TODO: User supplied
    beam_limiting_device_position_sequence.append(
        beam_limiting_device_position2)

    if HAS_MLC:  # TODO: Handle MLCs
        # Beam Limiting Device Position Sequence: Beam Limiting Device Position 3
        beam_limiting_device_position3 = Dataset()
        beam_limiting_device_position3.RTBeamLimitingDeviceType = 'MLCX'
        beam_limiting_device_position3.LeafJawPositions = []  # TODO: Tricksy MLC stuff
        beam_limiting_device_position_sequence.append(
            beam_limiting_device_position3)

        # Beam Limiting Device Position Sequence: Beam Limiting Device Position 4
        beam_limiting_device_position4 = Dataset()
        beam_limiting_device_position4.RTBeamLimitingDeviceType = 'MLCY'
        beam_limiting_device_position4.LeafJawPositions = []  # TODO: Tricksy MLC stuff
        beam_limiting_device_position_sequence.append(
            beam_limiting_device_position4)

    cp0.GantryAngle = "0"  # TODO: User supplied, default to 0
    cp0.GantryRotationDirection = 'NONE'
    cp0.BeamLimitingDeviceAngle = "0"  # TODO: User supplied, default to 0
    cp0.BeamLimitingDeviceRotationDirection = 'NONE'
    cp0.PatientSupportAngle = "0"
    cp0.PatientSupportRotationDirection = 'NONE'
    cp0.TableTopEccentricAngle = "0"
    cp0.TableTopEccentricRotationDirection = 'NONE'
    cp0.TableTopPitchAngle = 0.0
    cp0.TableTopPitchRotationDirection = 'NONE'
    cp0.TableTopRollAngle = 0.0
    cp0.TableTopRollRotationDirection = 'NONE'
    cp0.TableTopVerticalPosition = ''  # Required but can leave empty
    cp0.TableTopLongitudinalPosition = ''  # Required but can leave empty
    cp0.TableTopLateralPosition = ''  # Required but can leave empty
    # Required but can leave empty TODO: not according to RS!
    cp0.IsocenterPosition = ['0', '0', '0']
    cp0.SourceToSurfaceDistance = 900  # TODO: User supplied

    cp_sequence.append(cp0)

    # Control Point Sequence: Control Point 1
    cp1 = Dataset()
    cp1.ControlPointIndex = "1"
    cp1.CumulativeMetersetWeight = "1"

    cp_sequence.append(cp1)

    # Referenced Beam Sequence: Referenced Beam 1
    refd_beam = Dataset()
    refd_beam.ReferencedBeamNumber = "1"
    refd_beam.BeamMeterset = "100"  # TODO: Set upon plan setup

    return beam, refd_beam


if __name__ == "__main__":

    fields = [Field('test1', 'a', 'b', 'c', 'd')]  # values unused for now
    save_path = os.path.join(DATA_DIRECTORY, 'RP.test.dcm')
    generate_rtplan(fields, save_path)
