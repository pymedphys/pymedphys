import lzma
import pathlib
import shutil
import socket
from datetime import datetime

MINUTES_OF_DATA = 30
BATCH = 240 * MINUTES_OF_DATA
BUFFER_SIZE = 16384
ICOM_PORT = 1706


def write_data(data, ip, holding_dir, processing_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{ip}_{timestamp}.xz"

    holding_path = holding_dir.joinpath(filename)
    processing_path = processing_dir.joinpath(filename)

    with lzma.open(holding_path, "w") as f:
        f.write(data)

    shutil.move(holding_path, processing_path)


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

            write_data(data, ip, holding_dir, processing_dir)

    finally:
        s.close()
        print(s)
        write_data(data, ip, holding_dir, processing_dir)


def listen_cli(args):
    listen(args.ip, args.directory)
