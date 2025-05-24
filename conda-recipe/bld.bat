@echo off

REM Build script for Windows
REM Install using pip with poetry-core as the build backend
"%PYTHON%" -m pip install . -vv --no-deps --no-build-isolation
if errorlevel 1 exit 1

REM Copy license file to the conda environment
copy LICENSE "%PREFIX%\LICENSE-pymedphys"
if errorlevel 1 exit 1
