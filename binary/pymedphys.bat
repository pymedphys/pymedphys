@echo off
pushd "%~dp0"
FOR /F "tokens=*" %%g IN ('resolve-path.cmd') do (SET PYTHON_DIR=%%g)
popd

"%PYTHON_DIR%\python" -m pymedphys %*
