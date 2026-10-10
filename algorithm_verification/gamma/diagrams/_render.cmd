@echo off
REM Render all .puml files in this directory to SVG.
REM
REM Requires plantuml.jar. Conventional locations checked in order:
REM   %USERPROFILE%\.cache\plantuml\plantuml.jar
REM   %PLANTUML_JAR%   (env var override)
REM   plantuml         (on PATH)
REM
REM Usage:  _render.cmd
REM         (run from this directory)
REM
REM After rendering, also runs _inject_bg.py to add an opaque white background
REM to each SVG (PlantUML emits transparent-canvas SVGs that are invisible on
REM dark IDE themes).

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

REM Inject opaque background into each SVG (idempotent).
pushd "%~dp0"
python _inject_bg.py
popd

echo Done.
