import json
from urllib import request
import pathlib
import zipfile
import os

import pymedphys


BASE_DOWNLOAD_URL = "https://github.com/pymedphys/data/releases/download"

data_root = pymedphys._config.get_config_dir().joinpath("data")

nnUNet_data_root = data_root.joinpath("nnUNet")

nnUNet_raw_data_base = nnUNet_data_root.joinpath("nnUNet_raw_data_base")
raw_data_dir = nnUNet_raw_data_base.joinpath("nnUNet_raw_data")
relative_raw_data_dir = raw_data_dir.relative_to(data_root)

hash_path = nnUNet_data_root.joinpath("hashes.json")


def main():
    task = "Task06_Lung"
    task_number = task.split("_")[0].replace("Task", "0")

    nnUNet_data_root.mkdir(exist_ok=True, parents=True)
    raw_data_dir.mkdir(exist_ok=True, parents=True)

    here = pathlib.Path(".")

    nnUNet_preprocessed = here.joinpath("nnUNet_preprocessed")
    results_folder = here.joinpath("results")

    if not hash_path.exists():
        with open(hash_path, "w") as f:
            f.write("{}")

    gen = get_filepaths_for_task(task)
    list(gen)

    task_path = raw_data_dir.joinpath(task)

    metadata_path = data_root.joinpath(get_metadata_path(task))

    metadata = get_metadata(task)
    metadata["test"] = []

    with open(metadata_path, "w") as f:
        json.dump(metadata, f)

    ts_path = task_path.joinpath("imagesTs")
    ts_path.mkdir(exist_ok=True)

    os.environ["nnUNet_raw_data_base"] = str(nnUNet_raw_data_base)
    os.environ["nnUNet_preprocessed"] = str(nnUNet_preprocessed)
    os.environ["RESULTS_FOLDER"] = str(results_folder)

    os.system(f"nnUNet_convert_decathlon_task -i {str(task_path)} -p 1")
    os.system(f"nnUNet_plan_and_preprocess -t {task_number} --verify_dataset_integrity")
    os.system(f"nnUNet_train 2d nnUNetTrainerV2 {task} 0")


def get_metadata_path(task):
    return relative_raw_data_dir.joinpath(task, "dataset.json")


def get_metadata(task):
    download_url = f"{BASE_DOWNLOAD_URL}/{task}/dataset.json"
    metadata_path = pymedphys.data_path(
        get_metadata_path(task),
        url=download_url,
        hash_filepath=hash_path,
        delete_when_no_hash_found=False,
    )

    with open(metadata_path) as f:
        metadata = json.load(f)

    return metadata


def download_task_path(task, path):
    url = f"{BASE_DOWNLOAD_URL}/{task}/{path[2:].replace('/', '--os.sep--')}"
    full_path = relative_raw_data_dir.joinpath(task).joinpath(path)

    return pymedphys.data_path(
        full_path, url=url, hash_filepath=hash_path, delete_when_no_hash_found=False
    )


def get_filepaths_for_task(task):
    metadata = get_metadata(task)

    for paths in metadata["training"]:
        image_path = download_task_path(task, paths["image"])
        label_path = download_task_path(task, paths["label"])

        yield image_path, label_path


if __name__ == "__main__":
    main()
