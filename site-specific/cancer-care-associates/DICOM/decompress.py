import os
import pathlib
import shutil

HERE = pathlib.Path(__file__).parent.resolve()


def main():
    input_dir = HERE.joinpath("input")
    output_dir = HERE.joinpath("output")

    input_files = input_dir.glob("**/*")

    for path in input_files:
        if not path.is_dir():
            new_path = output_dir.joinpath(path.relative_to(input_dir))
            print("\n================================================================")
            if new_path.exists():
                print("{} already exists, skipping...".format(new_path))
            else:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                print("Attempting decompression:{} --> {}".format(path, new_path))
                try:
                    command = 'gdcmconv -w -i "{}" -o "{}"'.format(path, new_path)
                    print(command)
                    os.system(command)
                except Exception as e:
                    print(e)

                if not new_path.exists():
                    print("Decompression failed, just copying file instead...")
                    shutil.copy2(str(path), str(new_path))

            print("================================================================")


if __name__ == "__main__":
    main()
