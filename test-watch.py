import os


def main():
    os.remove('.testmondata')
    os.system('ptw -- --testmon')


if __name__ == "__main__":
    main()
