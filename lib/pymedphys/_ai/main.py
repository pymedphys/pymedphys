import pathlib

from streamlit.web import bootstrap

HERE = pathlib.Path(__file__).parent
APP_ROOT = HERE / "app.py"


def main():
    bootstrap.run(str(APP_ROOT), args=list(), flag_options=dict(), is_hello=False)


if __name__ == "__main__":
    main()
