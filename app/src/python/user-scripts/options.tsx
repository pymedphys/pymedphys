export interface IUserScripts {
    name: string;
    description: string;
    code: string;
}

import trf2csv from './trf2csv.py';
import muDensityDiff from './mu-density-diff.py';
import trf2dcm from './trf2dcm.py';

export const USER_SCRIPTS: IUserScripts[] = [
    {
        name: "trf2csv", code: trf2csv,
        description: "Convert files that end in `.trf` into header and table `.csv` files."
    },
    {
        name: "MU Density diff", code: muDensityDiff,
        description: "Calculates the MU Density for the first `.trf` file and the first RT DICOM `.dcm` file. Saves a `.png` of the plot of the difference."
    },
    {
        name: "trf2dcm", code: trf2dcm,
        description: "Converts files that end in `.trf` into a RT DICOM plan file. Requires the RT DICOM plan file that was used for delivery as a template."
    }
]