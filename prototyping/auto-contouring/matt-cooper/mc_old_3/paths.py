import glob


def get_patient_paths(data_path):
    patient_paths = glob.glob(data_path + "/*")
    return patient_paths


def get_input_paths(patient_path):
    input_paths = glob.glob(patient_path + "/*CT*", recursive=True)
    return input_paths


def get_label_paths(patient_path):
    label_paths = glob.glob(patient_path + "/*RS*", recursive=True)
    return label_paths


def flatten_list(top_list):
    return [item for sublist in top_list for item in sublist]
