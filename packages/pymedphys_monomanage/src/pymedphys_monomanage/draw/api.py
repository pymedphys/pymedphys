from .packages import draw_packages
from .modules import draw_modules

def all(save_directory):
    draw_packages(save_directory)
    draw_modules(save_directory)