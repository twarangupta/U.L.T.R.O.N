@echo off
rem Start ULTRON. Pass --benchmark or --self-test to run those instead.
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
venv\Scripts\python.exe -m ultron %*
