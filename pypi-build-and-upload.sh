rm -rf build dist

# https://pypi.org/project/twine/
python setup.py sdist bdist_wheel
twine upload dist/*
