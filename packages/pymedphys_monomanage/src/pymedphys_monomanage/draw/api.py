from .packages import draw_packages
from .directories import draw_directory_modules
from .files import draw_file_modules

def all(save_directory):
    draw_packages(save_directory)
    draw_directory_modules(save_directory)
    draw_file_modules(save_directory)