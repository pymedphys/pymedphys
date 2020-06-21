# -*- coding: utf-8 --
"""
Created on Thu Mar  5 16:43:11 2020

@author: D. Buckle
*******************************************************************************

Load a plan and calculate the plan complexity factors.

Only works with IMRT/VMAT plans at the moment. This can cause problems when trying
to open plans with a mixture of IMRT/non-IMRT fields as these cannot be opened
at the moment.

Input needs to be either a VMAT DICOM RT plan file or an IMRT.

This has been written and works when using Pinnacle plans and has not been tested
on plans from any other TPS

*******************************************************************************
"""
from pathlib import Path

from pymedphys._imports import pydicom
from pymedphys._imports import tkinter as tk

from .classes import BeamComplexity, ModulationComplexity


def main():
    root = tk.Tk()
    root.withdraw()

    path = tk.filedialog.askopenfilename()
    path = Path(path)
    path = str(path)
    ds = pydicom.dcmread(path)

    mcs = ModulationComplexity(ds=ds)
    mcs_all = mcs.calcMCS()

    bc = BeamComplexity(ds=ds)
    bc_all = bc.calcBeamComplexity()

    beamNames = mcs_all[0].keys()

    n = 0
    for b in beamNames:
        beamType = mcs_all[1].get(b)
        mcs = round(mcs_all[0].get(b), 3)
        ba = round(bc_all[0].get(b), 1)
        bi = round(bc_all[1].get(b), 2)
        bm = round(bc_all[2].get(b), 3)
        n = n + 1

        print(
            f"""
    Printing beam complexity report:
        Beam name: {b}
        Beam type: {beamType}

        Modulation Complexity Score: {mcs}
        Beam Area: {ba}
        Beam irregularity: {bi}
        Beam modulation: {bm}"""
        )


if __name__ == "__main__":
    main()
