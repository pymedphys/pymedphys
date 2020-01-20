import lzma
import pathlib

from . import extract, observer


def save_patient_data(start_timestamp, patient_data, output_dir: pathlib.Path):
    _, patient_id = extract.extract(patient_data[0], "Patient ID")

    for data in patient_data:
        _, patient_name = extract.extract(data, "Patient Name")
        if not patient_name is None:
            break

    patient_dir = output_dir.joinpath(f"{patient_id}_{patient_name}")
    patient_dir.mkdir(parents=True, exist_ok=True)

    reformated_timestamp = (
        start_timestamp.replace(":", "").replace("T", "_").replace("-", "")
    )
    filename = patient_dir.joinpath(f"{reformated_timestamp}.xz")

    data = b""
    for item in patient_data:
        data += item

    with lzma.open(filename, "w") as f:
        f.write(data)


class PatientIcomData:
    def __init__(self, output_dir):
        self._data = {}
        self._usage_start = {}
        self._current_patient_data = {}
        self._output_dir = pathlib.Path(output_dir)

    def update_data(self, ip, data):
        try:
            self._data[ip].append(data)
        except KeyError:
            self._data[ip] = [data]

        timestamp = data[8:26].decode()
        shrunk_data, patient_id = extract.extract(data, "Patient ID")
        shrunk_data, patient_name = extract.extract(shrunk_data, "Patient Name")
        shrunk_data, machine_id = extract.extract(shrunk_data, "Machine ID")
        print(
            f"IP: {ip} | Timestamp: {timestamp} | "
            f"Patient ID: {patient_id} | "
            f"Patient Name: {patient_name} | Machine ID: {machine_id}"
        )

        try:
            usage_start = self._usage_start[ip]
        except KeyError:
            usage_start = None

        if patient_id is not None:
            if usage_start is None:
                self._current_patient_data[ip] = []

                timestamp = data[8:26].decode()
                iso_timestamp = f"{timestamp[0:10]}T{timestamp[10::]}"
                self._usage_start[ip] = iso_timestamp

            self._current_patient_data[ip].append(data)
        elif not usage_start is None:
            save_patient_data(
                usage_start, self._current_patient_data[ip], self._output_dir
            )
            self._current_patient_data[ip] = None
            self._usage_start[ip] = None


def archive_by_patient(directories_to_watch, output_dir):
    patient_icom_data = PatientIcomData(output_dir)

    def archive_by_patient_callback(ip, data):
        patient_icom_data.update_data(ip, data)

    observer.observe_with_callback(directories_to_watch, archive_by_patient_callback)


def archive_by_patient_cli(args):
    directories_to_watch = args.directories
    output_dir = args.output_dir

    archive_by_patient(directories_to_watch, output_dir)
