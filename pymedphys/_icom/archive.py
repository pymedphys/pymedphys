from . import patients


def archive_cli(args):
    if args.by_patient:
        return patients.archive_by_patient_cli(args)

    raise ValueError("No archive type chosen")


# import lzma
# import multiprocessing
# import pathlib
# import shutil
# import socket
# from datetime import datetime


# MINUTES_OF_DATA = 5
# ICOM_HZ = 4
# SECONDS_OF_DATA = MINUTES_OF_DATA * 60
# BATCH = int(ICOM_HZ * SECONDS_OF_DATA)


#             # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
#             # filename = f"{ip}_{timestamp}"

#             # temp_path = live_dir.joinpath(f"{filename}.txt")
#             # shutil.move(live_path, temp_path)

#             # compressed_path = compressed_dir.joinpath(f"{filename}.xz")

#             # multiprocessing.Process(
#             #     target=compress_and_move_data, args=(temp_path, compressed_path)
#             # ).start()


#         # multiprocessing.Process(
#         #     target=compress_and_move_data, args=(live_path, compressed_path)
#         # ).start()


# def compress_and_move_data(input_file, output_file):
#     input_file = pathlib.Path(input_file)
#     output_file = pathlib.Path(output_file)

#     with open(input_file, "rb") as in_file:
#         with lzma.open(output_file, "w") as out_file:
#             out_file.write(in_file.read())

#     input_file.unlink()
