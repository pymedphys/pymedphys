# -*- coding: utf-8 -*-
"""
Created on Sun Jun  7 13:53:34 2020

@author: D Buckle

File containign the information about each metric which can be printed.

This gives detail on where these have been described in the literature as well
as some detail on how they are calculated

"""
mcsInfo = """
Modulation Complexity Score (MCS):
For further information refer to the references provided.

Description:
    Metric which describes the movement of leaves relative to one another in each
    leaf bank and each control point in an IMRT/VMAT plan. This was originally
    described by McNiven at al and the original definition was applicable to
    step and shoot IMRT fields where leaves do not move during a control point.
    The definition was then extended by Masi et al to take account of the more
    common situation of each 'segment' having a starting and ending control point.
    MCS values range from 0 to 1 with 1 being an open field and 0 being infinitely
    modulated.

Definition:
    MCS is equal to the product of two further quantities: Apperture Area Variation
    (AAV) and Leaf Sequence Variation (LSV).

    AAV = Leaf gap for leaf pair in cp/maximum leaf gap for leaf pair in beam
    (summed over all leaf pairs)

    LSV = (PosMax) - (PosN - PosN+1)) / N x PosMax
    where:
        N = current leaf pair
        PosMax = maximum distance between positions for a leaf bank
        i.e. PosMax = max(Pos) - min(Pos)
        PosN = position of leaf in leaf pair N
    LSV is summed over all leaf pairs to give LSVsegment for each bank seperately
    i.e. LSVsegment  = LSVsegment_RightBank x LSVsegment_LeftBank

    These are calculated for each control point and summed over all control points.

    MCS = Sum over all segments[LSVsegment x AAVsegment x MU weighting for segment]

References:
    1. McNiven L et al - A new metric for assessing IMRT modulation complexity
    and plan deliverability Med Phys 37(2) Feb 2010

    2. Masi L et al - Impact of plan parameters on the dosimetric accuracy of
    volumetric modulated arc therapy Med Phys 40(7) July 2013

    """

bcInfo = """
Description:
    Metric which describes the beam complexity in terms of the apperture areas
    and the apperture shapes.

Definition:
    There are several metrics which make up this group which can be calculated
    seperately and considered individually or together

References:
    1. Du W et al - Quantification of beam complexity in intensity-modulated
    radiation therapy treatment plans Med Phys 41(2) Feb 2014
   """
