# Dictionary created by Ara Alexandrian
# Dictionaries contain the following keys: D1-10cc, Mean, Max, V%, D%, and Mean_95%.
# They obey this data structure:

# D1-10cc: The dose received for range of volumes 1-10cc
# D1-10cc  -> (Dose, Toxicity Rate, Endpoint)

# Mean: The mean dose received by the OAR. This has a Dose limit and toxicity rate associated with it.
# Mean     -> (Dose, Toxicity Rate, Endpoint)

# Max: this is the max dose the OAR should receive. This has a Dose limit and toxicity rate associated with it.
# Max      -> (Dose, Toxicity Rate, Endpoint)

# V%: This is the dose received by a particular volume %. This has a Dose limit, Volume %, and toxicity rate associated with it.
# V%       -> (Dose, Volume % or cc if > 1, Toxicity Rate, Endpoint)

# D%: This is the dose received by a particular amount of cubic centimeters. This has a Dose, volume of cc, and toxicity rate associated with it.
# D%      -> (Dose, Volume cc, Toxicity Rate, Endpoint)

# Mean_95%: This is the mean dose to 95% of the gland. It has a dose limit, and toxicity rate assosiated with it.
# Mean_95% -> (Dose, Toxicity Rate, Endpoint)

Brain = {
    "D1_10cc": " ",
    "Mean": " ",
    "Max": [
        (60, 0, 0.03, "Symptomatic necrosis"),
        (72, 0, 0.05, "Symptomatic necrosis"),
        (90, 0, 0.10, "Symptomatic necrosis"),
    ],
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Brain_stem = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": [
        (54, 0, 0.05, "Neuropathy or necrosis"),
        (64, 0, 0.05, "Neuropathy or necrosis"),
    ],
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Chiasm = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": [
        # Linearly Scaled Toxicity Rate
        (55, 0, 0.03, "Optic neuropathy"),
        (56, 0, 0.04, "Optic neuropathy"),
        (57, 0, 0.05, "Optic neuropathy"),
        (58, 0, 0.06, "Optic neuropathy"),
        (59, 0, 0.07, "Optic neuropathy"),
        (60, 0, 0.08, "Optic neuropathy"),
        (61, 0, 0.09, "Optic neuropathy"),
        (62, 0, 0.10, "Optic neuropathy"),
        (63, 0, 0.11, "Optic neuropathy"),
        (64, 0, 0.12, "Optic neuropathy"),
        (65, 0, 0.13, "Optic neuropathy"),
        (66, 0, 0.14, "Optic neuropathy"),
        (67, 0, 0.15, "Optic neuropathy"),
        (68, 0, 0.16, "Optic neuropathy"),
        (69, 0, 0.17, "Optic neuropathy"),
        (70, 0, 0.18, "Optic neuropathy"),
        (71, 0, 0.19, "Optic neuropathy"),
        (56, 0, 0.20, "Optic neuropathy"),
        (73, 0, 0.21, "Optic neuropathy"),
    ],
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Optic_nerve_L = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": [
        (55, 0, 0.03, "Optic neuropathy"),
        (56, 0, 0.04, "Optic neuropathy"),
        (57, 0, 0.05, "Optic neuropathy"),
        (58, 0, 0.06, "Optic neuropathy"),
        (59, 0, 0.07, "Optic neuropathy"),
        (60, 0, 0.08, "Optic neuropathy"),
        (61, 0, 0.09, "Optic neuropathy"),
        (62, 0, 0.10, "Optic neuropathy"),
        (63, 0, 0.11, "Optic neuropathy"),
        (64, 0, 0.12, "Optic neuropathy"),
        (65, 0, 0.13, "Optic neuropathy"),
        (66, 0, 0.14, "Optic neuropathy"),
        (67, 0, 0.15, "Optic neuropathy"),
        (68, 0, 0.16, "Optic neuropathy"),
        (69, 0, 0.17, "Optic neuropathy"),
        (70, 0, 0.18, "Optic neuropathy"),
        (71, 0, 0.19, "Optic neuropathy"),
        (56, 0, 0.20, "Optic neuropathy"),
        (73, 0, 0.21, "Optic neuropathy"),
    ],
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Optic_nerve_R = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": [
        (55, 0, 0.03, "Optic neuropathy"),
        (56, 0, 0.04, "Optic neuropathy"),
        (57, 0, 0.05, "Optic neuropathy"),
        (58, 0, 0.06, "Optic neuropathy"),
        (59, 0, 0.07, "Optic neuropathy"),
        (60, 0, 0.08, "Optic neuropathy"),
        (61, 0, 0.09, "Optic neuropathy"),
        (62, 0, 0.10, "Optic neuropathy"),
        (63, 0, 0.11, "Optic neuropathy"),
        (64, 0, 0.12, "Optic neuropathy"),
        (65, 0, 0.13, "Optic neuropathy"),
        (66, 0, 0.14, "Optic neuropathy"),
        (67, 0, 0.15, "Optic neuropathy"),
        (68, 0, 0.16, "Optic neuropathy"),
        (69, 0, 0.17, "Optic neuropathy"),
        (70, 0, 0.18, "Optic neuropathy"),
        (71, 0, 0.19, "Optic neuropathy"),
        (56, 0, 0.20, "Optic neuropathy"),
        (73, 0, 0.21, "Optic neuropathy"),
    ],
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Spinal_cord = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": [
        (50, 0.002, "Myelopathy"),
        (60, 0.06, "Myelopathy"),
        (69, 0.50, "NTR", "Myelopathy"),
    ],
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Cochlea = {
    "D1-10cc": " ",
    "Mean": [(25, 0.30, "NTR", "Sensory-neural hearing loss")],
    "Max": " ",
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Cochlea_L = {
    "D1-10cc": " ",
    "Mean": [(25, 0.30, "NTR", "Sensory-neural hearing loss")],
    "Max": " ",
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Cochlea_R = {
    "D1-10cc": " ",
    "Mean": [(25, 0.30, "NTR", "Sensory-neural hearing loss")],
    "Max": " ",
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Parotid_L = {
    "D1-10cc": " ",
    "Mean": [
        (25, 0.20, "NTR", "Long-term salivary function <25%"),
        (39, 0.50, "NTR", "Long-term salivary function <25%"),
    ],
    "Max": " ",
    "V%": [
        (32, 0.66, 0.05, "Emami: Xerostomia"),
        (46, 0.66, 0.50, "Emami: Xerostomia"),
    ],
    "D%": " ",
    "Mean_95%": " ",
}

Parotid_R = {
    "D1-10cc": " ",
    "Mean": [
        (25, 0.20, "NTR", "Long-term salivary function <25%"),
        (39, 0.50, "NTR", "Long-term salivary function <25%"),
    ],
    "Max": " ",
    "V%": [
        (32, 0.66, 0.05, "Emami: Xerostomia"),
        (46, 0.66, 0.50, "Emami: Xerostomia"),
    ],
    "D%": " ",
    "Mean_95%": " ",
}

Parotid_unilateral = {
    "D1-10cc": " ",
    "Mean": [(20, 0.20, "NTR", "Long-term salivary function <25%")],
    "Max": " ",
    "V%": [
        (32, 0.66, 0.05, "Emami: Xerostomia"),
        (46, 0.66, 0.50, "Emami: Xerostomia"),
    ],
    "D%": " ",
    "Mean_95%": " ",
}

Pharyngeal_constrictors = {
    "D1-10cc": " ",
    "Mean": [(50, 0.20, "NTR", "Symptomatic dysphagia and aspiration")],
    "Max": " ",
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Larynx = {
    "D1-10cc": " ",
    "Mean": [(50, 0.30, "NTR", "Aspiration"), (44, 0.20, "Edema")],
    "Max": [(66, 0.30, "NTR", "Vocal dysfunction")],
    "V%": [(50, 0.27, 0.20, "Edema"), (44, 0.20, 0.20, "Edema")],
    "D%": " ",
    "Mean_95%": " ",
}

Lung_L = {
    "D1-10cc": " ",
    "Mean": [
        (7, 0.05, "NTR", "Symptomatic pneumonitis"),
        (13, 0.10, "NTR", "Symptomatic pneumonitis"),
        (20, 0.20, "NTR", "Symptomatic pneumonitis"),
        (24, 0.30, "NTR", "Symptomatic pneumonitis"),
        (27, 0.40, "NTR", "Symptomatic pneumonitis"),
    ],
    "Max": " ",
    "V%": [(20, 0.30, 0.20, "Symptomatic pneumonitis")],
    "D%": " ",
    "Mean_95%": " ",
}

Lung_R = {
    "D1-10cc": " ",
    "Mean": [
        (7, 0.05, "NTR", "Symptomatic pneumonitis"),
        (13, 0.10, "NTR", "Symptomatic pneumonitis"),
        (20, 0.20, "NTR", "Symptomatic pneumonitis"),
        (24, 0.30, "NTR", "Symptomatic pneumonitis"),
        (27, 0.40, "NTR", "Symptomatic pneumonitis"),
    ],
    "Max": " ",
    "V%": [(20, 0.30, 0.20, "Symptomatic pneumonitis")],
    "D%": " ",
    "Mean_95%": " ",
}

Total_Lung = {
    "D1-10cc": " ",
    "Mean": [
        (7, 0.05, "NTR", "Symptomatic pneumonitis"),
        (13, 0.10, "NTR", "Symptomatic pneumonitis"),
        (20, 0.20, "NTR", "Symptomatic pneumonitis"),
        (24, 0.30, "NTR", "Symptomatic pneumonitis"),
        (27, 0.40, "NTR", "Symptomatic pneumonitis"),
    ],
    "Max": " ",
    "V%": [(20, 0.30, 0.20, "Symptomatic pneumonitis")],
    "D%": " ",
    "Mean_95%": " ",
}
Esophagus = {
    "D1-10cc": " ",
    "Mean": [(34, 0.05, "NTR", "Grade 3+ esophagitis")],
    "Max": " ",
    "V%": [
        (35, 0.50, 0.30, "Grade 2+ esophagitis"),
        (50, 0.40, 0.30, "Grade 2+ esophagitis"),
        (70, 0.20, 0.30, "Grade 2+ esophagitis"),
    ],
    "D%": " ",
    "Mean_95%": " ",
}

Heart_pericardium = {
    "D1-10cc": " ",
    "Mean": [(26, 0.15, "NTR", "Pericarditis")],
    "V%": [(30, 0.46, 0.15, "Pericarditis")],
    "D%": " ",
    "Mean_95%": " ",
}

Heart = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": [(25, 0.10, 0.01, "Long term cardiac mortality")],
    "D%": " ",
    "Mean_95%": " ",
}

Liver = {
    "D1-10cc": " ",
    "Mean": [
        (30, 0.05, "NTR", "RILD (in normal liver function)"),
        (31, 0.05, "NTR", "RILD (in normal liver function)"),
        (32, 0.05, "NTR", "RILD (in normal liver function)"),
        (42, 0.50, "NTR", "RILD (in normal liver function)"),
        (28, 0.05, "NTR", "RILD (in Child-Pugh A or HCC"),
        (36, 0.50, "NTR", "RILD (in Child-Pugh A or HCC"),
    ],
    "Max": " ",
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Kidney_bilateral = {
    "D1-10cc": " ",
    "Mean": [
        (15, 0.05, "NTR", "Clinical dysfunction"),
        (16, 0.05, "NTR", "Clinical dysfunction"),
        (17, 0.05, "NTR", "Clinical dysfunction"),
        (18, 0.50, "NTR", "Clinical dysfunction"),
        (28, 0.05, "NTR", "Clinical dysfunction"),
        (36, 0.50, "NTR", "Clinical dysfunction"),
    ],
    "Max": " ",
    "V%": [
        (12, 0.55, 0.05, "Clinical dysfunction"),
        (20, 0.32, 0.05, "Clinical dysfunction"),
        (23, 0.30, 0.05, "Clinical dysfunction"),
        (28, 0.20, 0.05, "Clinical dysfunction"),
    ],
    "D%": " ",
    "Mean_95%": " ",
}

Stomach = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": " ",
    "D%": [(45, 1.0, 0.07, "Ulceration")],
    "Mean_95%": " ",
}

Small_bowel = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": [(45, 195, 0.10, "Grade 3+ toxicity")],
    "D%": " ",
    "Mean_95%": " ",
}

Rectum = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": [
        (50, 0.50, 0.10, "Grade 3+ toxicity"),
        (60, 0.35, 0.10, "Grade 3+ toxicity"),
        (65, 0.25, 0.10, "Grade 3+ toxicity"),
        (70, 0.20, 0.10, "Grade 3+ toxicity"),
        (75, 0.15, 0.10, "Grade 3+ toxicity"),
    ],
    "D%": " ",
    "Mean_95%": " ",
}

Bladder_bladder_cancer = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": [(65, 0.06, "NTR", "Grade 3+ toxicity")],
    "V%": " ",
    "D%": " ",
    "Mean_95%": " ",
}

Bladder = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": [
        (65, 0.50, "NTR", "Grade 3+ toxicity"),
        (70, 0.35, "NTR", "Grade 3+ toxicity"),
        (75, 0.25, "NTR", "Grade 3+ toxicity"),
        (80, 0.15, "NTR", "Grade 3+ toxicity"),
    ],
    "D%": " ",
    "Mean_95%": " ",
}

Femoral_head_L = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": [(47, 0, 0.25, "Emami: Necrosis"), (52, 0, 0.75, "Emami: Necrosis")],
    "D%": " ",
    "Mean_95%": " ",
}

Femoral_head_R = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": [(47, 0, 0.25, "Emami: Necrosis"), (52, 0, 0.75, "Emami: Necrosis")],
    "D%": " ",
    "Mean_95%": " ",
}

Penile_bulb = {
    "D1-10cc": " ",
    "Mean": " ",
    "Max": " ",
    "V%": " ",
    "D%": [
        (90, 0.50, 0.35, "Severe erectile dysfunction"),
        (70, 0.60, 0.55, "Severe erectile dysfunction"),
    ],
    "Mean_95%": [(50, 0.35, "NTR", "Severe erectile dysfunction")],
}
