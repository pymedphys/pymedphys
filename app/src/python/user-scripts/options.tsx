import trf2csv from './trf2csv.py';
// import muDensityDiff from './mu-density-diff.py';
import trf2dcm from './trf2dcm.py';
import anonymiseDicom from './anonymise-dicom.py';
import splitFractionGroups from './split-fraction-groups.py';

export interface IUserScript {
    name: string;
    description: string;
    code: string;
}

export const USER_SCRIPTS: IUserScript[] = [
    {
        name: "trf2csv", code: trf2csv,
        description: "Convert files that end in `.trf` into header and table `.csv` files"
    },
    // {
    //     name: "MU Density diff", code: muDensityDiff,
    //     description: "Prints the MU Density for the first `.trf` file and the first RT DICOM `.dcm` file"
    // },
    {
        name: "trf2dcm", code: trf2dcm,
        description: "Converts files that end in `.trf` into DICOM RT Plan files using a user-supplied DICOM RT Plan file template."
    },
    {
        name: "Anonymise DICOM", code: anonymiseDicom,
        description: "Anonymises DICOM headers"
    },
    {
        name: "Split Fraction Groups", code: splitFractionGroups,
        description: "Splits an RT Plan DICOM file into its separate fractions"
    }
]
