@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "host\analyzer_viewer.py" --source record
if errorlevel 1 pause
endlocal
