import os

os.system('mkdir site')

if os.environ['SITE'] == 'docs':
    os.system("yarn install:prod && yarn pip:install:docs")
    os.system(
        "export PATH=`pwd`/bin:$PATH && yarn docs:prebuild && sphinx-build -W docs docs/_build/html")
    os.system("mv docs/_build/html/* site")

elif os.environ['SITE'] == 'app':
    os.system('yarn monomanage:install')
    os.system('yarn app:wheels')
    os.system('cd app && yarn && yarn build && cd ../')
    os.system('mv app/build/* site')

elif os.environ['SITE'] == 'home':
    pass
