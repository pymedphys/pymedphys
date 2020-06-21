# -*- coding: utf-8 -*-
"""
Created on Fri Mar 13 14:16:40 2020

@author: D Buckle

*******************************************************************************
Collection of classes to perform calculations of plan complexity metrics using
an input of mlcDataEval as produced by 'PlanOperations.py'

Metrics
    Base class for all the other metric classes to be derived from. The same
    operations will probably be needed for all metrics and this will save on
    repeating code.

ModulationComplexity
    Has methods to calculate the Leaf Sequence Variability and Aperture Area
    Variability as defined in the publication ??????? This calculation assumes
    the VMAT definition i.e. the average of two control points to take into
    account the moving jaws/leaves in between CP. This should still work for
    step/shoot IMRT as these have two CP/segment where the jaw/MLC positions
    are identical and the MU on the 1st one is 0.


BeamComplexity - Has methods which calculate:
    - aperture area (AA)
    - aperture perimeter (AP)
    - aperture irregularity (AI)
    - beam area (BA)
    - beam irregularity (BI)
    - beam modulation (BM)
*******************************************************************************
"""
import math
from math import pi

from pymedphys._imports import numpy as np

from . import data as MLCdata
from .operations import getBeamType, getMLCdata


class jawPositionError(ValueError):
    pass


class Metrics:
    def __init__(self, **kwargs):
        # initialiser function to define the default values of 0 for all parameters
        # and to pre-calculate the relevant parameters for the calculation
        self.ds = kwargs.get("ds")
        result = getMLCdata(self.ds)
        self.mlcData = result[0]
        self.jawData = result[1]
        self.segWeightData = result[2]
        self.maxSep = result[3]
        self.maxSepSum = result[4]
        self.maxPositions = result[5]
        self.maxJawPos = result[6]
        self.leafThicknesses = MLCdata.TrueBeamThick
        self.leafIndices = MLCdata.TrueBeam

        #        self.demographics = getDemographics()

        if self.mlcData is not None:
            self.beamNames = list(self.mlcData.keys())


#            self.controlPoints = len(self.mlcData.get(self.beamNames[0]))
#            self.leafIndices = self.mlcData.get(self.beamNames[0])[0]


def _calcLSV(left, right, y1, y2, indices):
    leftMax = abs(np.nanmax(left) - np.nanmin(left))
    rightMax = abs(np.nanmax(right) - np.nanmin(right))
    lsvLeft = 0
    lsvRight = 0
    leafDiffSum = 0
    leaves = 0
    assert len(left) == len(right)
    for l in range(len(left) - 1):  # looping through each leaf
        if indices[l] > float(y1) or indices[l] < float(y2):
            continue
        leafDiff = abs(left[l] - left[l + 1])
        leafDiffSum_ = leftMax - leafDiff
        leafDiffSum = leafDiffSum + leafDiffSum_
        leaves = leaves + 1
    try:  # handling for divide by 0 errors i.e. this factor needs to = 1 if no modulation
        lsvLeft = leafDiffSum / (leaves * leftMax)
    except ZeroDivisionError:
        lsvLeft = 1

    leafDiffSum = 0
    leaves = 0
    for l in range(len(right) - 1):
        leafDiff = abs(right[l] - right[l + 1])
        if math.isnan(leafDiff):
            continue
        leafDiffSum_ = rightMax - leafDiff
        leafDiffSum = leafDiffSum + leafDiffSum_
        leaves = leaves + 1

    try:
        lsvRight = leafDiffSum / (leaves * rightMax)
    except ZeroDivisionError:
        lsvRight = 1

    lsvSegment = lsvLeft * lsvRight
    return lsvSegment


class ModulationComplexity(Metrics):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calcLSV = _calcLSV
        print("Beginning Modulation Complexity Score calculation....")

    def __str__(self):
        return str("str function to be coded later")

    def calcAAV(self, left, right, beamName, y1, y2, indices):
        leafSepSum = 0
        assert len(left) == len(right)
        for l in range(0, 60):  # looping round all the leaves
            if indices[l] > float(y1) or indices[l] < float(y2):
                continue
            leafSep = abs(right[l] - left[l])
            if leafSep > 0.5:
                leafSepSum = leafSepSum + leafSep
        try:
            m = self.maxSepSum.get(beamName)
            aavSegment = leafSepSum / m
        except (ZeroDivisionError, RuntimeWarning):
            aavSegment = 1

        return aavSegment

    def calcMCSs(self, b):
        mcsBeam = 0
        controlPoints = len(self.mlcData.get(b))
        for c in range(0, controlPoints - 1):
            indices = self.mlcData.get(b)[c][:, 0]
            A = self.mlcData.get(b)[c][:, 1]
            B = self.mlcData.get(b)[c][:, 2]
            y1 = self.jawData.get(b)[c][3, 1]
            y2 = self.jawData.get(b)[c][2, 1]
            lsvSeg = self.calcLSV(A, B, y1, y2, indices)
            aavSeg = self.calcAAV(A, B, b, y1, y2, indices)

            w = self.segWeightData.get(b)[c]

            mcsSeg = lsvSeg * aavSeg * w
            mcsBeam = mcsBeam + mcsSeg
        return mcsBeam

    #            print(f"MCS for beam {b}: ",round(mcsBeam,3))

    def calcMCSv(self, b):
        controlPoints = len(self.mlcData.get(b))
        mcsBeam = 0
        for c in range(0, controlPoints - 1):
            indices = self.mlcData.get(b)[c][:, 0]
            A = self.mlcData.get(b)[c][:, 1]
            B = self.mlcData.get(b)[c][:, 2]
            y1 = self.jawData.get(b)[c][3, 1]
            y2 = self.jawData.get(b)[c][2, 1]
            lsvSeg = self.calcLSV(A, B, y1, y2, indices)
            aavSeg = self.calcAAV(A, B, b, y1, y2, indices)

            indices = self.mlcData.get(b)[c + 1][:, 0]
            A = self.mlcData.get(b)[c + 1][:, 1]
            B = self.mlcData.get(b)[c + 1][:, 2]
            lsvSeg_ = self.calcLSV(A, B, y1, y2, indices)
            aavSeg_ = self.calcAAV(A, B, b, y1, y2, indices)

            l = (lsvSeg + lsvSeg_) / 2
            a = (aavSeg + aavSeg_) / 2
            w = self.segWeightData.get(b)[c]

            mcsSeg = l * a * w
            mcsBeam = mcsBeam + mcsSeg
        return mcsBeam

    def calcMCS(self):
        #        self.lsvPlan = {}
        #        self.aavPlan = {}
        beamNumber = 0
        mcsBeam = {}
        beamTypes = {}
        for b in self.beamNames:
            beamType = getBeamType(self.ds, beamNumber)
            beamNumber = beamNumber + 1
            #            print("Printing the beam type: ",beamType)
            if beamType == "STATIC":
                mcs = self.calcMCSs(b)
            if beamType == "DYNAMIC":
                mcs = self.calcMCSv(b)
            mcsBeam[b] = mcs
            beamTypes[b] = beamType
        print("Done.")
        return (mcsBeam, beamTypes)


#            print(f"MCS for beam {b}: ",round(mcsBeam,3))


def _calcApertureArea(indices, A, B, y1, y2):
    AASeg = 0
    for i in range(0, 60):
        if indices[i] > float(y1) or indices[i] < float(y2):
            continue
        if abs(A[i] - B[i]) < 1:
            continue
        AA_leafPair = abs(A[i] - B[i]) * MLCdata.TrueBeamThick[i]
        AA_leafPair = AA_leafPair / 100  # converting to cm
        AASeg = AASeg + AA_leafPair
    return AASeg


def _calcAperturePerim(indices, A, B, y1, y2):
    edgesSeg = 0
    endsSeg = 0
    for i in range(0, 60):
        # ignore leaf paris which are behind the jaws
        if indices[i] > float(y1) or indices[i] < float(y2):
            continue

        # check if leaf pair is open to get the contribution of the leaf
        # ends to the perimeter as twice the leaf thickness which is looked
        # up from the MLCData.py file
        if abs(A[i] - B[i]) > 5:
            endsSeg = endsSeg + 2 * MLCdata.TrueBeamThick[i]

        # work out the contribution of the leaf edges to the perimeter
        # Calculated by looking at the leaves above and below and checking
        # whether any part of either edge is contributing to the shape of the
        # segment. For the first and last leaf pairs there is no leaf above/below
        # so these need to be ignored.
        if i == 0:  # no leaf above so only checking one side
            if A[i + 1] < A[i]:
                edgesSeg = edgesSeg + abs(A[i + 1] - A[i])
            if B[i + 1] > B[i]:
                edgesSeg = edgesSeg + abs(B[i + 1] - B[i])
            continue
        if i == 60:  # no leaf below so only checking one side
            if A[i - 1] < A[i]:
                edgesSeg = edgesSeg + abs(A[i - 1] - A[i])
            if B[i - 1] > B[i]:
                edgesSeg = edgesSeg + abs(B[i - 1] - B[i])
            continue

        # checking both sides of each lead
        if A[i + 1] < A[i]:
            edgesSeg = edgesSeg + abs(A[i + 1] - A[i])
        if A[i - 1] > A[i]:
            edgesSeg = edgesSeg + abs(A[i - 1] - A[i])
        if B[i + 1] < B[i]:
            edgesSeg = edgesSeg + abs(B[i + 1] - B[i])
        if B[i + 1] > B[i]:
            edgesSeg = edgesSeg + abs(B[i + 1] - B[i])

    APSeg = (edgesSeg + endsSeg) / 10  # divide by 10 to convert to cm
    return APSeg


class BeamComplexity(Metrics):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calcApertureArea = _calcApertureArea
        self.calcAperturePerim = _calcAperturePerim

        print("Beginning Beam Complexity calculation....")

    #        if self.jawData == None:
    #            print("Jaw positions not supplied. You must supply jaw position data.")
    #            raise jawPositionError(self.jawData)

    def __str__(self):
        return str("str function to be coded later")

    def calcApertureIrregularity(self, indices, A, B, y1, y2):
        AASeg = self.calcApertureArea(indices, A, B, y1, y2)
        APSeg = self.calcAperturePerim(indices, A, B, y1, y2)
        AISeg = (APSeg * APSeg) / (4 * pi * AASeg)
        return AASeg, APSeg, AISeg

    def calcBeamComplexity(self):
        beamArea = {}
        beamIrregularity = {}
        beamModulation = {}
        for b in self.beamNames:
            AABeam = 0
            AIBeam = 0
            beamMod = 0
            aMax = self.maxPositions.get(b)[:, 0]
            bMax = self.maxPositions.get(b)[:, 1]

            indices = self.mlcData.get(b)[0][:, 0]
            unionArea = self.calcApertureArea(indices, aMax, bMax, 200, -200)
            controlPoints = len(self.mlcData.get(b))
            for c in range(0, controlPoints):
                indices = self.mlcData.get(b)[c][:, 0]
                A = self.mlcData.get(b)[c][:, 1]
                B = self.mlcData.get(b)[c][:, 2]
                y1 = self.jawData.get(b)[c][3, 1]
                y2 = self.jawData.get(b)[c][2, 1]
                w = self.segWeightData.get(b)[c]

                AASeg = self.calcApertureArea(indices, A, B, y1, y2)
                AABeam = AABeam + (AASeg * w)

                AISeg = self.calcApertureIrregularity(indices, A, B, y1, y2)[2]
                AIBeam = AIBeam + (AISeg * w)

                beamMod = 1 - (AABeam / unionArea)

            beamArea[b] = AABeam
            beamIrregularity[b] = AIBeam
            beamModulation[b] = beamMod

        print("Done.")
        return (beamArea, beamIrregularity, beamModulation)
