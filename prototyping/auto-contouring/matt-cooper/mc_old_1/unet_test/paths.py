import glob
import random


def get_paths(data_path, context):
    patient_paths = glob.glob(data_path + "/*")

    context_paths = glob.glob(data_path + "/*/*CT*", recursive=True)
    context_paths.sort()

    input_paths = [
        glob.glob(path + "/*CT*")[context:-context] for path in patient_paths
    ]
    input_paths = [item for sublist in input_paths for item in sublist]
    random.shuffle(input_paths)

    label_paths = glob.glob(data_path + "/*/*RS*", recursive=True)

    assert len(context_paths) - (len(label_paths) * 2 * context) == len(input_paths)

    return input_paths, context_paths, label_paths


def split_paths(input_paths, ratio):
    num = len(input_paths)
    num_train = int(num * ratio[0] // 1)
    num_valid = int(num * ratio[1] // 1)
    num_test = int(num * ratio[2] // 1)

    print(f"Total: {num} = Train: {num_train} + Valid: {num_valid} + Test: {num_test}")

    train_paths = input_paths[0:num_train]
    valid_paths = input_paths[num_train : num_train + num_valid]
    test_paths = input_paths[num_train + num_valid :]
    return train_paths, valid_paths, test_paths
