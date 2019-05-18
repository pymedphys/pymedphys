import os

if os.environ['SITE'] == 'docs':
    os.system("yarn install:prod && yarn pip:install:docs")
    os.system(
        "export PATH=`pwd`/bin:$PATH && yarn docs:prebuild && sphinx-build -W docs docs/_build/html")
    os.system("mv docs/_build/html site")
elif os.environ['SITE'] == 'app':
    os.system('yarn app:wheels')
    os.system('mv app site')
