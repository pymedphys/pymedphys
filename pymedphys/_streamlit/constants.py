# TODO: Make this configurable
HOSTNAME = "physics-server"
BASE_URL_PATHS = ["/delivery/", "/monaco-anonymisation/", "/electrons/", "/dashboard/"]

NAMES = [
    "MU Density Delivery Comparison",
    "Monaco Anonymisation",
    "Electron Insert Factors",
    "Dashboard",
]
SCRIPTS = [
    "mudensity-compare.py",
    "anonymise-monaco.py",
    "electrons.py",
    "dashboard.py",
]
PORTS = [28888, 28889, 28890, 28891]
