import shutil


def main():
    try:
        shutil.copy("../../README.rst", "README.rst")
    except IOError:
        pass


if __name__ == "__main__":
    main()
