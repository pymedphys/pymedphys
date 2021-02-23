from pymedphys._imports import pandas as pd

alias_df = pd.read_csv("test3.csv")
alias_dict = alias_df.iloc[0].to_dict()
alias_df.to_csv("test3.csv", index=False)
# ALIASES = {
#     "Bladder": [
#         "bladder",
#     ],
#     "Bowel_bag": [
#         "bowel_bag",
#         "bowel bag",
#     ],
#     "Brachial_plexus": [
#         "brachial_plexus",
#         "brachial plexus",
#         "r brachial plexus",
#         "l brachial plexus",
#     ],
#     "Brain": [
#         "brain",
#     ],
#     "Brain_stem": [
#         "brainstem",
#         "brain stem",
#     ],
#     "Chiasm": [
#         "chiasm",
#         "optic chiasm",
#         "optic_chiasm",
#         "opticchiasm",
#         "optic chism",
#     ],
#     "Cochlea": [
#         "cochlea",
#     ],
#     "Cochlea_L": [
#         "cochlea_l",
#         "cochlea lt",
#         "cochlea_lt",
#         "left cochlea",
#         "l cochlea",
#         "lt cochlea",
#         "lt_cochlea",
#         "cochlea left",
#     ],
#     "Cochlea_R": [
#         "cochlea_r",
#         "cochlea rt",
#         "cochlea_rt",
#         "right cochlea",
#         "r cochlea",
#         "rt cochlea",
#         "rt_cochlea",
#         "cochlea right",
#     ],
#     "Duodenum": [
#         "duodenum",
#     ],
#     "Esophagus": [
#         "esophagus",
#         "esophagus partial",
#         "esophagus par",
#     ],
#     "Femoral_head_L": [
#         "femoral_head_l",
#         "femur_head_l",
#         "left femoral heads",
#         "femoral head l",
#         "l femur",
#         "femoralhead (left)",
#         "l femoral head",
#         "l fem head",
#         "lt fem head",
#         "left femoral head",
#         "left femur",
#         "lt femur",
#         "l-fem head",
#         "femoralhead_l",
#     ],
#     "Femoral_head_R": [
#         "femur_head_r",
#         "femur_head_r",
#         "right femoral heads",
#         "femoralhead (right)",
#         "r femur",
#         "r_fem",
#         "r femoral head",
#         "r fem head",
#         "rt fem head",
#         "right femoral head",
#         "r-fem head",
#         "femoralhead_r",
#     ],
#     "Heart": [
#         "heart",
#     ],
#     "Heart_pericardium": [
#         "heart_pericardium",
#         "pericardium",
#     ],
#     "Kidney_bilateral": [
#         "kidney_bilateral",
#     ],
#     "Kidney_L": [
#         "kidney_l",
#         "partial lt kidney",
#         "lft kidney",
#         "left kidney",
#         "kidney (left)",
#         "l kidney",
#         "lt kidney",
#         "lt_kidney",
#         "kidney_left",
#         "kidney_lt",
#         "kidney_lft",
#     ],
#     "Kidney_R": [
#         "kidney_r",
#         "partial rt kidney",
#         "right kidney",
#         "kidney (right)",
#         "r kidney",
#         "rt kidney",
#         "rt_kidney",
#         "kidney_right",
#         "kidney_rt",
#     ],
#     "Larynx": [
#         "larynx",
#     ],
#     "Lens_L": [
#         "lens_l",
#     ],
#     "Lens_R": [
#         "lens_r",
#     ],
#     "Liver": [
#         "liver",
#     ],
#     "Lung_L": [
#         "Lung_L",
#         "LEFT LUNG",
#         "Lung (Left)",
#         "L LUNG",
#         "lt lung",
#         "LUNG_LEFT",
#         "l-lung",
#         "Lung_L1",
#     ],
#     "Lung_R": [
#         "lung_r",
#         "right lung",
#         "lung (right)",
#         "r lung",
#         "rt lung",
#         "lung_right",
#         "r-lung",
#         "lung_r1",
#     ],
#     "Mandible": [
#         "mandible",
#     ],
#     "Optic_nerve_L": [
#         "opticnrv_l",
#         "left optic nerve",
#         "optic nerve l",
#         "l optic nerve",
#         "l optic n",
#         "lon",
#         "l on",
#     ],
#     "Optic_nerve_R": [
#         "opticnrv_r",
#         "right optic nerve",
#         "r optic nerve",
#         "ron",
#         "r optic n",
#     ],
#     "Oral_cavity": [
#         "oral_cavity",
#         "oral cavity",
#     ],
#     "Orbit_L": [
#         "orbital_l",
#         "orbital l",
#         "l orbit",
#         "lt orbit",
#         "left_orbit",
#         "left orbit",
#         "orbit_left",
#         "orbit left",
#     ],
#     "Orbit_R": [
#         "orbital_r",
#         "orbital r",
#         "r orbit",
#         "rt orbit",
#         "right_orbit",
#         "right orbit",
#         "orbit_right",
#         "orbit right",
#     ],
#     "Parotid_L": [
#         "parotid_l",
#         "left parotid",
#         "l parotid",
#         "l_parotid",
#         "lt parotid",
#     ],
#     "Parotid_R": [
#         "parotid r",
#         "parotid_r",
#         "right parotid",
#         "r parotid",
#         "r_parotid",
#         "rt parotid",
#         "rt_parotid",
#     ],
#     "Parotid_unilateral": [
#         "parotid_unilateral",
#     ],
#     "Penile_bulb": [
#         "penilebulb",
#         "penile bulb",
#         "penile_bulb",
#         "bulb",
#     ],
#     "Pharyngeal_constrictors": [
#         "pharyngeal_constrictors",
#     ],
#     "Rectum": [
#         "rectum",
#     ],
#     "Sigmoid": [
#         "sigmoid",
#     ],
#     "Small_bowel": [
#         "small_bowel",
#         "small bowel",
#         "bowel_small",
#         "bowel small",
#     ],
#     "Spinal_cord": [
#         "spinalcord",
#         "cord",
#         "spinal cord",
#         "spinal cord plus 5mm",
#         "spinalcord plus 5mm",
#         "spinal cord + 5mm",
#         "spinalcord + 5mm",
#     ],
#     "Stomach": [
#         "Stomach",
#     ],
#     "Temporal_lobes": [
#         "temporal_lobes",
#         "temporal lobe",
#     ],
#     "Tongue": [
#         "tongue",
#     ],
#     "Total_Lung": [
#         "lungs",
#         "total lung-gtv",
#         "total lung-itv",
#         "total lung",
#     ],
# }

aliases_df = pd.DataFrame()
for key, values in ALIASES.items():
    df[key] = [values]
