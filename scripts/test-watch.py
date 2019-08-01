import os


def main():
    try:
        os.remove(".testmondata")
    except FileNotFoundError:
        pass

    os.system("ptw -- --testmon -vv --maxfail=1")


if __name__ == "__main__":
    main()
