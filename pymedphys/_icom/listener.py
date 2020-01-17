import lzma
import multiprocessing
import pathlib
import shutil
import socket
from datetime import datetime

MINUTES_OF_DATA = 5
ICOM_HZ = 4
SECONDS_OF_DATA = MINUTES_OF_DATA * 60
BATCH = int(ICOM_HZ * SECONDS_OF_DATA)
BUFFER_SIZE = 16384
ICOM_PORT = 1706


def compress_and_move_data(input_file, output_file):
    input_file = pathlib.Path(input_file)
    output_file = pathlib.Path(output_file)

    with open(input_file, "rb") as in_file:
        with lzma.open(output_file, "w") as out_file:
            out_file.write(in_file.read())

    input_file.unlink()


def listen(ip, data_dir):
    data_dir = pathlib.Path(data_dir)
    live_dir = data_dir.joinpath("live")
    compressed_dir = data_dir.joinpath("compressed")

    live_dir.mkdir(exist_ok=True, parents=True)
    compressed_dir.mkdir(exist_ok=True)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, ICOM_PORT))
    print(s)

    try:
        live_path = live_dir.joinpath(f"{ip}.txt")

        while True:
            with open(live_path, "ba+") as f:
                for _ in range(BATCH):
                    f.write(s.recv(BUFFER_SIZE))

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{ip}_{timestamp}"

            temp_path = live_dir.joinpath(f"{filename}.txt")
            shutil.move(live_path, temp_path)

            compressed_path = compressed_dir.joinpath(f"{filename}.xz")

            multiprocessing.Process(
                target=compress_and_move_data, args=(temp_path, compressed_path)
            ).start()

    finally:
        s.close()
        print(s)

        multiprocessing.Process(
            target=compress_and_move_data, args=(live_path, compressed_path)
        ).start()


def listen_cli(args):
    listen(args.ip, args.directory)
