# -*- coding: utf-8 -*-
"""
Created on Fri Mar 13 14:29:35 2020

@author: D. Buckle
*******************************************************************************
Some operations to load and prepare plan data for calculation of plan metrics

openPlan - Opens a DICOM plan file and returns the whole data as 'ds'

getBeamType - extract the beam types from the plan as some metrics are calculated
    differently depending on whether they are VMAT.

getDeomgraphics - Extract the demographics information using the dicompyler-core
    dicomparser module

getmlcdata - Reads in the DICOM data from openPlan and extracts the MLC and
    jaws data per beam and per control point into individual dictionaries for
    easier visualisation and to make them easier to work with.
    Returns a tuple containing the MLC data and the jaw data stored in
    dictionaries. Each beam itself is a dictionary of numpy arrays for each CP

*******************************************************************************

"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import data as MLCdata

# from dicompylercore import dicomparser


def openPlan(plan):
    ds = pydicom.dcmread(plan)
    return ds


def getBeamType(ds, b):
    beamType = ds.BeamSequence[b].BeamType
    return beamType


# def getDemographics(file):
#    demographics = dicomparser.DicomParser.GetDemographics(file)
#    print(demographics)


def getMLCdata(ds):
    leafIndices = MLCdata.TrueBeam  # import leaf index values from MLC data file
    beamSequence = ds.BeamSequence
    beamNames = []  # getting the beam names
    mlcData = {}
    jawData = {}
    segWeightData = {}
    maxPositions = {}
    maxJawPos = {}
    maxSep = {}
    maxSepSum = {}
    for b in beamSequence:  # looping through the beams
        name = b.BeamName
        beamNames.append(name)
        cps = b.ControlPointSequence
        cp = len(cps)

        leafPositions = {}  # empty dictionary to place leaf positions into
        jawPositions = {}
        segWeight = {}
        maxA = np.zeros((60))
        maxB = np.zeros((60))
        maxJaws = np.zeros((4))
        maxPos = []
        for i in range(0, cp - 1):  # looping through control points
            if len(cps[i].BeamLimitingDevicePositionSequence) == 3:  # assymm jaws
                xJaws_ = cps[i].BeamLimitingDevicePositionSequence[0].LeafJawPositions
                yJaws_ = cps[i].BeamLimitingDevicePositionSequence[1].LeafJawPositions
                mlcPos = cps[i].BeamLimitingDevicePositionSequence[2].LeafJawPositions
            elif len(cps[i].BeamLimitingDevicePositionSequence) == 2:  # symmetric jaws
                xJaws_ = cps[i].BeamLimitingDevicePositionSequence[0].LeafJawPositions
                yJaws_ = cps[i].BeamLimitingDevicePositionSequence[0].LeafJawPositions
                mlcPos = cps[i].BeamLimitingDevicePositionSequence[1].LeafJawPositions
            leafPosA = list(map(float, mlcPos[0:60]))
            leafPosB = list(map(float, mlcPos[60:120]))
            leafPositions[i] = np.column_stack((leafIndices, leafPosA, leafPosB))
            xJaws = list(map(float, xJaws_))
            yJaws = list(map(float, yJaws_))
            positions = list((xJaws[0], xJaws[1], yJaws[0], yJaws[1]))
            indices = list(("x1", "x2", "y1", "y2"))
            jawPositions[i] = np.column_stack((indices, positions))

            if i == 0:
                segWeight[i] = float(cps[i + 1].CumulativeMetersetWeight)
            else:
                segWeight[i] = float(
                    cps[i + 1].CumulativeMetersetWeight
                    - cps[i].CumulativeMetersetWeight
                )

            for l in range(0, 60):
                if leafPosA[l] < maxA[l]:
                    maxA[l] = float(leafPosA[l])
                if leafPosB[l] > maxB[l]:
                    maxB[l] = float(leafPosB[l])

            for l in range(0, 4):
                if abs(positions[l]) > abs(maxJaws[l]):
                    maxJaws[l] = float(positions[l])

        string = str(f"{name}")
        maxPos = np.column_stack((maxA, maxB))
        mlcData[string] = leafPositions
        jawData[string] = jawPositions
        segWeightData[string] = segWeight
        maxPositions[string] = maxPos
        maxJawPos[string] = maxJaws

        _ = list(abs(np.array(maxA) - np.array(maxB)))
        maxSepSum[string] = np.nansum(_)
        maxSep[string] = _

    return (mlcData, jawData, segWeightData, maxSep, maxSepSum, maxPositions, maxJawPos)
