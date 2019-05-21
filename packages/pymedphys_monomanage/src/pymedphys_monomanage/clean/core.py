import shutil

try:
    shutil.rmtree('dist')
except FileNotFoundError:
    pass


try:
    shutil.rmtree('build')
except FileNotFoundError:
    pass
