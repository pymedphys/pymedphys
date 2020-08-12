# TODO: Make this configurable
HOSTNAME = "physics-server"
BASE_URL_PATHS = ["/delivery/", "/monaco-anonymisation/", "/electrons/"]

NAMES = [
    "MU Density Delivery Comparison",
    "Monaco Anonymisation",
    "Electron Insert Factors",
]
SCRIPTS = ["mudensity-compare.py", "anonymise-monaco.py", "electrons.py"]
PORTS = [28888, 28889, 28890]
