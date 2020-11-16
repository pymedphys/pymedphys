@echo off
@REM Copyright (C) 2020 PyMedPhys Contributors

@REM Licensed under the Apache License, Version 2.0 (the "License");
@REM you may not use this file except in compliance with the License.
@REM You may obtain a copy of the License at

@REM     http://www.apache.org/licenses/LICENSE-2.0

@REM Unless required by applicable law or agreed to in writing, software
@REM distributed under the License is distributed on an "AS IS" BASIS,
@REM WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
@REM See the License for the specific language governing permissions and
@REM limitations under the License.


@REM ==========================================================================
@REM                             Documentation
@REM ==========================================================================

@REM This bat file exposes the PyMedPhys CLI. To see what this CLI can do have
@REM a read through of the documentation:

@REM     https://docs.pymedphys.com/ref/cli/index.html

@REM              ---------------------------------------------
@REM               How to use this batfile anywhere on your PC
@REM              ---------------------------------------------

@REM If you would like to access this CLI tool accross your system you need to
@REM add the directory that contains this `.bat` file into your user path.
@REM To do this, open the start menu and type:

@REM     "Edit environment variables for your account"

@REM From there, find the variable called "PATH". Append to the end of that
@REM variable the directory containing this `.bat` file. Make sure that the
@REM full path location to each directory within the "PATH" variable is
@REM separated by a semicolon (;).

@REM For example, if your "PATH" originally looked like:

@REM     C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem;

@REM And this `.bat` file is located at `C:\Users\sbiggs\bin\pymedphys.bat`,
@REM then you would change it to look like:

@REM     C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem;C:\Users\sbiggs\bin;

@REM To make this change to "PATH" come into effect you should close all of
@REM your open command prompts and then open a new one afresh.

@REM                   -----------------------------------
@REM                    A note about shortcuts and moving
@REM                   -----------------------------------

@REM This batfile will only work if it is in the same location as the
@REM extracted `python-embed` directory. Also, shortcuts to this bat file will
@REM not work as one might expect. If you would like to use this bat file
@REM outside of its original directory please follow the instructions detailed
@REM above to add this `.bat` file's directory to your "PATH".

@REM ==========================================================================

"%~dp0\python-embed\python" -m pymedphys %*
