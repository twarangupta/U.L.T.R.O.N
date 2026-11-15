@echo off
rem Start ULTRON. Pass --benchmark or --self-test to run those instead.
rem Uses venv\Scripts\python.exe in this folder, or ULTRON_PYTHON if set.
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
set "PY=venv\Scripts\python.exe"
if defined ULTRON_PYTHON set "PY=%ULTRON_PYTHON%"
if not exist "%PY%" (
    echo Python not found at "%PY%".
    echo Create the venv here ^(see README^) or set ULTRON_PYTHON to a python.exe.
    exit /b 1
)
"%PY%" -m ultron %*
