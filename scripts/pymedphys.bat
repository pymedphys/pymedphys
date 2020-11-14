@echo off
pushd "%~dp0"

FOR /F "tokens=*" %%g IN ('resolve_path.cmd') do (SET PYTHON_DIR=%%g)
SET PATH=%PYTHON_DIR%;%PYTHON_DIR%\Scripts;"%PATH%"

popd

%PYTHON_DIR%\python -m pymedphys %*
