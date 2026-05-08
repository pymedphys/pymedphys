@echo off
REM Render all .puml files in this directory to SVG.
REM Same plantuml.jar discovery as lts_models/pseudonymise/diagrams/_render.cmd
REM (see that file for full doc).

setlocal

set "JAR=%USERPROFILE%\.cache\plantuml\plantuml.jar"
if defined PLANTUML_JAR set "JAR=%PLANTUML_JAR%"

if exist "%JAR%" (
    echo Using plantuml.jar at %JAR%
    pushd "%~dp0"
    java -jar "%JAR%" -tsvg *.puml
    popd
) else (
    where plantuml >nul 2>&1
    if %ERRORLEVEL%==0 (
        echo Using plantuml on PATH
        pushd "%~dp0"
        plantuml -tsvg *.puml
        popd
    ) else (
        echo ERROR: plantuml.jar not found.
        echo Either:
        echo   1. Download plantuml.jar to %USERPROFILE%\.cache\plantuml\plantuml.jar
        echo      from https://github.com/plantuml/plantuml/releases/latest
        echo   2. Set PLANTUML_JAR=path\to\plantuml.jar
        echo   3. Install plantuml on PATH
        exit /b 1
    )
)

pushd "%~dp0"
python _inject_bg.py
popd

echo Done.
