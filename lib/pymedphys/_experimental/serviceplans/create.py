# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import copy
import pathlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

HERE = pathlib.Path(__file__).parent
TEMPLATE_DIR = HERE.joinpath("templates")


def load_templates():
    vmat_example = pydicom.read_file(
        str(TEMPLATE_DIR.joinpath("vmat_example.dcm")), force=True
    )

    fff_example = pydicom.read_file(
        str(TEMPLATE_DIR.joinpath("FFF_example.dcm")), force=True
    )

    collimation = pydicom.read_file(
        str(TEMPLATE_DIR.joinpath("24mm_x_20mm_rectangle.dcm")), force=True
    )

    return vmat_example, fff_example, collimation


def from_bipolar(angles):
    ref = angles < 0
    angles[ref] = angles[ref] + 360

    return angles


def main(energy, dose_rate, prepend=""):
    total_mu = "{:.6f}".format(float(dose_rate))
    dose_rate = str(int(dose_rate))
    nominal_energy = str(float("".join(i for i in energy if i in "0123456789.")))
    fff = "fff" in str(energy).lower()

    vmat_example, fff_example, collimation = load_templates()

    fff_fluence_mode = fff_example.BeamSequence[0].PrimaryFluenceModeSequence
    beam_collimation = (
        collimation.BeamSequence[0]
        .ControlPointSequence[0]
        .BeamLimitingDevicePositionSequence
    )

    gantry_step_size = 15.0

    gantry_beam_1 = from_bipolar(np.arange(-180, 181, gantry_step_size))
    gantry_beam_1[0] = 180.1
    gantry_beam_1[-1] = 179.9

    coll_beam_1 = from_bipolar(np.arange(-180, 1, gantry_step_size / 2))
    coll_beam_1[0] = 180.1

    gantry_beam_2 = from_bipolar(np.arange(180, -181, -gantry_step_size))
    gantry_beam_2[-1] = 180.1
    gantry_beam_2[0] = 179.9

    coll_beam_2 = from_bipolar(np.arange(180, -1, -gantry_step_size / 2))
    coll_beam_2[0] = 179.9

    gant_directions = ["CW", "CC"]
    coll_directions = ["CC", "CW"]

    control_point_sequence_beam1 = create_control_point_sequence(
        vmat_example.BeamSequence[0],
        beam_collimation,
        coll_directions[0],
        dose_rate,
        gantry_beam_1,
        coll_beam_1,
        nominal_energy,
    )
    control_point_sequence_beam2 = create_control_point_sequence(
        vmat_example.BeamSequence[1],
        beam_collimation,
        coll_directions[1],
        dose_rate,
        gantry_beam_2,
        coll_beam_2,
        nominal_energy,
    )

    plan = copy.deepcopy(vmat_example)
    plan.BeamSequence[0].ControlPointSequence = control_point_sequence_beam1
    plan.BeamSequence[1].ControlPointSequence = control_point_sequence_beam2

    num_cps = len(gantry_beam_1)

    for beam_sequence, direction in zip(plan.BeamSequence, gant_directions):
        beam_sequence.NumberOfControlPoints = str(num_cps)
        beam_sequence.BeamName = (
            f"WLutzArc-{prepend}-{energy}-{dose_rate.zfill(4)}-{direction}"
        )

    if fff:
        for beam_sequence in plan.BeamSequence:
            beam_sequence.PrimaryFluenceModeSequence = fff_fluence_mode

    plan.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset = total_mu
    plan.FractionGroupSequence[0].ReferencedBeamSequence[1].BeamMeterset = total_mu

    plan.RTPlanLabel = f"{prepend}-{energy}-{dose_rate}"
    plan.RTPlanName = plan.RTPlanLabel
    plan.PatientID = "WLutzArc"

    return plan


def create_control_point_sequence(
    beam, beam_collimation, rotation_direction, dose_rate, gantry, coll, nominal_energy
):
    num_cps = len(gantry)
    meterset_weight = np.linspace(0, 1, num_cps)

    cp_bounds = bounding_control_points(
        beam, beam_collimation, rotation_direction, dose_rate
    )

    control_point_sequence = pydicom.Sequence([copy.deepcopy(cp_bounds["first"])])

    control_point_sequence[0].GantryAngle = str(gantry[0])
    control_point_sequence[0].BeamLimitingDeviceAngle = str(coll[0])
    control_point_sequence[0].NominalBeamEnergy = nominal_energy

    for i in range(1, num_cps - 1):
        cp = copy.deepcopy(cp_bounds["mid"])

        cp.GantryAngle = str(gantry[i])
        cp.BeamLimitingDeviceAngle = str(coll[i])
        cp.CumulativeMetersetWeight = str(round(meterset_weight[i], 6))
        cp.ControlPointIndex = str(i)

        control_point_sequence.append(cp)

    cp = copy.deepcopy(cp_bounds["last"])
    cp.GantryAngle = str(gantry[-1])
    cp.BeamLimitingDeviceAngle = str(coll[-1])
    cp.ControlPointIndex = str(num_cps - 1)

    control_point_sequence.append(cp)

    return control_point_sequence


def bounding_control_points(beam, beam_collimation, rotation_direction, dose_rate):
    cps = {}

    cps["first"] = beam.ControlPointSequence[0]
    cps["mid"] = beam.ControlPointSequence[1]
    cps["last"] = beam.ControlPointSequence[-1]

    for cp in cps.values():
        cp.BeamLimitingDevicePositionSequence = beam_collimation
        cp.DoseRateSet = dose_rate

    for key in ["first", "mid"]:
        cps[key].BeamLimitingDeviceRotationDirection = rotation_direction

    return cps
