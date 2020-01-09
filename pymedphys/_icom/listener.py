import pathlib
import shutil
import socket
from datetime import datetime

BATCH = 120
BUFFER_SIZE = 16384
ICOM_PORT = 1706


def listen(ip, data_dir):
    data_dir = pathlib.Path(data_dir)
    holding_dir = data_dir.joinpath("holding")
    processing_dir = data_dir.joinpath("processing")

    holding_dir.mkdir(exist_ok=True, parents=True)
    processing_dir.mkdir(exist_ok=True)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, ICOM_PORT))
    print(s)

    try:
        while True:
            data = b""
            for _ in range(BATCH):
                data += s.recv(BUFFER_SIZE)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{ip}_{timestamp}.txt"

            holding_path = holding_dir.joinpath(filename)
            processing_path = processing_dir.joinpath(filename)

            with open(holding_path, "wb") as a_file:
                a_file.write(data)

            shutil.move(holding_path, processing_path)
    finally:
        s.close()
        print(s)


def listen_cli(args):
    listen(args.ip, args.directory)
